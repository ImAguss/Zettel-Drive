# Roadmap — Zettel-Drive

Sincronización unidireccional (`PC -> Google Drive -> Teléfono / Termux`) mediante empaquetado `.zip` asociado a un `file_id` único en Google Drive.

## Fase 0 — Base del proyecto (Completada)
- [x] Estructura `src`-layout con `uv_build` (`src/zettel_drive/`).
- [x] Dependencias declaradas en [`pyproject.toml`](../pyproject.toml) (`google-api-python-client`, `google-auth-oauthlib`, `pytest`, Python `>=3.14`).
- [x] Exclusión de secretos y estado local en [`.gitignore`](../.gitignore).
- [x] Documentación base en `docs/` y registro técnico en `.docs-dev/`.

## Fase 1 — Operaciones de disco (`archive.py`) [En curso]
- [x] Hashing determinista `sha256` del árbol de archivos (orden estable, ruta relativa + contenido, exclusiones).
- [x] Empaquetado a `.zip` (`ZIP_DEFLATED`) aplicando reglas de exclusión.
- [ ] Extracción segura mediante *staging + swap*, prevención de *Zip Slip* y limpieza ante fallos.
- [ ] Pruebas unitarias offline en `tests/test_archive.py` con `pytest`.

## Fase 2 — Configuración y estado local (`config.py`, `state.py`)
- [ ] Esquema y validación de `config.json` por dispositivo (`local_path`, `file_id`, `excludes`, `drive_folder_id` opcional).
- [ ] Lectura y escritura atómica de `state.json` (`tree_sha256` en PC, `zip_md5` en teléfono).
- [ ] Persistencia del `file_id` en `config.json` tras el primer `push` (`create`).
- [ ] Pruebas unitarias en `tests/test_config_state.py`.

## Fase 3 — Orquestación y pruebas en memoria (`sync.py`)
- [ ] Contrato de cliente Drive (`Protocol` con `create`, `update`, `get_md5`, `download`).
- [ ] Flujo `push` (hash local vs `state.json` -> empaquetado -> `create`/`update` -> actualización de estado).
- [ ] Flujo `pull` (`get_md5` remoto vs `state.json` -> `download` a temporal -> *staging + swap* -> actualización de estado).
- [ ] Suite `tests/test_sync.py` con un cliente *fake* en memoria, sin acceso a red.

## Fase 4 — Adaptador de Google Drive (`drive.py`)
- [ ] Autenticación OAuth2 (`credentials.json` -> `token.json` con renovación automática).
- [ ] Flujo OAuth compatible con navegador local (PC) y consola/headless (Termux).
- [ ] Implementación de `create`, `update`, `get_md5` y `download` (con limpieza de descargas incompletas).
- [ ] Validación del ciclo de expiración del `refresh_token` en Google Cloud.

## Fase 5 — CLI y validación multi-dispositivo (`cli.py`)
- [ ] Interfaz de línea de comandos (`zettel-drive push`, `zettel-drive pull`, selección de target, `--dry-run`, `--force`).
- [ ] Validación de punta a punta en PC (Linux, Python `3.14.9`) y Android/Termux (Python `3.14.6`).
- [ ] Guía de instalación, configuración de credenciales OAuth2 y uso en `docs/`.
- [ ] Consolidación de notas técnicas desde `.docs-dev/` hacia el Zettelkasten.
