import typing as T
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


def sanity_check_path(path: Path):
    path = path.resolve().absolute()
    if not path.exists() and path is not None:
        msg = f"Path {path} does not exist"
        raise ValueError(msg)


def sanity_check_path_parent(path: str | Path):
    if isinstance(path, str):
        _path: Path = Path(path)  # type: ignore
    elif isinstance(path, Path):
        _path = path
    else:
        raise ValueError(f"`path` needs to be of type str or Path, got {type(path)}")
    _path = _path.resolve().absolute()
    if not _path.parent.exists() and _path is not None:
        msg = f"Path {_path} does not exist"
        raise ValueError(msg)


class Data(BaseModel):
    root_dir: Path
    legacy_root_dir: Path | None = None
    extraction_subdir: str
    collation_subdir: str
    use_user: bool
    username: str | None = None

    @field_validator("root_dir")  # "legacy_root_dir"
    @classmethod
    def path_valid(cls, path_str: str) -> str:
        sanity_check_path_parent(path_str)
        return path_str

    def _root_dir(self) -> Path:
        if self.username and self.use_user:
            return self.root_dir / self.username
        return self.root_dir

    def get_extraction_dir(self) -> Path:
        return self._root_dir() / self.extraction_subdir

    def get_collation_dir(self) -> Path:
        return self._root_dir() / self.collation_subdir

    @model_validator(mode="after")
    def check_subdirs_exist(self) -> T.Self:
        extraction_dir = self.get_extraction_dir()
        collation_dir = self.get_collation_dir()

        if not extraction_dir.exists():
            msg = f"The directory to store extracted data at does not exist: {extraction_dir=}"
            raise FileExistsError(msg)

        if not collation_dir.exists():
            msg = f"The directory to store collated data at does not exist: {collation_dir=}"
            raise FileExistsError(msg)

        return self

    @model_validator(mode="after")
    def check_username_provided_if_needed(self) -> T.Self:
        if self.use_user and self.username is None:
            raise ValueError(
                "Exepected username to be provided when use_user Flag is True."
            )

        return self


class Logging(BaseModel):
    config_file: Path

    @field_validator("config_file")
    @classmethod
    def path_valid(cls, path_str: str) -> str:
        sanity_check_path(Path(path_str))
        return path_str


class Keys(BaseModel):
    dir: Path

    @field_validator("dir")
    @classmethod
    def path_valid(cls, path_str: str) -> str:
        sanity_check_path(Path(path_str))
        return path_str


class AnthropicService(BaseModel):
    key_file_name: str
    model: str
    max_tokens: int
    key: str | None = None


class Services(BaseModel):
    keys: Keys
    anthropic: AnthropicService

    def get_anthropic_key(self) -> str:
        if self.anthropic.key:
            return self.anthropic.key
        path = self.keys.dir / self.anthropic.key_file_name
        with path.open("r") as f:
            key = f.readline()
        key = key.replace("\n", "")
        return key

    @model_validator(mode="after")
    def check_keys_exist(self) -> T.Self:
        if self.anthropic.key:
            return self

        anthropic_key_file_name = self.anthropic.key_file_name
        path = self.keys.dir / anthropic_key_file_name

        if not path.exists():
            msg = f"The anthropic key file was not found at: {anthropic_key_file_name}"
            raise FileExistsError(msg)

        return self


class Settings(BaseSettings):
    # https://docs.pydantic.dev/latest/concepts/pydantic_settings/#other-settings-source
    data: Data
    logging: Logging
    services: Services

    model_config = SettingsConfigDict(
        toml_file=[
            "./app-config.toml",
        ],
        env_nested_delimiter="__",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: T.Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> T.Tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, TomlConfigSettingsSource(settings_cls), env_settings)

    def get_data_root_dir(self) -> Path:
        root_dir = Path(self.data._root_dir()).resolve().absolute()
        return root_dir

    def get_legacy_data_root_dir(self) -> T.Optional[Path]:
        if self.data.legacy_root_dir:
            return Path(self.data.legacy_root_dir).resolve().absolute()
        return None

    def get_extraction_artifacts_dir(self) -> Path:
        return self.data.get_extraction_dir()

    def get_collation_artifacts_dir(self) -> Path:
        return self.data.get_collation_dir()

    def get_logger_config_path(self) -> Path:
        return Path(self.logging.config_file).resolve().absolute()


class StoredFileNames(BaseModel):
    original_image: str = "original-image.jpg"
    rotated_image: str = "rotated-image.jpg"
    cropped_image: str = "cropped-image.jpg"
    edited_image: str = "edited-image.jpg"
    shop_info_json: str = "shop-info.json"
    shop_info_parquet: str = "shop-info.parquet"
    items_info_json: str = "items-info.json"
    items_info_parquet: str = "items-info.parquet"
