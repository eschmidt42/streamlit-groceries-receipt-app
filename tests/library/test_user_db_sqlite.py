import sqlite3
from dataclasses import dataclass
from pathlib import Path

import bcrypt
import pytest

from library.user_db import (
    check_sqlite_db_present,
    get_user_password_in_sqlite_db,
)


@dataclass
class User:
    username: str
    password: bytes

    @property
    def hashed_password(self) -> bytes:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(self.password, salt)


@pytest.fixture()
def temp_sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_dir = tmp_path / "sqlite"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create a simple table
    cursor.execute("""CREATE TABLE user
                      (username TEXT PRIMARY KEY, hashed_password TEXT)""")
    users = [
        User(username="user1", password=b"wup"),
        User(username="user2", password=b"wuppety"),
    ]

    statement = "INSERT INTO user VALUES(?, ?)"
    cursor.executemany(statement, [(u.username, u.hashed_password) for u in users])

    conn.commit()
    conn.close()

    # Change the working directory to the temporary directory
    monkeypatch.chdir(db_dir)
    return db_path


def test_check_sqlite_db_present(temp_sqlite_db: Path):
    # Test when the database is present
    assert check_sqlite_db_present(temp_sqlite_db.name) is True


def test_check_sqlite_db_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_dir = tmp_path / "missing-sqlite"
    db_dir.mkdir(exist_ok=True)
    monkeypatch.chdir(db_dir)
    # Test when the database is not present
    assert check_sqlite_db_present() is False


@pytest.mark.parametrize(
    "user,password",
    [
        ("user1", b"wup"),
        ("user2", b"wuppety"),
        ("user3", b""),
    ],
)
def test_get_user_password_in_sqlite_db(
    monkeypatch: pytest.MonkeyPatch, temp_sqlite_db: Path, user: str, password: bytes
):
    monkeypatch.chdir(temp_sqlite_db.parent)
    assert temp_sqlite_db.exists()
    retrieved_password = get_user_password_in_sqlite_db(
        user, db_name=temp_sqlite_db.name
    )
    try:
        assert bcrypt.checkpw(password, retrieved_password)
    except ValueError as e:
        if password != b"":
            raise e
