import json
import os
from pathlib import Path

import pytest

from zettel_drive.config import ConfigContract, load_config, save_file_id


def test_load_config_happy_path(tmp_path: Path) -> None:
    config_json = tmp_path / "config.json"
    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "local_path": "/vault",
                "file_id": None,
                "excludes": (".git", "*.tmp"),
                "drive_folder_id": None,
            },
            f,
            indent=4,
        )

    contract = load_config(config_json)
    assert contract.local_path == Path("/vault")
    assert contract.file_id is None
    assert contract.excludes == (".git", "*.tmp")
    assert contract.drive_folder_id is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"local_path": "/vault"}, id="only-local-path"),
        pytest.param({"local_path": "/vault", "excludes": None}, id="null-excludes"),
    ],
)
def test_load_config_defaults_and_null_excludes(tmp_path: Path, payload: dict) -> None:
    config_json = tmp_path / "config.json"
    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)

    contract = load_config(config_json)
    assert contract.local_path == Path("/vault")
    assert contract.file_id is None
    assert contract.excludes == ()
    assert contract.drive_folder_id is None


@pytest.mark.parametrize(
    "corrupt_data",
    [
        pytest.param(["list", "invalid"], id="root-not-dict"),
        pytest.param(
            {"local_path": "/vault", "excludes": "*.git"}, id="excludes-as-str"
        ),
        pytest.param({"local_path": "  "}, id="blank-local-path"),
        pytest.param({"local_path": "/vault", "file_id": 123}, id="non-str-file-id"),
        pytest.param({"extra": 1}, id="unknown-key"),
        pytest.param({}, id="missing-local-path"),
        pytest.param(
            {"local_path": "/vault", "excludes": [".git", 1]}, id="non-str-exclude-item"
        ),
        pytest.param(
            {"local_path": "/vault", "excludes": [".git", ""]}, id="empty-exclude-item"
        ),
        pytest.param(
            {"local_path": "/vault", "excludes": [".git", None]}, id="null-exclude-item"
        ),
    ],
)
def test_load_config_rejects_invalid_schema(
    tmp_path: Path, corrupt_data: object
) -> None:
    config_json = tmp_path / "config.json"
    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(corrupt_data, f, indent=4)

    with pytest.raises(ValueError):
        load_config(config_json)


def test_load_config_rejects_malformed_json(tmp_path: Path) -> None:
    config_json = tmp_path / "config.json"
    config_json.write_text("{break", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(config_json)


def test_load_config_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "config.json")


def test_save_file_id_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_json = tmp_path / "config.json"
    json_data = {
        "local_path": "/vault",
        "file_id": None,
        "excludes": [".git"],
        "drive_folder_id": "folder-9",
    }

    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4)

    ret = save_file_id(Path("config.json"), "drive-id-123")

    assert isinstance(ret, ConfigContract)
    assert str(ret.local_path) == json_data["local_path"]
    assert ret.file_id == "drive-id-123"
    assert list(ret.excludes) == json_data["excludes"]
    assert ret.drive_folder_id == json_data["drive_folder_id"]
    assert list(tmp_path.iterdir()) == [config_json]


def test_save_file_id_overwrites_existing_id_with_defaults(tmp_path: Path) -> None:
    config_json = tmp_path / "config.json"
    with open(config_json, "w", encoding="utf-8") as f:
        json.dump({"local_path": "/vault", "file_id": "old-id-1"}, f, indent=4)

    ret = save_file_id(config_json, "new-id-2")

    assert ret == ConfigContract(
        local_path=Path("/vault"),
        file_id="new-id-2",
        excludes=(),
        drive_folder_id=None,
    )
    assert load_config(config_json) == ret
    assert list(tmp_path.iterdir()) == [config_json]


def test_save_file_id_preserves_config_on_replace_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_json = tmp_path / "config.json"
    json_data = {
        "local_path": "/vault",
        "file_id": "old-id-1",
        "excludes": [".git"],
        "drive_folder_id": None,
    }

    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4)

    def failing_replace_os(src, dst):
        raise OSError("Simulated OSError")

    monkeypatch.setattr(os, "replace", failing_replace_os)

    with pytest.raises(OSError, match="Simulated OSError"):
        save_file_id(config_json, "new-id-2")

    ret = load_config(config_json)
    assert str(ret.local_path) == json_data["local_path"]
    assert ret.file_id == json_data["file_id"]
    assert list(ret.excludes) == json_data["excludes"]
    assert ret.drive_folder_id == json_data["drive_folder_id"]
    assert list(tmp_path.iterdir()) == [config_json]


def test_save_file_id_rejects_invalid_file_id(tmp_path: Path) -> None:
    config_json = tmp_path / "config.json"
    json_data = {
        "local_path": "/vault",
        "file_id": "old-id-1",
    }

    with open(config_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4)

    with pytest.raises(TypeError):
        save_file_id(config_json, 123)  # type: ignore[arg-type]

    for bad_id in ("", " id-1 ", "id\t1"):
        with pytest.raises(ValueError):
            save_file_id(config_json, bad_id)

    ret = load_config(config_json)
    assert str(ret.local_path) == json_data["local_path"]
    assert ret.file_id == json_data["file_id"]
    assert list(tmp_path.iterdir()) == [config_json]


def test_save_file_id_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        save_file_id(tmp_path / "config.json", "drive-id-123")

    assert list(tmp_path.iterdir()) == []


def test_save_file_id_rejects_malformed_json(tmp_path: Path) -> None:
    config_json = tmp_path / "config.json"
    config_json.write_text("{break", encoding="utf-8")

    with pytest.raises(ValueError):
        save_file_id(config_json, "drive-id-123")

    assert config_json.read_text(encoding="utf-8") == "{break"
    assert list(tmp_path.iterdir()) == [config_json]
