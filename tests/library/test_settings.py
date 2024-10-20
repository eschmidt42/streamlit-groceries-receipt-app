from pathlib import Path

import pytest

from library.settings import (
    AnthropicService,
    Data,
    Keys,
    Logging,
    Services,
    Settings,
    sanity_check_path_parent,
)


# Test sanity_check_path function
def test_sanity_check_path_parent(tmp_path: Path):
    valid_path = tmp_path / "valid" / "wup"
    valid_path.mkdir(parents=True)
    sanity_check_path_parent(valid_path)  # Should not raise an exception

    invalid_path = tmp_path / "invalid" / "wubba"
    with pytest.raises(ValueError):
        sanity_check_path_parent(invalid_path)


# ============== Test the class Data ==============
def test_data_error_missing_dir(tmp_path: Path):
    root_dir = tmp_path / "root"

    with pytest.raises(FileExistsError):
        _ = Data(
            root_dir=root_dir,
            extraction_subdir="extraction",
            collation_subdir="collation",
            use_user=False,
        )


def test_data_without_user(tmp_path: Path):
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    extraction_dir = root_dir / "extraction"
    extraction_dir.mkdir()
    collation_dir = root_dir / "collation"
    collation_dir.mkdir()

    data = Data(
        root_dir=root_dir,
        extraction_subdir="extraction",
        collation_subdir="collation",
        use_user=False,
    )

    assert data.get_extraction_dir() == extraction_dir
    assert data.get_collation_dir() == collation_dir


def test_data_with_user_missing_dir(tmp_path: Path):
    root_dir = tmp_path / "root"

    root_dir.mkdir()
    extraction_dir = root_dir / "extraction"
    extraction_dir.mkdir(parents=True)
    collation_dir = root_dir / "collation"
    collation_dir.mkdir(parents=True)

    with pytest.raises(ValueError):
        _ = Data(
            root_dir=root_dir,
            extraction_subdir="extraction",
            collation_subdir="collation",
            use_user=True,
            username=None,
        )


def test_data_with_user(tmp_path: Path):
    root_dir = tmp_path / "root"
    username = "testuser"

    root_dir.mkdir()
    extraction_dir = root_dir / username / "extraction"
    extraction_dir.mkdir(parents=True)
    collation_dir = root_dir / username / "collation"
    collation_dir.mkdir(parents=True)

    data_with_user = Data(
        root_dir=root_dir,
        extraction_subdir="extraction",
        collation_subdir="collation",
        use_user=True,
        username=username,
    )

    assert data_with_user.get_extraction_dir() == root_dir / username / "extraction"
    assert data_with_user.get_collation_dir() == root_dir / username / "collation"


# ============== Test the class Logging ==============
def test_logging_config_missing(tmp_path: Path):
    with pytest.raises(ValueError):
        Logging(config_file=tmp_path / "nonexistent.conf")


def test_logging(tmp_path: Path) -> None:
    config_file = tmp_path / "logging.conf"
    config_file.touch()

    logging = Logging(config_file=config_file)
    assert logging.config_file == config_file


# ============== Test the class Keys ==============
def test_keys_dir_missing():
    tmp_path = Path("/dummy/does/not/exist")
    with pytest.raises(ValueError):
        _ = Keys(dir=tmp_path)


def test_keys_dir(tmp_path: Path):
    keys = Keys(dir=tmp_path)
    assert keys.dir == tmp_path


# ============== Test the class AnthropicService ==============
def test_anthropic_service():
    service = AnthropicService(
        key_file_name="anthropic.key",
        model="gpt-3",
        max_tokens=1000,
    )
    assert service.key_file_name == "anthropic.key"
    assert service.model == "gpt-3"
    assert service.max_tokens == 1000


# ============== Test the class Services ==============
def test_services(tmp_path: Path):
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    key_file = key_dir / "anthropic.key"
    key_file.write_text("test-key\n")

    services = Services(
        keys=Keys(dir=key_dir),
        anthropic=AnthropicService(
            key_file_name="anthropic.key",
            model="gpt-3",
            max_tokens=1000,
        ),
    )

    assert services.get_anthropic_key() == "test-key"


def test_services_missing_key_file(tmp_path: Path):
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    with pytest.raises(FileExistsError):
        Services(
            keys=Keys(dir=key_dir),
            anthropic=AnthropicService(
                key_file_name="nonexistent.key",
                model="gpt-3",
                max_tokens=1000,
            ),
        )


# ============== Test the class Settings ==============
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert settings.get_data_root_dir() == root_dir
    assert settings.get_extraction_artifacts_dir() == extraction_dir
    assert settings.get_collation_artifacts_dir() == collation_dir
    assert settings.get_logger_config_path() == log_config


@pytest.fixture
def env_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    # Set environment variables using monkeypatch
    monkeypatch.setenv("DATA__ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DATA__EXTRACTION_SUBDIR", "extraction")
    monkeypatch.setenv("DATA__COLLATION_SUBDIR", "collation")
    monkeypatch.setenv("DATA__USE_USER", "false")
    monkeypatch.setenv("LOGGING__CONFIG_FILE", str(log_config))
    monkeypatch.setenv("SERVICES__KEYS__DIR", str(key_dir))
    monkeypatch.setenv("SERVICES__ANTHROPIC__KEY_FILE_NAME", "anthropic.key")
    monkeypatch.setenv("SERVICES__ANTHROPIC__MODEL", "gpt-3")
    monkeypatch.setenv("SERVICES__ANTHROPIC__MAX_TOKENS", "1000")

    return {
        "root_dir": root_dir,
        "log_config": log_config,
        "key_dir": key_dir,
    }


def test_settings_from_env(env_setup):
    settings = Settings()  # type: ignore

    assert str(settings.data.root_dir) == str(env_setup["root_dir"])
    assert settings.data.extraction_subdir == "extraction"
    assert settings.data.collation_subdir == "collation"
    assert settings.data.use_user is False
    assert str(settings.logging.config_file) == str(env_setup["log_config"])
    assert str(settings.services.keys.dir) == str(env_setup["key_dir"])
    assert settings.services.anthropic.key_file_name == "anthropic.key"
    assert settings.services.anthropic.model == "gpt-3"
    assert settings.services.anthropic.max_tokens == 1000

    # Additional checks
    assert settings.get_extraction_artifacts_dir().exists()
    assert settings.get_collation_artifacts_dir().exists()
    assert settings.get_logger_config_path().exists()
    assert (
        Path(settings.services.keys.dir) / settings.services.anthropic.key_file_name
    ).exists()
