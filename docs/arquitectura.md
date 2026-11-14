# Arquitectura de Zettel-Drive

## Modelo de flujo
`Zettel-Drive` implementa un **mirror unidireccional de autoridad única**:

```text
[PC (autoridad)] --(push: .zip)--> [Google Drive (file_id)] --(pull: .zip)--> [Teléfono / Termux]
```

- La PC y el teléfono **no se conocen entre sí**: cada dispositivo mantiene su propio `config.json` y `state.json`.
- El único contrato compartido entre dispositivos es el `file_id` de Drive y el formato `.zip`.

## Responsabilidades de módulos (`src/zettel_drive/`)

| Módulo | Responsabilidad | Frontera de I/O |
| :--- | :--- | :--- |
| `config.py` | Carga y validación de `config.json` por dispositivo | Disco (JSON de config) |
| `state.py` | Lectura/escritura atómica de hashes previos (`state.json`) | Disco (JSON de estado) |
| `archive.py` | Hash determinista, empaquetado `.zip` y extracción *staging + swap* | Disco puro (`stdlib`) |
| `drive.py` | Autenticación OAuth2 y 4 operaciones (`create`, `update`, `get_md5`, `download`) | Red (Google Drive API) |
| `sync.py` | Orquestación de casos de uso `push` y `pull` | Coordina dominio + cliente |
| `cli.py` | Parseo de comandos e invocación a `sync.py` | Terminal (`stdin`/`stdout`) |
