"Interactively creates the database for the intended users and their hashed passwords"

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

    res = cur.execute("SELECT name FROM sqlite_master")

    if res.fetchone() is not None:
        logger.info("Found pre-existing user table, dropping it.")
        cur.execute("DROP TABLE user")
        con.commit()

    logger.info("Creating the user table")
    cur.execute("CREATE TABLE user(username,hashed_password)")

    password_og = input("OG's password: ")

    users = [
        User(username="og", password=password_og.encode()),
    ]

    logger.info(f"Writing {len(users)} to the user table.")
    statement = "INSERT INTO user VALUES(?, ?)"
    cur.executemany(statement, [(u.username, u.hashed_password) for u in users])
    con.commit()

    logger.info("Done")
