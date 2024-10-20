import datetime
import logging
import os
import sqlite3

import bcrypt
import psycopg
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


def get_sqlite_connection_string(db_name: str | None) -> str:
    if db_name is None:
        db_name = "user.db"
    connection_string = f"file:{db_name}?mode=ro"
    return connection_string


def check_sqlite_db_present(db_name: str | None = None) -> bool:
    connection_string = get_sqlite_connection_string(db_name)
    try:
        with sqlite3.connect(connection_string, uri=True) as conn:
            conn.cursor()  # Attempt to create a cursor
        return True
    except sqlite3.Error as e:
        logger.debug(f"Failed to connect to SQLite DB: {e}")
        return False


def get_user_password_in_sqlite_db(username: str, db_name: str | None = None) -> bytes:
    connection_string = get_sqlite_connection_string(db_name)
    con = sqlite3.connect(connection_string, uri=True)
    cur = con.cursor()

    retrieved_hashed_password = b""
    for user, hpw in cur.execute("SELECT username, hashed_password FROM user"):
        if user == username:
            retrieved_hashed_password = hpw

    con.close()

    return retrieved_hashed_password


def get_railway_postgresql_connection_string() -> str | None:
    connection_string = os.getenv("DATABASE_URL")
    if connection_string is None:
        logger.warning("DATABASE_URL environment variable is not set")
    return connection_string


def check_postgresql_db_present() -> bool:
    connection_string = get_railway_postgresql_connection_string()
    if connection_string is None:
        logger.warning("No PostgreSQL connection string available")
        return False
    try:
        with psycopg.connect(conninfo=connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")  # Simple query to test the connection
        return True
    except psycopg.OperationalError as e:
        logger.debug(f"Failed to establish connection to PostgreSQL DB: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error when connecting to PostgreSQL DB: {e}")
        return False


def get_user_password_in_postgresql_db(username: str) -> bytes:
    connection_string = get_railway_postgresql_connection_string()
    if connection_string is None:
        raise ValueError("connection_string is None")

    retrieved_hashed_password = b""
    with psycopg.connect(conninfo=connection_string) as conn:
        # Open a cursor to perform database operations
        with conn.cursor() as cur:
            # Note: contrary to the sqlite db the table here is called app_users because there is already a `user` table in postgres by default...
            for user, hpw in cur.execute(
                "SELECT username, hashed_password FROM app_users"
            ):
                if not isinstance(hpw, bytes) and isinstance(hpw, str):
                    hpw = hpw.encode()
                if user == username:
                    retrieved_hashed_password = hpw

    return retrieved_hashed_password


class User(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    def min_length(cls, v: str) -> str:
        if len(v) == 0:
            raise ValueError("Expected a value of length > 0.")
        return v


# Define the rate limits for each user
RATE_LIMIT_COUNT = 1
RATE_LIMIT_WINDOW = 60  # seconds


class Attempt(BaseModel):
    count: int
    last_time: datetime.datetime


class RateLimiter:
    attempts: dict[str, Attempt]

    def __init__(self):
        self.attempts: dict[str, Attempt] = {}

    def increment(self, username: str):
        now = datetime.datetime.now()

        if username not in self.attempts:
            self.attempts[username] = Attempt(count=1, last_time=now)
            return

        attempts = self.attempts[username]

        dt = now - attempts.last_time
        t_threshold = datetime.timedelta(seconds=RATE_LIMIT_WINDOW)

        if dt > t_threshold:
            attempts.count = 1
            attempts.last_time = now
        else:
            attempts.count += 1

        self.attempts[username] = attempts

    def check_limit_exceeded(self, username: str) -> bool:
        self.increment(username)

        attempts = self.attempts[username]
        if attempts.count > RATE_LIMIT_COUNT:
            return True  # Rate limit exceeded
        return False


rate_limiter = RateLimiter()


def check_is_legit_user(user: User) -> bool:
    if rate_limiter.check_limit_exceeded(user.username):
        return False

    if check_sqlite_db_present():
        logger.debug("Found a sqlite db")
        retrieved_hashed_password = get_user_password_in_sqlite_db(user.username)
    elif check_postgresql_db_present():
        logger.debug("Found a postgresql db")
        retrieved_hashed_password = get_user_password_in_postgresql_db(user.username)
    else:
        logger.debug("Found no db")
        return False

    if retrieved_hashed_password == b"" or retrieved_hashed_password is None:
        return False

    bytes_password = user.password.encode()

    return bcrypt.checkpw(bytes_password, retrieved_hashed_password)
