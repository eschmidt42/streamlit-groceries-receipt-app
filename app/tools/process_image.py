import logging

import polars as pl
import streamlit as st
from PIL.Image import Image
from streamlit_cropper import st_cropper

import library.handler as handler
import library.schemas as schemas
import library.state as sto
import library.utils as utils
import library.vlms as vlms

logger = logging.getLogger(__name__)


def do_upload_image():
    logger.info("Upload image")
    st.markdown("## Upload Image")

    app_state = sto.get_app_state()
    uploaded_file = st.file_uploader(
        "Choose an image file", type=["jpg", "jpeg", "png", "mpo"]
    )

    if uploaded_file is not None:
        # show image
        st.image(uploaded_file, caption="Uploaded Image", use_column_width=True)

        is_done = st.button("Continue", use_container_width=True)

        if is_done:
            settings = sto.get_settings()
            receipt_handler = handler.from_streamlit_uploaded_file(
                uploaded_file, settings
            )

            receipt_handler.save(mkdir=True, overwrite=False)

            app_state.image_handler = receipt_handler

            app_state.state = sto.identify_image_processing_state(receipt_handler)

            sto.set_app_state(app_state)
            st.rerun()


def do_rotate():
    logger.info("Rotate image")
    st.markdown("## Rotate Image")

    app_state = sto.get_app_state()
    if app_state.image_handler is None:
        msg = "Something went wrong, do_rotate expected app_state.image_handler not to be None!"
        raise ValueError(msg)

    image = app_state.image_handler.original_image.copy()

    degrees = st.number_input(
        "Set image rotation 🔁",
        min_value=-360,
        max_value=360,
        value=0,
    )
    image_rotated = image.rotate(360 - degrees, expand=True)

    img_plot = image_rotated.copy()

    img_plot.thumbnail((150, 300))

    cols = st.columns(3)
    with cols[1]:
        st.image(
            img_plot,
            use_column_width="auto",
            caption=f"Rotated by {degrees} degrees (thumbnail of plot shown)",
        )

    is_done = st.button("Continue", use_container_width=True)

    if is_done:
        app_state.image_handler.angle = degrees
        app_state.image_handler.rotated = True
        app_state.image_handler.edited_image = image_rotated
        app_state.state = sto.States.CROP
        app_state.image_handler.save_edited_image(mkdir=False, overwrite=True)

        logger.debug("Done rotating image")
        sto.set_app_state(app_state)

        st.rerun()


def do_crop():
    logger.info("Crop image")
    st.markdown("## Crop Image")

    app_state = sto.get_app_state()
    if app_state.image_handler is None:
        msg = "Something went wrong, do_crop expected app_state.image_handler not to be None!"
        raise ValueError(msg)

    image = app_state.image_handler.edited_image

    image_cropped: Image = st_cropper(
        image.copy(),  # type: ignore
        realtime_update=True,
        box_color="#ecdb93",  # aspect_ratio=None
    )

    img_plot = image_cropped.copy()

    img_plot.thumbnail((150, 300))

    cols = st.columns(3)
    with cols[1]:
        st.image(img_plot, caption="Cropped image (thumbnail of cropped image shown)")

    is_done = st.button("Continue", use_container_width=True)

    if is_done:
        app_state.image_handler.cropped = True
        app_state.image_handler.edited_image = image_cropped
        app_state.state = sto.States.EXTRACT
        app_state.image_handler.save_edited_image(mkdir=False, overwrite=True)
        logger.debug("Done cropping image")
        sto.set_app_state(app_state)

        st.rerun()


def do_extract():
    logger.info("Extract data")
    st.markdown("## Extract data")
    utils.internet_connection()

    app_state = sto.get_app_state()
    if app_state.image_handler is None:
        msg = "Something went wrong, do_extract expected app_state.image_handler not to be None!"
        raise ValueError(msg)

    settings = sto.get_settings()
    client = vlms.get_anthropic_client(settings.services)
    logger.debug("Extracting data from image")

    base64_image = app_state.image_handler.edited_image_base64

    with st.spinner("Extracting"):
        extracted_receipt_info = vlms.make_anthropic_request(
            base64_image, client, settings.services
        )
    st.success("Completed extraction")

    app_state.image_handler.extracted_receipt_info = extracted_receipt_info

    app_state.image_handler.save_receipt_info(overwrite=True)

    logger.debug("Done extracting receipt info from the image")

    app_state.state = sto.States.WRANGLE
    sto.set_app_state(app_state)
    st.rerun()


def do_wrangle():
    logger.info("Wrangling data")
    st.markdown("## Wrangling data")

    app_state = sto.get_app_state()
    if app_state.image_handler is None:
        msg = "Something went wrong, do_wrangle expected app_state.image_handler not to be None!"
        raise ValueError(msg)
    if app_state.image_handler.edited_image is None:
        msg = "Something went wrong, do_wrangle expected app_state.edited_image not to be None!"
        raise ValueError(msg)
    if app_state.image_handler.extracted_receipt_info is None:
        msg = "Something went wrong, do_wrangle expected app_state.image_handler.extracted_receipt_info not to be None!"
        raise ValueError(msg)

    shop = schemas.convert_to_dataframe_shop(
        app_state.image_handler.extracted_receipt_info
    )
    items = schemas.convert_to_dataframe_items(
        app_state.image_handler.extracted_receipt_info
    )

    shop_pd = shop.to_pandas()
    items_pd = items.to_pandas()

    cols = st.columns(2)
    with cols[0]:
        st.write("Image used for info extraction:")
        img_plot = app_state.image_handler.edited_image.copy()
        img_plot.thumbnail((300, 600))
        st.image(img_plot, caption="Rotated & cropped image")
    with cols[1]:
        st.write("Shop info:")
        shop_pd = st.data_editor(shop_pd)

        st.write("Items info:")
        items_pd = st.data_editor(items_pd)

    is_done = st.button("Continue", use_container_width=True)

    if is_done:
        shop_pl = pl.from_pandas(shop_pd)
        items_pl = pl.from_pandas(items_pd)

        app_state.image_handler.extracted_receipt_info = (
            schemas.polars_info_dataframes_to_pydantic(shop_pl, items_pl)
        )
        app_state.image_handler.save_receipt_info(overwrite=False)
        app_state.state = sto.States.DONE

        sto.set_app_state(app_state)
        st.rerun()


def do_done():
    logger.info("Resetting for next image to parse")

    app_state = sto.get_app_state()

    app_state.state = sto.States.UPLOAD
    sto.set_app_state(app_state)
    st.rerun()


app_state = sto.get_app_state()
logger.info(f"Running image processing: {app_state.state=} {app_state.is_logged_in=}")

match app_state.state:
    case sto.States.UPLOAD:
        do_upload_image()
    case sto.States.ROTATE:
        do_rotate()
    case sto.States.CROP:
        do_crop()
    case sto.States.EXTRACT:
        do_extract()
    case sto.States.WRANGLE:
        do_wrangle()
    case sto.States.DONE:
        do_done()
    case _:
        logger.warning(f"Tried to match irrelevant state {app_state.state}")
