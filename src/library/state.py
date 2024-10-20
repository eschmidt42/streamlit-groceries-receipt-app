import logging
from enum import Enum

import streamlit as st
from pydantic import BaseModel

import library.fine_logging as fine_logging
import library.handler as handler
from library.settings import Settings

logger = logging.getLogger(__name__)

VAR_STATE = "app_state"
VAR_SETTINGS = "settings"


class States(str, Enum):
    LOGIN = "login"
    UPLOAD = "upload"
    ROTATE = "rotate"
    CROP = "crop"
    EXTRACT = "extract"
    WRANGLE = "wrangle"
    SAVE = "save"
    DONE = "done"


class AppState(BaseModel):
    state: States = States.LOGIN
    is_logged_in: bool = False
    image_handler: handler.ImageHandler | None = None
    username: str | None = None


def set_app_state(app_state: AppState):
    st.session_state[VAR_STATE] = app_state


def get_app_state() -> AppState:
    if VAR_STATE in st.session_state:
        return st.session_state[VAR_STATE]
    else:
        app_state = AppState()
        set_app_state(app_state)
        return app_state


def init_settings(username: str):
    if VAR_SETTINGS not in st.session_state:
        logger.info("Initializing settings")
        settings = Settings(**{"data": {"username": username}})  # type: ignore
        st.session_state[VAR_SETTINGS] = settings
        fine_logging.setup_logging(settings.get_logger_config_path())


def set_settings(settings: Settings):
    st.session_state[VAR_SETTINGS] = settings


def get_settings() -> Settings:
    try:
        return st.session_state[VAR_SETTINGS]
    except KeyError as e:
        logger.error("Failed to retrive non-existing settings.")
        raise e


def check_is_logged_in() -> bool:
    app_state = get_app_state()
    return app_state.is_logged_in


def set_logging_in_state_if_not_logged_in():
    if check_is_logged_in():
        return

    app_state = get_app_state()
    app_state.state = States.LOGIN
    set_app_state(app_state)


def identify_image_processing_state(handler: handler.ImageHandler) -> States:
    if handler.extracted_receipt_info is not None:
        logger.debug(
            f"Found extracted receipt data in handler, setting state to {States.WRANGLE}"
        )
        return States.WRANGLE

    logger.debug(f"Setting state to {States.ROTATE}")
    return States.ROTATE
