import hashlib
import os
import shutil
import stat
import zipfile
from collections.abc import Generator, Sequence
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile


def deterministic_hashing_from_tree(
    folder: Path, excludes: Sequence[str] | None = None
) -> str:
    """Calcula un SHA-256 determinista del árbol de archivos de `folder`.

    Asume: `folder` es un directorio existente (symlinks y patrones en `excludes` se omiten).
    Garantiza: mismo orden lexicográfico y encuadre inyectivo (`rel_posix + \\x00 + sha256`),
      independiente del directorio padre o del orden del filesystem.
    Errores: lanza `NotADirectoryError` si `folder` no existe o no es directorio.
    """
    hasher = hashlib.sha256()

    for archive, rel_posix in _excludes_helper(folder, excludes):
        with open(archive, "rb") as f:
            digest = hashlib.file_digest(f, "sha-256").digest()
            hasher.update(rel_posix.encode("utf-8") + b"\x00" + digest)

    return hasher.hexdigest()


def hash_comparator(
    folder: Path, hash_to_compare: str, excludes: Sequence[str] | None = None
) -> bool:
    local_hash = deterministic_hashing_from_tree(folder, excludes)
    return local_hash == hash_to_compare


def zip_file_compress(
    folder: Path, path_to_compress: Path, excludes: Sequence[str] | None = None
) -> None:
    """Empaqueta el árbol de `folder` en un `.zip` con rutas POSIX relativas.

    Asume: `folder` es un directorio existente (omite symlinks y `excludes`; no empaqueta carpetas vacías).
    Garantiza: crea directorios padre de `path_to_compress` y sobrescribe el `.zip` de forma idempotente.
    Errores: lanza `NotADirectoryError` si `folder` no es directorio, sin dejar un `.zip` vacío en disco.
    """
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))

    path_to_compress.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(
        path_to_compress, "w", compression=zipfile.ZIP_DEFLATED
    ) as zip_ref:
        for archive, rel_posix in _excludes_helper(folder, excludes):
            zip_ref.write(archive, arcname=rel_posix)


def _is_excluded(excludes: Sequence[str], rel_path: Path) -> bool:
    if excludes is not None:
        for exclude in excludes:
            pat = exclude.strip("/")
            if not pat:
                continue
            if fnmatchcase(rel_path.as_posix(), pat) or any(
                fnmatchcase(part, pat) for part in rel_path.parts
            ):
                return True

    return False


def _excludes_helper(
    folder: Path, excludes: Sequence[str] | None = None
) -> Generator[tuple[Path, str], Any]:
    if excludes is None:
        excludes = []

    if not folder.is_dir():
        raise NotADirectoryError(str(folder))

    folder = folder.resolve()
    for dirpath, dirnames, filenames in folder.walk():
        clean_dirnames = list()
        for d in sorted(dirnames):
            sub = dirpath / d
            if sub.is_symlink() or _is_excluded(excludes, sub.relative_to(folder)):
                continue

            clean_dirnames.append(d)
        dirnames[:] = clean_dirnames
        for f in sorted(filenames):
            file = dirpath / f
            relative = file.relative_to(folder).as_posix()

            if (
                not file.is_symlink()
                and file.is_file()
                and not _is_excluded(excludes, file.relative_to(folder))
            ):
                yield file, relative


def _recover_orphan_state(dest: Path, staging: Path, bak: Path) -> None:
    if staging.exists():
        shutil.rmtree(staging)

    if bak.exists():
        if not dest.exists():
            os.rename(bak, dest)
        else:
            shutil.rmtree(bak)


def extract_staging_swap(dest: Path, zip_path: Path) -> None:
    """Extrae un .zip propio y reemplaza `dest` atómicamente en el mismo filesystem.

    Asume: `zip_path` fue generado por `zip_file_compress` (fuera de alcance:
      carpetas vacías de zips externos o archivos especiales como FIFO/sockets).
    Garantiza: recupera `.bak`/`.tmp` huérfanos, reemplaza `dest` con el árbol del
      zip y no deja residuos `.tmp`/`.bak`.
    Errores: lanza `FileExistsError` si `dest` es archivo/symlink, `FileNotFoundError`
      si falta `zip_path`, `BadZipFile` si el zip es inválido/vacío/malicioso, y
      restaura `dest` intacto si falla la extracción o el swap.
    """
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        raise FileExistsError(str(dest))

    if not zip_path.is_file():
        raise FileNotFoundError(str(zip_path))

    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / f"{dest.name}.tmp"
    bak = dest.parent / f"{dest.name}.bak"

    _recover_orphan_state(dest, staging, bak)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            entries = [e for e in zip_ref.infolist() if not e.is_dir()]
            if not entries:
                raise BadZipFile("Empty zip archive")

            staging.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                if (
                    stat.S_ISLNK(entry.external_attr >> 16)
                    or PurePosixPath(entry.filename).is_absolute()
                    or not (staging / entry.filename).resolve().is_relative_to(staging)
                ):
                    raise BadZipFile(f"Unsafe zip entry: {entry.filename}")

                target = staging / entry.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_ref.open(entry) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    had_dest = dest.exists()
    if had_dest:
        os.rename(dest, bak)
    try:
        os.rename(staging, dest)
    except Exception:
        if had_dest and bak.exists() and not dest.exists():
            os.rename(bak, dest)
        if staging.exists():
            shutil.rmtree(staging)
        raise

    if had_dest and bak.exists():
        shutil.rmtree(bak)
