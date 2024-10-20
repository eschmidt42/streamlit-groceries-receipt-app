from datetime import datetime, timedelta
from unittest.mock import patch

import bcrypt
import pytest

import library.user_db as user_db
from library.user_db import (
    RATE_LIMIT_COUNT,
    RATE_LIMIT_WINDOW,
    Attempt,
    RateLimiter,
    User,
    check_is_legit_user,
)

# Test data
TEST_USERNAME = "testuser"
TEST_PASSWORD = "testpassword"
TEST_HASHED_PASSWORD = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt())
TEST_HASHED_PASSWORD2 = bcrypt.hashpw("wuppety".encode(), bcrypt.gensalt())


@pytest.mark.parametrize(
    "postgres_present, sqlite_present, username, password, expected_result",
    [
        (True, False, TEST_USERNAME, TEST_PASSWORD, True),
        (False, True, TEST_USERNAME, TEST_PASSWORD, True),
        (True, False, TEST_USERNAME, "-.-", False),
        (False, True, TEST_USERNAME, "-.-", False),
        (True, False, "-.-", TEST_PASSWORD, False),
        (False, True, "-.-", TEST_PASSWORD, False),
    ],
)
def test_check_is_legit_user(
    postgres_present: bool,
    sqlite_present: bool,
    username: str,
    password: str,
    expected_result: bool,
):
    if username in user_db.rate_limiter.attempts:
        user_db.rate_limiter.attempts[username].count = 0

    db_pw = TEST_HASHED_PASSWORD if username == TEST_USERNAME else TEST_HASHED_PASSWORD2
    with patch(
        "library.user_db.check_postgresql_db_present",
        return_value=postgres_present,
    ), patch(
        "library.user_db.check_sqlite_db_present",
        return_value=sqlite_present,
    ), patch(
        "library.user_db.get_user_password_in_postgresql_db",
        return_value=db_pw,
    ), patch(
        "library.user_db.get_user_password_in_sqlite_db",
        return_value=db_pw,
    ):
        user = User(username=username, password=password)
        result = check_is_legit_user(user)
        assert result == expected_result


def test_check_is_legit_user_no_db():
    with patch(
        "library.user_db.check_postgresql_db_present",
        return_value=False,
    ), patch(
        "library.user_db.check_sqlite_db_present",
        return_value=False,
    ):
        user = User(username=TEST_USERNAME, password=TEST_PASSWORD)
        result = check_is_legit_user(user)
        assert result == False


# ========== Rate limiting ==========


@pytest.fixture
def rate_limiter():
    return RateLimiter()


def test_initial_attempt(rate_limiter: RateLimiter):
    username = "test_user"
    start = datetime.now()
    rate_limiter.increment(username)
    attempt = rate_limiter.attempts[username]
    assert attempt.count == 1
    assert attempt.last_time >= start


def test_increment_rate_limit(rate_limiter: RateLimiter):
    username = "test_user"
    start = datetime.now()
    for i in range(RATE_LIMIT_COUNT):
        rate_limiter.increment(username)
        assert rate_limiter.attempts[username].count == i + 1

    assert rate_limiter.attempts[username].count == RATE_LIMIT_COUNT
    assert rate_limiter.attempts[username].last_time > start


def test_rate_limit_not_exceeded(rate_limiter: RateLimiter):
    username = "test_user"

    now = datetime.now()
    rate_limiter.attempts[username] = Attempt(count=0, last_time=now)
    assert not rate_limiter.check_limit_exceeded(username)

    now = datetime.now() - timedelta(seconds=RATE_LIMIT_WINDOW + 1)
    rate_limiter.attempts[username] = Attempt(count=RATE_LIMIT_COUNT, last_time=now)
    assert not rate_limiter.check_limit_exceeded(username)


def test_rate_limit_exceeded(rate_limiter: RateLimiter):
    username = "test_user"
    now = datetime.now()
    previous_time = now - timedelta(seconds=RATE_LIMIT_WINDOW - 1)

    rate_limiter.attempts[username] = Attempt(
        count=RATE_LIMIT_COUNT, last_time=previous_time
    )

    assert rate_limiter.check_limit_exceeded(username)
