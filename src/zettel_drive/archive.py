import hashlib
import zipfile

from pathlib import Path
from fnmatch import fnmatchcase
from typing import Sequence, Any, Generator


def deterministic_hashing_from_tree(folder: Path, excludes: Sequence[str] | None = None) -> str:
    hasher = hashlib.sha256()

    for archive, rel_posix in _excludes_helper(folder, excludes):
        with open(archive, "rb") as f:
            digest = hashlib.file_digest(f, 'sha-256').digest()
            hasher.update(rel_posix.encode('utf-8') + b'\x00' + digest)

    return hasher.hexdigest()

def hash_comparator(folder: Path, hash_to_compare: str, excludes: Sequence[str] | None = None) -> bool:
    local_hash = deterministic_hashing_from_tree(folder, excludes)
    return local_hash == hash_to_compare

def zip_file_compress(folder: Path, path_to_compress: Path, excludes: Sequence[str] | None = None) -> None:
    path_to_compress.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path_to_compress, 'w', compression=zipfile.ZIP_DEFLATED) as zip_ref:
        for archive, rel_posix in _excludes_helper(folder, excludes):
            zip_ref.write(archive, arcname=rel_posix)

def _is_excluded(excludes: Sequence[str], rel_path: Path) -> bool:
    if excludes is not None:
        for exclude in excludes:
            pat = exclude.strip("/")
            if not pat:
                continue
            if (
                    fnmatchcase(rel_path.as_posix(), pat)
                    or any(fnmatchcase(part, pat) for part in rel_path.parts)
            ):
                return True

    return False

def _excludes_helper(folder: Path, excludes: Sequence[str] | None = None) -> Generator[tuple[Path, str], Any, None]:
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
            file = (dirpath / f)
            relative = file.relative_to(folder).as_posix()

            if (
                    not file.is_symlink()
                    and file.is_file()
                    and not _is_excluded(excludes, file.relative_to(folder))
            ):
                yield file, relative