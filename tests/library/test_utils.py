import base64
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest
import requests
from PIL import Image, ImageChops

from library.settings import (
    AnthropicService,
    Data,
    Keys,
    Logging,
    Services,
    Settings,
    StoredFileNames,
)
from library.utils import (
    ID_COL,
    base64_encode_image_bytes,
    check_available_extraction_dirs,
    cleanup,
    collect,
    compile_infos,
    create_zipfile,
    get_compiled_paths,
    internet_connection,
    put_id_col_at_end,
    read_and_b64_encode_image,
    read_image_as_bytes,
    save_image_as_jpg_file,
    write_excel_workbook,
)


# ======= test def internet_connection =======
@pytest.mark.parametrize(
    "status_code,expected",
    [
        (200, True),
        (404, False),
        (500, False),
    ],
)
def test_internet_connection_status_codes(status_code: int, expected: bool):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = status_code
        assert internet_connection() is expected


def test_internet_connection_timeout():
    with patch("requests.get", side_effect=requests.Timeout):
        assert internet_connection() is False


def test_internet_connection_connection_error():
    with patch("requests.get", side_effect=requests.ConnectionError):
        assert internet_connection() is False


def test_internet_connection_request_exception():
    with patch("requests.get", side_effect=requests.RequestException):
        assert internet_connection() is False


# ======= test def check_available_extraction_dirs =======
@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    return Settings()  # type: ignore


def test_check_available_extraction_dirs_empty(settings: Settings):
    shop_info_files, items_info_files = check_available_extraction_dirs(settings)
    assert len(shop_info_files) == 0
    assert len(items_info_files) == 0


def test_check_available_extraction_dirs_with_files(settings: Settings):
    root_dir = settings.get_extraction_artifacts_dir()
    file_names = StoredFileNames()

    # Create mock directory structure
    dir1 = root_dir / "dir1"
    dir1.mkdir()
    dir2 = root_dir / "dir2"
    dir2.mkdir()

    # Create mock files
    file1 = dir1 / file_names.shop_info_parquet
    file1.touch()
    file2 = dir2 / file_names.items_info_parquet
    file2.touch()

    shop_info_files, items_info_files = check_available_extraction_dirs(settings)

    assert len(shop_info_files) == 1
    assert len(items_info_files) == 1
    assert shop_info_files[0] == file1
    assert items_info_files[0] == file2

    shutil.rmtree(dir1)
    shutil.rmtree(dir2)


def test_check_available_extraction_dirs_ignore_root_files(settings: Settings):
    root_dir = settings.get_extraction_artifacts_dir()
    file_names = StoredFileNames()

    # Create files in root directory (should be ignored)
    file1 = root_dir / file_names.shop_info_parquet
    file1.touch()
    file2 = root_dir / file_names.items_info_parquet
    file2.touch()

    shop_info_files, items_info_files = check_available_extraction_dirs(settings)

    assert len(shop_info_files) == 0
    assert len(items_info_files) == 0

    file1.unlink()
    file2.unlink()


def test_check_available_extraction_dirs_multiple_files(settings: Settings):
    root_dir = settings.get_extraction_artifacts_dir()
    file_names = StoredFileNames()

    # Create mock directory structure
    dir1 = root_dir / "dir1"
    dir1.mkdir()
    dir2 = root_dir / "dir2"
    dir2.mkdir()
    dir3 = root_dir / "dir3"
    dir3.mkdir()

    # Create mock files
    file1 = dir1 / file_names.shop_info_parquet
    file1.touch()
    file2 = dir2 / file_names.shop_info_parquet
    file2.touch()
    file3 = dir2 / file_names.items_info_parquet
    file3.touch()
    file4 = dir3 / file_names.items_info_parquet
    file4.touch()

    shop_info_files, items_info_files = check_available_extraction_dirs(settings)

    assert len(shop_info_files) == 2
    assert len(items_info_files) == 2
    assert set(shop_info_files) == {file1, file2}
    assert set(items_info_files) == {file3, file4}

    shutil.rmtree(dir1)
    shutil.rmtree(dir2)
    shutil.rmtree(dir3)


# ======= test def compile_infos =======


def create_test_parquet(tmp_path: Path, filename: str, data: dict) -> Path:
    df = pl.DataFrame(data)
    file_path = tmp_path / filename
    df.write_parquet(file_path)
    return file_path


def test_compile_infos_single_file(tmp_path: Path):
    info_file = create_test_parquet(
        tmp_path, "info1.parquet", {"col1": [1, 2], "col2": ["a", "b"]}
    )
    result = compile_infos([info_file])

    assert isinstance(result, pl.DataFrame)
    assert result.shape == (2, 3)  # 2 rows, 3 columns (col1, col2, ID_COL)
    assert ID_COL in result.columns
    assert all(result[ID_COL] == tmp_path.name)
    info_file.unlink()


def test_compile_infos_multiple_files(tmp_path: Path):
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    info_file1 = create_test_parquet(
        dir1, "info1.parquet", {"col1": [1, 2], "col2": ["a", "b"]}
    )
    dir2 = tmp_path / "dir2"
    dir2.mkdir()
    info_file2 = create_test_parquet(
        dir2, "info2.parquet", {"col1": [3, 4], "col2": ["c", "d"]}
    )

    result = compile_infos([info_file1, info_file2])

    assert isinstance(result, pl.DataFrame)
    assert result.shape == (4, 3)  # 4 rows, 3 columns (col1, col2, ID_COL)
    assert ID_COL in result.columns
    assert set(result[ID_COL].unique()) == {dir1.name, dir2.name}
    shutil.rmtree(dir1)
    shutil.rmtree(dir2)


def test_compile_infos_empty_list():
    with pytest.raises(ValueError):
        _ = compile_infos([])


def test_compile_infos_different_schemas(tmp_path: Path):
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    info_file1 = create_test_parquet(
        dir1, "info1.parquet", {"col1": [1, 2], "col2": ["a", "b"]}
    )
    dir2 = tmp_path / "dir2"
    dir2.mkdir()
    info_file2 = create_test_parquet(
        dir2, "info2.parquet", {"col1": [3, 4], "col3": [True, False]}
    )

    result = compile_infos([info_file1, info_file2])

    assert isinstance(result, pl.DataFrame)
    assert result.shape == (4, 4)  # 4 rows, 4 columns (col1, col2, col3, ID_COL)
    assert set(result.columns) == {"col1", "col2", "col3", ID_COL}
    assert result["col2"].null_count() == 2
    assert result["col3"].null_count() == 2
    shutil.rmtree(dir1)
    shutil.rmtree(dir2)


def test_compile_infos_file_not_found(tmp_path):
    info_file = tmp_path / "non_existent.parquet"

    with pytest.raises(Exception):  # Adjust the exception type if needed
        compile_infos([info_file])


# ======= test def get_compiled_paths =======


def test_get_compiled_paths(settings: Settings):
    compiled_shop_info_path, compiled_items_info_path = get_compiled_paths(settings)

    expected_root_dir = Path(settings.data.root_dir) / settings.data.collation_subdir
    file_names = StoredFileNames()

    assert compiled_shop_info_path == expected_root_dir / file_names.shop_info_parquet
    assert compiled_items_info_path == expected_root_dir / file_names.items_info_parquet
    assert compiled_shop_info_path.is_absolute()
    assert compiled_items_info_path.is_absolute()
    assert compiled_shop_info_path != compiled_items_info_path


# ======= test def collect =======


def test_collect_creates_output_files(settings: Settings):
    file_names = StoredFileNames()

    # Create some dummy input files
    extraction_dir = settings.get_extraction_artifacts_dir()
    dummy_dir = extraction_dir / "dummy"
    dummy_dir.mkdir(parents=True)
    dummy_shop_file = dummy_dir / file_names.shop_info_parquet
    dummy_items_file = dummy_dir / file_names.items_info_parquet

    pl.DataFrame(
        {"name": ["Shop1"], "date": ["2023-01-01"], "time": ["12:00"], "total": [100.0]}
    ).write_parquet(dummy_shop_file)

    pl.DataFrame(
        {
            "name": ["Item1"],
            "price": [10.0],
            "count": [1],
            "mass": [1.0],
            "tax": [0.1],
            "category": ["Category1"],
        }
    ).write_parquet(dummy_items_file)

    collect(settings)

    collation_dir = settings.get_collation_artifacts_dir()
    assert (collation_dir / file_names.shop_info_parquet).exists()
    assert (collation_dir / file_names.items_info_parquet).exists()

    shutil.rmtree(dummy_dir)


def test_collect_compiles_data_correctly(settings: Settings):
    file_names = StoredFileNames()

    # Create some dummy input files
    extraction_dir = settings.get_extraction_artifacts_dir()
    dummy_shop_file1 = extraction_dir / "dummy1" / file_names.shop_info_parquet
    dummy_items_file1 = extraction_dir / "dummy1" / file_names.items_info_parquet
    dummy_shop_file2 = extraction_dir / "dummy2" / file_names.shop_info_parquet
    dummy_items_file2 = extraction_dir / "dummy2" / file_names.items_info_parquet

    for file in [
        dummy_shop_file1,
        dummy_items_file1,
        dummy_shop_file2,
        dummy_items_file2,
    ]:
        file.parent.mkdir(parents=True, exist_ok=True)

    pl.DataFrame(
        {"name": ["Shop1"], "date": ["2023-01-01"], "time": ["12:00"], "total": [100.0]}
    ).write_parquet(dummy_shop_file1)

    pl.DataFrame(
        {
            "name": ["Item1", "Item2"],
            "price": [10.0, 20.0],
            "count": [1, 2],
            "mass": [1.0, 2.0],
            "tax": [0.1, 0.2],
            "category": ["Category1", "Category2"],
        }
    ).write_parquet(dummy_items_file1)

    pl.DataFrame(
        {"name": ["Shop2"], "date": ["2023-01-02"], "time": ["13:00"], "total": [200.0]}
    ).write_parquet(dummy_shop_file2)

    pl.DataFrame(
        {
            "name": ["Item3"],
            "price": [30.0],
            "count": [3],
            "mass": [3.0],
            "tax": [0.3],
            "category": ["Category3"],
        }
    ).write_parquet(dummy_items_file2)

    collect(settings)

    collation_dir = Path(settings.get_collation_artifacts_dir())
    compiled_shop_info = pl.read_parquet(collation_dir / file_names.shop_info_parquet)
    compiled_items_info = pl.read_parquet(collation_dir / file_names.items_info_parquet)

    assert len(compiled_shop_info) == 2
    assert len(compiled_items_info) == 3
    assert "target_directory" in compiled_shop_info.columns
    assert "target_directory" in compiled_items_info.columns
    assert "pretty name" in compiled_items_info.columns


# ======= test def create_zipfile =======


def test_create_zipfile_creates_zip(tmp_path: Path):
    # Create some test files
    file1 = tmp_path / "file1.txt"
    file1.write_text("Test content 1")
    file2 = tmp_path / "file2.txt"
    file2.write_text("Test content 2")
    dir1 = tmp_path / "subdir"
    dir1.mkdir()
    file3 = dir1 / "file3.txt"
    file3.write_text("Test content 3")

    # Call the function
    zip_path = create_zipfile(tmp_path)

    # Check if zip file was created
    assert zip_path.exists()
    assert zip_path.is_file()
    assert zip_path.name == "extractions.zip"


def test_create_zipfile_contents(tmp_path: Path):
    # Create some test files
    file1 = tmp_path / "file1.txt"
    file1.write_text("Test content 1")
    file2 = tmp_path / "file2.txt"
    file2.write_text("Test content 2")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    file3 = subdir / "file3.txt"
    file3.write_text("Test content 3")

    # Call the function
    zip_path = create_zipfile(tmp_path)

    # Check zip contents
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        file_list = zip_ref.namelist()
        assert file1.name in file_list
        assert file2.name in file_list
        assert "subdir/file3.txt" in file_list

        # Check file contents
        assert zip_ref.read("file1.txt").decode() == "Test content 1"
        assert zip_ref.read("file2.txt").decode() == "Test content 2"
        assert zip_ref.read("subdir/file3.txt").decode() == "Test content 3"


def test_create_zipfile_empty_directory(tmp_path: Path):
    # Call the function on an empty directory
    zip_path = create_zipfile(tmp_path)

    # Check if zip file was created
    assert zip_path.exists()
    assert zip_path.is_file()

    # Check that the zip file is empty
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        assert len(zip_ref.namelist()) == 0


def test_create_zipfile_nonexistent_directory(tmp_path):
    non_existent_path = tmp_path / "nonexistent"
    with pytest.raises(FileNotFoundError):
        create_zipfile(non_existent_path)


# ======= test def create_zipfile =======


def test_put_id_col_at_end():
    # Create a sample DataFrame
    df = pl.DataFrame(
        {"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "age": [25, 30, 35]}
    )

    # Call the function
    result = put_id_col_at_end(df, "id")

    # Check if the 'id' column is at the end
    assert result.columns[-1] == "id"

    # Check if all columns are present
    assert set(result.columns) == set(["id", "name", "age"])

    # Check if the order of other columns is preserved
    assert result.columns[:-1] == ["name", "age"]

    # Test with 'id' column already at the end
    df_id_at_end = pl.DataFrame(
        {"name": ["Alice", "Bob", "Charlie"], "age": [25, 30, 35], "id": [1, 2, 3]}
    )
    result_id_at_end = put_id_col_at_end(df_id_at_end, "id")
    assert result_id_at_end.columns == ["name", "age", "id"]

    # Test with non-existent 'id' column
    with pytest.raises(Exception):
        put_id_col_at_end(df, "non_existent_id")


# ======= test def write_excel_workbook =======
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


@pytest.fixture
def sample_data(mock_settings: Settings) -> tuple[pl.DataFrame, pl.DataFrame]:
    compiled_shop_info_path, compiled_items_info_path = get_compiled_paths(
        mock_settings
    )

    # Create sample shops DataFrame
    shops = pl.DataFrame(
        {
            "name": ["Shop A", "Shop B"],
            "address": ["123 Main St", "456 Elm St"],
            ID_COL: [1, 2],
        }
    )
    shops.write_parquet(compiled_shop_info_path)

    # Create sample items DataFrame
    items = pl.DataFrame(
        {
            "name": ["Item 1", "Item 2"],
            "price": [10.99, 5.50],
            "mass": [0.5, 1.0],
            ID_COL: [1, 2],
        }
    )
    items.write_parquet(compiled_items_info_path)

    return shops, items


def test_write_excel_workbook(
    mock_settings: Settings, sample_data: tuple[pl.DataFrame, pl.DataFrame]
):
    # Call the function
    excel_path = write_excel_workbook(mock_settings)

    # Assert that the Excel file was created
    assert excel_path.exists()
    assert excel_path.name == "groceries-data.xlsx"

    # Read the Excel file to verify its contents
    shops_disk = pl.read_excel(excel_path, sheet_name="Shops", engine="openpyxl")
    items_disk = pl.read_excel(excel_path, sheet_name="Items", engine="openpyxl")

    shops, items = sample_data

    # Verify shops data
    assert shops_disk.shape == (2, 3)
    assert shops_disk.columns == ["name", "address", ID_COL]
    assert shops_disk[ID_COL].to_list() == [1, 2]
    assert shops_disk.equals(shops)

    # Verify items data
    assert items_disk.shape == (2, 4)
    assert items_disk.columns == ["name", "price", "mass", ID_COL]
    assert items_disk[ID_COL].to_list() == [1, 2]
    assert items_disk.equals(items)


# ======= test def cleanup =======
def test_cleanup_removes_existing_directories(settings: Settings):
    # Create some dummy files in the directories
    collation_dir = settings.get_collation_artifacts_dir()
    collation_file = collation_dir / "test_file.txt"
    collation_subdir = collation_dir / "subdir"
    extraction_dir = settings.get_extraction_artifacts_dir()
    extraction_file = extraction_dir / "test_file.txt"
    extraction_subdir = extraction_dir / "subdir"
    collation_file.touch()
    collation_subdir.mkdir()
    extraction_file.touch()
    extraction_subdir.mkdir()

    cleanup(settings)

    assert not collation_file.exists()
    assert not extraction_file.exists()
    assert not collation_subdir.exists()
    assert not extraction_subdir.exists()
    assert collation_dir.exists()
    assert extraction_dir.exists()


def test_cleanup_fails_with_non_existent_directories(settings: Settings):
    # Remove the directories first
    collation_dir = settings.get_collation_artifacts_dir()
    collation_dir.rmdir()

    with pytest.raises(FileNotFoundError):
        cleanup(settings)

    collation_dir.mkdir()

    extraction_dir = settings.get_extraction_artifacts_dir()
    extraction_dir.rmdir()

    with pytest.raises(FileNotFoundError):
        cleanup(settings)


# ======= test image utility functions =======


def test_read_image_as_bytes_valid_file(tmp_path: Path):
    # Create a temporary image file
    image_path = tmp_path / "test_image.png"
    image_content = b"Fake image content"
    image_path.write_bytes(image_content)

    # Test the function
    result = read_image_as_bytes(image_path)
    assert result == image_content


def test_read_image_as_bytes_file_not_found():
    non_existent_path = Path("/path/to/non_existent_image.jpg")
    with pytest.raises(FileNotFoundError):
        read_image_as_bytes(non_existent_path)


def test_read_image_as_bytes_directory(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_image_as_bytes(tmp_path)


@pytest.mark.parametrize("file_extension", [".png", ".jpg", ".gif"])
def test_read_image_as_bytes_different_formats(tmp_path: Path, file_extension: str):
    image_path = tmp_path / f"test_image{file_extension}"
    image_content = b"Fake image content"
    image_path.write_bytes(image_content)

    result = read_image_as_bytes(image_path)
    assert result == image_content


def test_base64_encode_image_bytes_empty():
    empty_bytes = b""
    result = base64_encode_image_bytes(empty_bytes)
    assert result == "", "Empty bytes should result in an empty string"


def test_base64_encode_image_bytes_simple():
    test_bytes = b"Hello, World!"
    expected_result = base64.b64encode(test_bytes).decode("utf-8")
    result = base64_encode_image_bytes(test_bytes)
    assert result == expected_result, "Encoding mismatch for simple byte string"


def test_base64_encode_image_bytes_actual_image(tmp_path: Path):
    # Create a dummy image file
    image_path = tmp_path / "test_image.png"
    dummy_image_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

    with image_path.open("wb") as f:
        f.write(dummy_image_data)

    with image_path.open("rb") as image_file:
        image_bytes = image_file.read()

    expected_result = base64.b64encode(image_bytes).decode("utf-8")
    result = base64_encode_image_bytes(image_bytes)
    assert result == expected_result, "Encoding mismatch for actual image bytes"


def test_base64_encode_image_bytes_invalid_input():
    with pytest.raises(TypeError):
        base64_encode_image_bytes("Not a bytes object")  # type: ignore


@pytest.fixture
def temp_image_file(tmp_path: Path) -> Path:
    image_path = tmp_path / "test_image.jpg"
    image_path.write_bytes(b"fake image content")
    return image_path


def test_read_and_b64_encode_image_valid(temp_image_file: Path):
    result = read_and_b64_encode_image(temp_image_file)
    assert isinstance(result, str)
    decoded = base64.b64decode(result.encode("utf-8"))
    assert decoded == b"fake image content"


def test_read_and_b64_encode_image_non_existent():
    with pytest.raises(FileNotFoundError):
        read_and_b64_encode_image(Path("non_existent.jpg"))


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path / "test_images"


@pytest.fixture
def sample_image_bytes() -> bytes:
    # Create a sample image in bytes format
    return b"sample image bytes"


@pytest.fixture
def sample_image_pil() -> Image.Image:
    # Create a sample PIL Image
    return Image.new("RGB", (100, 100), color="red")


def test_save_image_as_jpg_fail_file_directory_not_exists_no_mkdir(temp_dir: Path):
    with pytest.raises(FileNotFoundError):
        save_image_as_jpg_file(
            image_path=temp_dir / "test.jpg", image=b"", overwrite=False, mkdir=False
        )


def test_save_image_as_jpg_success(temp_dir: Path):
    image_path = temp_dir / "test.jpg"
    save_image_as_jpg_file(
        image_path=image_path, image=b"", overwrite=False, mkdir=True
    )
    assert temp_dir.exists()
    assert image_path.exists()


def test_save_image_as_jpg_success_file_exists_no_overwrite(temp_dir: Path):
    temp_dir.mkdir(parents=True)
    file_path = temp_dir / "test.jpg"
    file_path.touch()
    save_image_as_jpg_file(
        image_path=file_path, image=b"new content", overwrite=False, mkdir=True
    )
    assert file_path.read_bytes() == b""


def test_save_image_as_jpg_success_file_exists_with_overwrite(temp_dir: Path):
    temp_dir.mkdir(parents=True)
    file_path = temp_dir / "test.jpg"
    file_path.touch()
    image = b"new content"
    save_image_as_jpg_file(
        image_path=file_path, image=image, overwrite=True, mkdir=True
    )
    assert file_path.read_bytes() == image


def test_save_image_as_jpg_success_save_pil_image(
    temp_dir: Path, sample_image_pil: Image.Image
):
    file_path = temp_dir / "test.jpg"
    save_image_as_jpg_file(
        image_path=file_path, image=sample_image_pil, overwrite=True, mkdir=True
    )
    assert file_path.exists()
    _ = Image.open(file_path, formats=["JPEG", "JPG"])
    # note: comparing loaded and original image object not sensible, PIL.Image.Image.save/open do not generate the same image


def test_save_image_as_jpg_invalid_image_type(temp_dir: Path):
    with pytest.raises(TypeError):
        save_image_as_jpg_file(
            image_path=temp_dir / "test.jpg",
            image="invalid type",  # type: ignore
            overwrite=True,
            mkdir=True,
        )
