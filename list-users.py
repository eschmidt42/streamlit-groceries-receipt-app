"Lists entries of the database for the intended users"

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import bcrypt

from library import fine_logging

logger = logging.getLogger(__name__)
fine_logging.setup_logging(Path("logger-config.json"))


@dataclass
class User:
    username: str
    password: bytes

    @property
    def hashed_password(self) -> bytes:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(self.password, salt)


if __name__ == "__main__":
    logger.info("Starting create-user-db job")

    con = sqlite3.connect("user.db")
    cur = con.cursor()

    logger.info("Creating the user table")
    for x in cur.execute("select username, hashed_password from user"):
        logger.info(f"{x=}")

    logger.info("Done")
