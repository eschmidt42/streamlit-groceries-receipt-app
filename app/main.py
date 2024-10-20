"""Entry point for the app.

App states:

* login
* upload image
* rotate image
* crop image
* extract data from image
* wrangle data
* save results (with lifetime) / next image
* collate / export stored data (zip archive, archive, xlsxs)
"""

import logging

import streamlit as st
from pydantic import ValidationError

import library.state as sto
from library.user_db import User, check_is_legit_user

logger = logging.getLogger(__name__)

st.set_page_config(layout="centered")


def do_login():
    logger.info("Login step")
    st.markdown("## Login")

    with st.form("login"):
        username = st.text_input("username")
        password = st.text_input("password", type="password")

        submit = st.form_submit_button("Submit", use_container_width=True)

        if submit:
            try:
                user = User(username=username, password=password)
            except ValidationError as e:
                st.error("Login failed")
                logger.info("Login failed")
                user = None

            sto.init_settings(username)
            if user is not None:
                if check_is_legit_user(user):
                    st.info("Successfully logged in")
                    logger.info("Login succeeded")

                    app_state = sto.get_app_state()
                    app_state.is_logged_in = True
                    app_state.state = sto.States.UPLOAD
                    app_state.username = user.username
                    sto.set_app_state(app_state)

                    st.rerun()
                else:
                    st.error("Login failed")
                    logger.info("Login failed")


def do_logout():
    logger.info("Logout step")
    st.markdown("## Logout")

    if st.button("Log out", use_container_width=True):
        st.info("Logging out")
        app_state = sto.get_app_state()
        app_state.is_logged_in = False
        app_state.state = sto.States.LOGIN
        sto.set_app_state(app_state)

        st.rerun()


def main():
    # https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation

    sto.set_logging_in_state_if_not_logged_in()
    app_state = sto.get_app_state()

    login_page = st.Page(do_login, title="Log in", icon=":material/login:")
    logout_page = st.Page(do_logout, title="Log out", icon=":material/logout:")
    process_page = st.Page(
        "tools/process_image.py",
        title="Process image",
        icon=":material/search:",
        default=True,
    )
    collect_page = st.Page(
        "tools/collect_data.py", title="Collect data", icon=":material/history:"
    )

    if app_state.is_logged_in:
        pg = st.navigation(
            {
                "Tools": [process_page, collect_page],
                "Accounts": [logout_page],
            }
        )
    else:
        pg = st.navigation([login_page])

    pg.run()


if __name__ == "__main__":
    main()
