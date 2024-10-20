import typing as T
from unittest.mock import MagicMock, patch

import bcrypt
import psycopg
import pytest

from library.user_db import (
    check_postgresql_db_present,
    get_railway_postgresql_connection_string,
    get_user_password_in_postgresql_db,
)


# Tests for get_railway_postgresql_connection_string()
def test_get_railway_postgresql_connection_string_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert (
        get_railway_postgresql_connection_string() == "postgresql://user:pass@host/db"
    )


def test_get_railway_postgresql_connection_string_not_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_railway_postgresql_connection_string() is None


MockType = T.Generator[MagicMock, None, None]


# Tests for check_postgresql_db_present()
@pytest.fixture
def mock_psycopg_connect():
    with patch("psycopg.connect") as mock_connect:
        yield mock_connect


def test_check_postgresql_db_present_success(
    monkeypatch: pytest.MonkeyPatch, mock_psycopg_connect
):
    mock_psycopg_connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = MagicMock()
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert check_postgresql_db_present() is True


def test_check_postgresql_db_present_no_connection_string(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert check_postgresql_db_present() is False


def test_check_postgresql_db_present_connection_error(
    monkeypatch: pytest.MonkeyPatch, mock_psycopg_connect
):
    mock_psycopg_connect.side_effect = psycopg.OperationalError
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert check_postgresql_db_present() is False


def test_check_postgresql_db_present_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, mock_psycopg_connect
):
    mock_psycopg_connect.side_effect = Exception
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    assert check_postgresql_db_present() is False


# Test data
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpassword"
TEST_HASHED_PASSWORD = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt())


@pytest.fixture
def mock_psycopg_connect2():
    with patch("library.user_db.psycopg.connect") as mock_connect:
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = [
            (TEST_USERNAME, TEST_HASHED_PASSWORD),
            ("otheruser", b"otherhash"),
        ]
        mock_connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        yield mock_connect


def test_get_user_password_in_postgresql_db(
    mock_psycopg_connect2, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "something")
    result = get_user_password_in_postgresql_db(TEST_USERNAME)
    assert result == TEST_HASHED_PASSWORD


def test_get_user_password_in_postgresql_db_user_not_found(
    mock_psycopg_connect2, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DATABASE_URL", "something")
    result = get_user_password_in_postgresql_db("nonexistentuser")
    assert result == b""


def test_get_user_password_in_postgresql_db_connection_string_none():
    with pytest.raises(ValueError, match="connection_string is None"):
        get_user_password_in_postgresql_db(TEST_USERNAME)
