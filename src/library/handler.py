import logging
from pathlib import Path

import polars as pl
import streamlit.runtime.uploaded_file_manager as st_file
from PIL import Image
from pydantic import BaseModel

import library.schemas as schemas
import library.utils as utils
from library.settings import Settings, StoredFileNames

logger = logging.getLogger(__name__)


class ImageHandler(BaseModel):
    # type hinting https://stackoverflow.com/questions/33533148/how-do-i-type-hint-a-method-with-the-type-of-the-enclosing-class
    target_directory: Path
    original_image: Image.Image
    original_image_bytes: bytes
    original_file_name: str
    target_file_names: StoredFileNames = StoredFileNames()
    extracted_receipt_info: schemas.Receipt | None = None
    cropped: bool = False
    rotated: bool = False
    angle: float = 0.0
    edited_image: Image.Image | None = None

    class Config:
        arbitrary_types_allowed = True

    @property
    def original_image_base64(self) -> str:
        return utils.base64_encode_image_bytes(self.original_image_bytes)

    @property
    def edited_image_base64(self) -> str:
        edited_image_path = self.get_target_file_path("edited_image")
        return utils.read_and_b64_encode_image(edited_image_path)

    def get_target_file_path(self, name: str) -> Path:
        is_missing = not hasattr(self.target_file_names, name)
        if is_missing:
            msg = f"Failed to find target path for {name=}, known file names: {self.target_file_names.model_dump_json()}"
            logger.error(msg)
            raise ValueError(msg)

        target_file_path = self.target_directory / getattr(self.target_file_names, name)
        return target_file_path

    def save(self, mkdir: bool, overwrite: bool):
        self.save_images(mkdir, overwrite)

        if self.extracted_receipt_info:
            self.save_receipt_info(overwrite)

    def save_images(self, mkdir: bool, overwrite: bool):
        self.save_original_image(mkdir, overwrite)
        self.save_edited_image(mkdir, overwrite)

    def save_original_image(self, mkdir: bool, overwrite: bool):
        image_path = self.get_target_file_path("original_image")
        save_image(self.original_image, "original_image", image_path, overwrite, mkdir)

    def save_edited_image(self, mkdir: bool, overwrite: bool):
        image_path = self.get_target_file_path("edited_image")
        if self.edited_image is None:
            logger.error(f"Could not save edited_image because {self.edited_image=}")
            return
        save_image(self.edited_image, "edited_image", image_path, overwrite, mkdir)

    def save_receipt_info(self, overwrite: bool):
        logger.debug("Saving receipt info")
        self.save_shop_info(overwrite)
        self.save_items_info(overwrite)

    def save_shop_info(self, overwrite: bool):
        logger.debug("Saving shop info")
        if self.extracted_receipt_info is None:
            logger.error(
                f"Could not save shop_info because {self.extracted_receipt_info=}"
            )
            return
        shop = schemas.convert_to_dataframe_shop(self.extracted_receipt_info)
        shop = shop.with_columns(
            pl.lit(None).alias("time")
        )  # preventing: PanicException: not yet implemented: Writing Time64(Nanosecond) to JSON
        json_path = self.get_target_file_path("shop_info_json")
        parquet_path = self.get_target_file_path("shop_info_parquet")

        save_dataframe(shop, "shop", json_path, parquet_path, overwrite)

    def save_items_info(self, overwrite: bool):
        logger.debug("Saving items info")
        if self.extracted_receipt_info is None:
            logger.error(
                f"Could not save items_info because {self.extracted_receipt_info=}"
            )
            return
        items = schemas.convert_to_dataframe_items(self.extracted_receipt_info)
        json_path = self.get_target_file_path("items_info_json")
        parquet_path = self.get_target_file_path("items_info_parquet")

        save_dataframe(items, "items", json_path, parquet_path, overwrite)


def save_dataframe(
    df: pl.DataFrame, name: str, json_path: Path, parquet_path: Path, overwrite: bool
):
    logger.debug("Writing dataframe to disk")

    is_missing = not json_path.exists()
    if is_missing or overwrite:
        logger.debug(f"Writing {name} info to {json_path}")
        df.write_json(json_path)

    is_missing = not parquet_path.exists()
    if is_missing or overwrite:
        logger.debug(f"Writing {name} info to {parquet_path}")
        df.write_parquet(parquet_path)

    logger.debug("Done writing")


def save_image(
    image: Image.Image, name: str, image_path: Path, overwrite: bool, mkdir: bool
):
    if image is not None:
        logger.debug(f"Saving {name} at {image_path}")
        utils.save_image_as_jpg_file(
            image_path, image, overwrite=overwrite, mkdir=mkdir
        )
    else:
        logger.debug(f"Passed `image` was None. Doing nothing for {name}.")


def from_source_image_path(image_path: Path, settings: Settings) -> ImageHandler:
    logger.debug("Creating ImageHandler from an image path")
    logger.debug(f"Reading image from {image_path=}")
    image = Image.open(image_path)
    with image_path.open("rb") as f:
        image_bytes = f.read()

    image_hash = utils.get_image_hash(image_bytes)
    target_directory = utils.get_image_dir_name(settings, image_hash, image_path.name)

    logger.debug("Creating instance of ImageHandler")
    return ImageHandler(
        target_directory=target_directory,
        original_image=image,
        original_image_bytes=image_bytes,
        original_file_name=image_path.name,
    )


def from_target_directory(target_directory: Path) -> ImageHandler:
    logger.debug("Creating ImageHandler from a target directory")
    logger.debug(f"Reading data from {target_directory=}")

    file_names = StoredFileNames()

    logger.debug("Reading the original image")

    # original image
    image_path = target_directory / file_names.original_image
    image = Image.open(image_path)
    with image_path.open("rb") as f:
        image_bytes = f.read()

    logger.debug("Creating instance of ImageHandler")
    handler = ImageHandler(
        target_directory=target_directory,
        original_image=image,
        original_image_bytes=image_bytes,
        original_file_name=image_path.name,
        target_file_names=file_names,
    )

    # edited image
    edited_image_path = handler.get_target_file_path("edited_image")
    if edited_image_path.exists():
        logger.debug("Reading the edited image")
        handler.edited_image = Image.open(edited_image_path)

    # extracted data
    shop_df, items_df = None, None
    shop_path = handler.get_target_file_path("shop_info_parquet")
    if shop_path.exists():
        logger.debug(f"Reading shop info: {shop_path}")
        shop_df = pl.read_parquet(shop_path)

    items_path = handler.get_target_file_path("items_info_parquet")
    if items_path.exists():
        logger.debug(f"Reading items info: {items_path}")
        items_df = pl.read_parquet(items_path)

    if shop_df is not None and items_df is not None:
        logger.debug("Reconstructing the receipt data")
        handler.extracted_receipt_info = schemas.polars_info_dataframes_to_pydantic(
            shop_df, items_df
        )
    else:
        logger.debug(
            f"Did not reconstruct the receipt data because: {shop_path.exists()=} / {items_path.exists()=}"
        )

    return handler


def from_streamlit_uploaded_file(
    uploaded_file: st_file.UploadedFile, settings: Settings
) -> ImageHandler:
    logger.debug("Creating handler from a streamlit UploadedFile object")

    # derive directory from image
    image_bytes = uploaded_file.getvalue()
    image_hash = utils.get_image_hash(image_bytes)
    original_file_name = uploaded_file.name

    target_directory = utils.get_image_dir_name(
        settings, image_hash, original_file_name
    )

    if target_directory.exists():
        logger.debug(
            "Target directory already exists for the passed file. Loading pre-existing directory."
        )
        return from_target_directory(target_directory)

    original_image = Image.open(uploaded_file)

    logger.debug("Creating handler for new file.")

    return ImageHandler(
        target_directory=target_directory,
        original_image=original_image,
        original_image_bytes=image_bytes,
        original_file_name=original_file_name,
    )
