import base64
from pathlib import Path
from unittest.mock import Mock, patch

import instructor
import pytest
from anthropic import Anthropic
from instructor.exceptions import InstructorRetryException

from library import schemas, vlms
from library.settings import (
    AnthropicService,
    Data,
    Keys,
    Logging,
    Services,
    Settings,
)


@pytest.fixture
def mock_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    dummy_dir = tmp_path / "dummy"
    dummy_dir.mkdir()
    monkeypatch.chdir(dummy_dir)

    root_dir = tmp_path / "root"
    root_dir.mkdir()
    extraction_dir = root_dir / "extraction"
    extraction_dir.mkdir()
    collation_dir = root_dir / "collation"
    collation_dir.mkdir()
    log_config = tmp_path / "logging.conf"
    log_config.touch()
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    key_file = key_dir / "anthropic.key"
    key_file.write_text("test-key\n")

    settings = Settings(
        data=Data(
            root_dir=root_dir,
            extraction_subdir="extraction",
            collation_subdir="collation",
            use_user=False,
        ),
        logging=Logging(config_file=log_config),
        services=Services(
            keys=Keys(dir=key_dir),
            anthropic=AnthropicService(
                key_file_name="anthropic.key",
                model="gpt-3",
                max_tokens=1000,
            ),
        ),
    )
    return settings


def test_get_anthropic_client(mock_settings: Settings):
    client = vlms.get_anthropic_client(mock_settings.services)
    assert isinstance(client, instructor.Instructor)


def test_create_anthropic_messages():
    base64_image = base64.b64encode(b"dummy image data").decode("utf-8")
    messages = vlms.create_anthropic_messages(base64_image)

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert len(messages[0]["content"]) == 2
    assert messages[0]["content"][0]["type"] == "text"
    assert messages[0]["content"][1]["type"] == "image"
    assert messages[0]["content"][1]["source"]["data"] == base64_image


def test_make_anthropic_request_fail(mock_settings: Settings):
    # passing of arguments needs to be correct and then the client request fail because of incorrect creds
    base64_image = base64.b64encode(b"dummy image data").decode("utf-8")
    client = vlms.get_anthropic_client(mock_settings.services)
    with pytest.raises(InstructorRetryException):
        _ = vlms.make_anthropic_request(
            base64_image, client, mock_settings.services, max_retries=1
        )
