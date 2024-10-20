import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

import library.handler as handler
import library.settings as settings_module
from library.settings import Settings


@pytest.fixture
def sample_image_bytesio() -> io.BytesIO:
    image = Image.new("RGB", (100, 100), color="red")
    byte_io = io.BytesIO()
    image.save(byte_io, format="JPEG")
    byte_io.seek(0)
    return byte_io


class MockUploadedFile:
    def __init__(self, name: str, byte_io: io.BytesIO):
        self.name = name
        self.byte_io = byte_io

    def getvalue(self) -> bytes:
        return self.byte_io.getvalue()

    def seek(self, *args, **kwargs) -> int:
        return self.byte_io.seek(*args, **kwargs)

    def read(self, *args) -> bytes:
        return self.byte_io.read(*args)

    def tell(self) -> int:
        return self.byte_io.tell()


@pytest.fixture
def mock_uploaded_file(sample_image_bytesio: io.BytesIO) -> MockUploadedFile:
    return MockUploadedFile("test_image.jpg", sample_image_bytesio)


def get_settings(tmp_path: Path) -> Settings:
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
        data=settings_module.Data(
            root_dir=root_dir,
            extraction_subdir=extraction_dir.name,
            collation_subdir=collation_dir.name,
            use_user=False,
        ),
        logging=settings_module.Logging(config_file=log_config),
        services=settings_module.Services(
            keys=settings_module.Keys(dir=key_dir),
            anthropic=settings_module.AnthropicService(
                key_file_name=key_file.name, model="wup", max_tokens=42
            ),
        ),
    )

    return settings


def test_from_streamlit_uploaded_file_new_directory(
    mock_uploaded_file: MockUploadedFile, tmp_path: Path
):
    settings = get_settings(tmp_path)

    # Line to test
    result = handler.from_streamlit_uploaded_file(mock_uploaded_file, settings)  # type: ignore

    # Conditions
    assert isinstance(result, handler.ImageHandler)
    assert isinstance(result.target_directory, Path)
    assert isinstance(result.original_image, Image.Image)
    assert isinstance(result.original_image_bytes, bytes)
    assert isinstance(result.original_file_name, str)

    assert not result.target_directory.exists()
    assert result.original_image.size == (100, 100)
    assert result.original_image_bytes == mock_uploaded_file.getvalue()
    assert result.original_file_name == "test_image.jpg"

    # Clean up
    shutil.rmtree(settings.data.root_dir)


def test_from_streamlit_uploaded_file_existing_directory(
    mock_uploaded_file: MockUploadedFile, tmp_path: Path
):
    # Create a directory that will be detected as existing
    settings = get_settings(tmp_path)
    result0 = handler.from_streamlit_uploaded_file(mock_uploaded_file, settings)  # type: ignore
    result0.save(mkdir=True, overwrite=False)

    assert result0.target_directory.exists()

    # Line to test
    result1 = handler.from_streamlit_uploaded_file(mock_uploaded_file, settings)  # type: ignore

    # Conditions - loaded data expected
    assert isinstance(result1, handler.ImageHandler)
    assert isinstance(result1.target_directory, Path)
    assert isinstance(result1.original_image, Image.Image)
    assert isinstance(result1.original_image_bytes, bytes)
    assert isinstance(result1.original_file_name, str)

    assert result1.target_directory.exists()
    assert result1.original_image.size == (100, 100)
    assert result1.original_image_bytes == mock_uploaded_file.getvalue()

    file_names = settings_module.StoredFileNames()
    assert result1.original_file_name == file_names.original_image

    # Contitions - files present as expected just after .save() call
    original_image_path = result1.get_target_file_path("original_image")
    assert original_image_path.exists()
    edited_image_path = result1.get_target_file_path("edited_image")
    assert not edited_image_path.exists()
    shop_parquet_path = result1.get_target_file_path("shop_info_parquet")
    assert not shop_parquet_path.exists()
    items_parquet_path = result1.get_target_file_path("items_info_parquet")
    assert not items_parquet_path.exists()

    # Clean up
    shutil.rmtree(settings.data.root_dir)


def test_from_source_image_path(mock_uploaded_file: MockUploadedFile, tmp_path: Path):
    # Create a directory with the image to start from
    settings = get_settings(tmp_path)

    test_image = Image.open(mock_uploaded_file.byte_io)
    test_image_path = settings.data.root_dir / "test_image.jpg"
    test_image.save(test_image_path)
    assert test_image_path.exists()

    # Line to test
    result = handler.from_source_image_path(test_image_path, settings)

    # Conditions - loaded data expected
    assert isinstance(result, handler.ImageHandler)
    assert isinstance(result.target_directory, Path)
    assert isinstance(result.original_image, Image.Image)
    assert isinstance(result.original_image_bytes, bytes)
    assert isinstance(result.original_file_name, str)

    assert result.original_image.size == (100, 100)
    assert result.original_image_bytes == mock_uploaded_file.getvalue()

    assert result.original_file_name == "test_image.jpg"

    # Clean up
    shutil.rmtree(settings.data.root_dir)
