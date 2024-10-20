import logging
from pathlib import Path

import polars as pl
import streamlit as st

import library.state as sto
import library.utils as utils
from library import fine_logging


def collect(
    settings: sto.Settings, shop_info_files: list[Path], items_info_files: list[Path]
):
    start_collection = st.button("Run collection", use_container_width=True)

    if start_collection and len(shop_info_files) > 0 and len(items_info_files) > 0:
        utils.collect(settings)
        st.info("Done collecting")

    elif start_collection and len(shop_info_files) == 0 and len(items_info_files) == 0:
        st.error(
            "No shop and item files present, cannot collect. Parse some images first."
        )


def compress(do_create_zipfile: bool, settings: sto.Settings) -> bytes:
    root_dir_extraction = settings.get_extraction_artifacts_dir().absolute()
    compiled_shop_info_path, compiled_items_info_path = utils.get_compiled_paths(
        settings
    )

    if do_create_zipfile and (
        compiled_shop_info_path.exists() or compiled_items_info_path.exists()
    ):
        path_archive = utils.create_zipfile(root_dir_extraction)
        logger.debug(f"Loading {path_archive=} as bytes")
        with path_archive.open("rb") as f:
            archive_bytes = f.read()

        st.info("Zip file extractions.zip created")

    elif do_create_zipfile:
        st.error(
            "Could not create zip file extractions.zip because no shop or items info present."
        )
        archive_bytes = b""

    else:
        archive_bytes = b""

    return archive_bytes


def make_excel(settings: sto.Settings) -> bytes:
    path_excel = utils.write_excel_workbook(settings)

    with path_excel.open("rb") as f:
        excel_bytes = f.read()

    return excel_bytes


#### Setup

logger = logging.getLogger(__name__)


title = "Collect Data"
st.title(title)

settings = sto.get_settings()
fine_logging.setup_logging(settings.get_logger_config_path())

compiled_shop_info_path, compiled_items_info_path = utils.get_compiled_paths(settings)
disable_shop_download = not compiled_shop_info_path.exists()
disable_items_download = not compiled_items_info_path.exists()

shop_info_files, items_info_files = utils.check_available_extraction_dirs(settings)
msg = f"""Detected files:

* shop info: {len(shop_info_files):_}
* items info: {len(items_info_files):_}"""
st.markdown(msg)

##### Collect

collect(settings, shop_info_files, items_info_files)

##### Create zip

create_zipfile = st.button("Create zip-file", use_container_width=True)
archive_bytes = compress(create_zipfile, settings)

##### Download: zip

st.download_button(
    label="Download all info as extractions.zip",
    data=archive_bytes,
    file_name="extractions.zip",
    mime="application/octet-stream",
    disabled=disable_shop_download and disable_items_download,
    use_container_width=True,
)

##### Download: csvs

if compiled_shop_info_path.exists():
    shop_csv = pl.read_parquet(compiled_shop_info_path).write_csv(separator=";")
else:
    shop_csv = ""

if compiled_shop_info_path.exists():
    items_csv = pl.read_parquet(compiled_items_info_path).write_csv(separator=";")
else:
    items_csv = ""

st.download_button(
    label="Download shop info as CSV",
    data=shop_csv,
    file_name="shop.csv",
    mime="text/csv",
    disabled=disable_shop_download,
    use_container_width=True,
)

st.download_button(
    label="Download item info as CSV",
    data=items_csv,
    file_name="items.csv",
    mime="text/csv",
    disabled=disable_items_download,
    use_container_width=True,
)

##### Download: excel

if compiled_items_info_path.exists() and compiled_shop_info_path.exists():
    excel_bytes = make_excel(settings)
else:
    excel_bytes = b""

st.download_button(
    label="Download all info as groceries-data.xlsx",
    data=excel_bytes,
    file_name="groceries-data.xlsx",
    mime="application/octet-stream",
    disabled=disable_shop_download or disable_items_download,
    use_container_width=True,
)

##### Cleanup

delete_history = st.button("Delete history", use_container_width=True)

if delete_history:
    utils.cleanup(settings)
    st.info("Done deleting history")
