import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfigContract:
    local_path: Path
    file_id: str | None = None
    excludes: tuple[str, ...] = ()
    drive_folder_id: str | None = None


def load_config(config_path: Path) -> ConfigContract:
    """Carga y valida la configuración del dispositivo desde `config_path`.

    Asume: `config_path` apunta a un JSON UTF-8 plano; única clave obligatoria `local_path` (string no vacío) y opcionales `file_id`, `excludes`, `drive_folder_id`.
    Garantiza: devuelve `ConfigContract` inmutable (`local_path` como `Path`, `excludes` como tupla de strings) sin tocar Drive ni exigir que `local_path` exista en disco.
    Errores: `FileNotFoundError` si falta el archivo; `ValueError` si el JSON es inválido, trae claves desconocidas o falla algún tipo/valor.
    """
    KEYS = {"local_path", "file_id", "excludes", "drive_folder_id"}
    if not config_path.exists():
        raise FileNotFoundError

    with open(config_path, "r", encoding="utf-8") as f:
        config_json = json.load(f)

    if not isinstance(config_json, dict):
        raise ValueError("Json is not a dict")

    if "local_path" not in config_json:
        raise ValueError("Not a local_path key in json")

    fake_key = config_json.keys() - KEYS
    if fake_key:
        raise ValueError("Key invalid in config")

    parsed_config = _clean_json(config_json)
    return ConfigContract(**parsed_config)


def _clean_json(obj: dict) -> dict:
    new_json = dict()

    for key, value in obj.items():
        match key:
            case "local_path":
                if _is_non_empty_str(value):
                    new_json[key] = Path(value)
                else:
                    raise ValueError("Invalid local path")
            case "file_id":
                if _is_non_empty_str(value):
                    new_json[key] = value
                elif value is None:
                    new_json[key] = None
                else:
                    raise ValueError("Invalid file id")
            case "excludes":
                if isinstance(value, list):
                    if not all(_is_non_empty_str(v) for v in value):
                        raise ValueError("Invalid types in excludes")
                    new_json[key] = tuple(v for v in value)
                elif value is None:
                    new_json[key] = ()
                else:
                    raise ValueError("Invalid excludes")
            case "drive_folder_id":
                if _is_non_empty_str(value):
                    new_json[key] = value
                elif value is None:
                    new_json[key] = None
                else:
                    raise ValueError("Invalid drive_folder_id")
            case _:
                raise ValueError("Invalid json")

    return new_json


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def save_file_id(config_path: Path, file_id: str) -> ConfigContract:
    """Actualiza de forma atómica `file_id` en `config_path` y devuelve el nuevo `ConfigContract`.

    Asume: `config_path` existe y es válido según `load_config`; `file_id` es `str` no vacío sin espacios (Drive ID opaco).
    Garantiza: preserva el resto de los campos en `config_path`, reemplaza el archivo atómicamente y no deja temporales residuales.
    Errores: `TypeError` si `file_id` no es `str`; `FileNotFoundError` si falta `config_path`; `ValueError` si `file_id` o el JSON son inválidos, dejando `config_path` intacto.
    """
    if not isinstance(file_id, str):
        raise TypeError

    if not file_id or any(c.isspace() for c in file_id):
        raise ValueError

    config_file = load_config(config_path)
    staging = config_path.parent / f"tmp_{config_path.name}"
    try:
        with open(staging, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "local_path": str(config_file.local_path),
                    "file_id": file_id,
                    "excludes": config_file.excludes,
                    "drive_folder_id": config_file.drive_folder_id,
                },
                f,
                indent=4,
            )
        config_file = load_config(staging)
        os.replace(staging, config_path)
        return config_file
    except OSError:
        staging.unlink(missing_ok=True)
        raise
