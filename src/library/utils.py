import base64
import hashlib
import logging
import shutil
import typing as T
import zipfile
from pathlib import Path

import polars as pl
import requests
from PIL import Image
from xlsxwriter import Workbook

from library.names import assign_normalized_name
from library.settings import Settings, StoredFileNames

logger = logging.getLogger(__name__)

ID_COL = "target_directory"
SHOP_COLS = [ID_COL, "name", "date", "time", "total"]
ITEMS_COLS = [ID_COL, "name", "price", "count", "mass", "tax", "category"]
NORMALIZED_NAME_COL = "pretty name"


def check_available_extraction_dirs(
    settings: Settings,
) -> T.Tuple[T.List[Path], T.List[Path]]:
    root_dir = settings.get_extraction_artifacts_dir()
    file_names = StoredFileNames()

    # shop info
    shop_info_files = root_dir.rglob(f"**/{file_names.shop_info_parquet}")
    shop_info_files = [f for f in shop_info_files if f.parent != root_dir]
    logger.debug(f"Detected {len(shop_info_files):_} shop info files")

    # items info
    items_info_files = list(root_dir.rglob(f"**/{file_names.items_info_parquet}"))
    items_info_files = [f for f in items_info_files if f.parent != root_dir]
    logger.debug(f"Detected {len(items_info_files):_} items info files")

    return shop_info_files, items_info_files


def compile_infos(info_files: T.List[Path]) -> pl.DataFrame:
    if len(info_files) == 0:
        raise ValueError(f"{len(info_files)=} is zero, expected at least one element.")
    compiled_info = []
    for info_file in info_files:
        info = pl.read_parquet(info_file)
        info = info.with_columns(pl.lit(info_file.parent.name).alias(ID_COL))
        compiled_info.append(info)

    compiled_info = pl.concat(compiled_info, how="diagonal")
    return compiled_info


def internet_connection():
    try:
        res = requests.get("https://status.anthropic.com/", timeout=5)
        success = res.status_code == 200
        logger.info(f"anthropic.com {res.status_code=}")
        return success
    except requests.RequestException as e:
        logger.info(f"anthropic.com is unavailable: {str(e)}")
        return False


def get_compiled_paths(settings: Settings):
    root_dir_collation = settings.get_collation_artifacts_dir().absolute()
    file_names = StoredFileNames()
    compiled_shop_info_path = root_dir_collation / file_names.shop_info_parquet
    compiled_items_info_path = root_dir_collation / file_names.items_info_parquet
    return compiled_shop_info_path, compiled_items_info_path


def collect(settings: Settings):
    compiled_shop_info_path, compiled_items_info_path = get_compiled_paths(settings)
    shop_info_files, items_info_files = check_available_extraction_dirs(settings)

    logger.info("Compiling shop info")
    compiled_shop_info = compile_infos(shop_info_files)
    logger.info(
        f"Compiled shop info for {compiled_shop_info[ID_COL].n_unique():_} receipts, totalling {len(compiled_shop_info):_} lines."
    )

    logger.info("Compiling items info")
    compiled_items_info = compile_infos(items_info_files)
    logger.info(
        f"Compiled items info for {compiled_items_info[ID_COL].n_unique():_} receipts, totalling {len(compiled_items_info):_} lines."
    )

    compiled_shop_info = compiled_shop_info[SHOP_COLS]

    compiled_items_info = compiled_items_info[ITEMS_COLS]

    logger.debug(f"Assigning {NORMALIZED_NAME_COL}")
    compiled_items_info = compiled_items_info.with_columns(
        **{
            NORMALIZED_NAME_COL: pl.col("name").map_elements(
                assign_normalized_name, return_dtype=pl.Utf8
            )
        }
    )

    logger.debug(f"Writing compiled shop info to {compiled_shop_info_path}")
    compiled_shop_info.write_parquet(compiled_shop_info_path)

    logger.debug(f"Writing compiled items info to {compiled_items_info_path}")
    compiled_items_info.write_parquet(compiled_items_info_path)

    logger.info("Done collecting")


def create_zipfile(root_dir_extraction: Path) -> Path:
    if not root_dir_extraction.exists():
        raise FileNotFoundError(
            f"{root_dir_extraction=} does not exist, stopping creation of zipfile."
        )
    path_archive = root_dir_extraction.parent / "extractions.zip"
    logger.debug(f"Creating {path_archive=}")

    with zipfile.ZipFile(
        path_archive, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for file_path in root_dir_extraction.rglob("*"):
            archive.write(file_path, arcname=file_path.relative_to(root_dir_extraction))

    logger.debug(f"{path_archive.exists()=}, {path_archive.is_file()=}")
    return path_archive


def put_id_col_at_end(df: pl.DataFrame, id_col: str) -> pl.DataFrame:
    new_cols = [c for c in df.columns if c != id_col] + [id_col]
    return df.select(new_cols)


def write_excel_workbook(settings: Settings) -> Path:
    root_dir_extraction = settings.get_extraction_artifacts_dir().absolute()
    compiled_shop_info_path, compiled_items_info_path = get_compiled_paths(settings)
    path_excel = root_dir_extraction.parent / "groceries-data.xlsx"
    logger.debug(f"Creating {path_excel=}")

    shops = pl.read_parquet(compiled_shop_info_path)
    items = pl.read_parquet(compiled_items_info_path)

    # https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_excel.html
    with Workbook(path_excel) as wb:
        shops = put_id_col_at_end(shops, ID_COL)
        shops.write_excel(
            workbook=wb,
            worksheet="Shops",
            table_style="Table Style Medium 4",
            freeze_panes=(1, 0),
            autofit=True,
            autofilter=True,
            float_precision=2,
            header_format={"bold": True},
        )

        items = put_id_col_at_end(items, ID_COL)
        items.write_excel(
            workbook=wb,
            worksheet="Items",
            table_style="Table Style Medium 4",
            freeze_panes=(1, 0),
            autofit=True,
            autofilter=True,
            header_format={"bold": True},
            column_formats={
                "price": "##0.00",
                "mass": "##0.000",
            },  # https://support.microsoft.com/en-us/office/number-format-codes-5026bbd6-04bc-48cd-bf33-80f18b4eae68
        )

    return path_excel


def cleanup(settings: Settings):
    root_dir_collation = settings.get_collation_artifacts_dir().absolute()
    root_dir_extraction = settings.get_extraction_artifacts_dir().absolute()

    shutil.rmtree(root_dir_collation)
    shutil.rmtree(root_dir_extraction)
    logger.debug("Deleted collation and extraction dirs")

    root_dir_collation.mkdir()
    root_dir_extraction.mkdir()
    logger.debug("Created clean collation and extraction dirs")


def read_image_as_bytes(image_path: Path) -> bytes:
    if image_path.exists() and image_path.is_file():
        with image_path.open("rb") as image_file:
            image_bytes = image_file.read()

        return image_bytes

    msg = f"Image file not found at {image_path}"
    logger.error(msg)
    raise FileNotFoundError(msg)


def base64_encode_image_bytes(image_bytes: bytes) -> str:
    if isinstance(image_bytes, bytes):
        return base64.b64encode(image_bytes).decode("utf-8")
    raise TypeError(f"{image_bytes=} is not of type bytes but {type(image_bytes)=}.")


def read_and_b64_encode_image(image_path: Path) -> str:
    image_bytes = read_image_as_bytes(image_path)
    base64_enc = base64_encode_image_bytes(image_bytes)
    return base64_enc


def get_image_hash(image_bytes: bytes) -> str:
    hash_object = hashlib.sha256(image_bytes)
    return hash_object.hexdigest()


def get_image_dir_name(
    settings: Settings, image_hash: str, original_file_name: str
) -> Path:
    return (
        settings.get_extraction_artifacts_dir() / f"{original_file_name}-{image_hash}"
    )


def save_image_as_jpg_file(
    image_path: Path, image: bytes | Image.Image, overwrite: bool, mkdir: bool
):
    image_dir = image_path.parent

    if not image_dir.exists() and not mkdir:
        msg = f"{image_dir=} does not exist and {mkdir=}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    elif not image_dir.exists() and mkdir:
        logger.info(f"{image_dir=} is being created")
        image_dir.mkdir()

    if image_path.exists() and not overwrite:
        logger.warning(
            f"File {image_path} already exists and {overwrite=}, skipping creation."
        )
        return

    logger.debug(f"Writing image to {image_path}")
    is_bytes = isinstance(image, bytes)
    is_pil = hasattr(image, "save")

    if is_bytes:
        with image_path.open("wb") as f:
            f.write(image)

    elif is_pil:
        image.save(image_path)  # type: ignore

    else:
        msg = f"Image is neither bytes nor PIL Image, but {type(image)}."
        logger.error(msg)
        raise TypeError(msg)
