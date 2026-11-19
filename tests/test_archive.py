import os
import stat
import zipfile
from pathlib import Path
from zipfile import BadZipFile

import pytest

from zettel_drive.archive import (
    deterministic_hashing_from_tree,
    extract_staging_swap,
    hash_comparator,
    zip_file_compress,
)


def _make_corrupt_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.txt", b"garbage")
    data = bytearray(zip_path.read_bytes())
    data[0] ^= 0xFF
    zip_path.write_bytes(data)


def test_extract_replaces_existing_dest_cleanly(tmp_path: Path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "file.md").write_text("New File", encoding="utf-8")
    (src / "sub" / "file.md").write_text("File in sub", encoding="utf-8")

    zip_path = tmp_path / "vault.zip"
    zip_file_compress(src, zip_path)

    dest = tmp_path / "vault"
    dest.mkdir()
    (dest / "old.md").write_text("Old File", encoding="utf-8")

    extract_staging_swap(dest, zip_path)

    assert (dest / "file.md").read_text(encoding="utf-8") == "New File"
    assert (dest / "sub" / "file.md").read_text(encoding="utf-8") == "File in sub"
    assert not (dest / "old.md").exists()
    assert not (tmp_path / "vault.bak").exists()
    assert not (tmp_path / "vault.tmp").exists()


def test_extract_first_pull_creates_missing_parents(tmp_path: Path):
    zip_path = tmp_path / "paquete.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.md", "testing")
        zf.writestr("sub/b.md", "testing_another")

    dest = tmp_path / "nested" / "vault"
    extract_staging_swap(dest, zip_path)

    assert (dest / "a.md").read_text(encoding="utf-8") == "testing"
    assert (dest / "sub" / "b.md").read_text(encoding="utf-8") == "testing_another"
    assert not (dest.parent / "vault.bak").exists()
    assert not (dest.parent / "vault.tmp").exists()


def test_extract_with_relative_dot_dest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    zip_path = tmp_path / "file.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.md", "test")

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "old.md").write_text("v1", encoding="utf-8")
    monkeypatch.chdir(sandbox)

    extract_staging_swap(Path("."), zip_path)

    assert zip_path.exists()
    assert not (sandbox / "old.md").exists()
    assert (sandbox / "a.md").read_text(encoding="utf-8") == "test"


def test_extract_rejects_missing_zip(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "sana.md").write_text("v1", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        extract_staging_swap(vault, tmp_path / "ghost.zip")

    assert (vault / "sana.md").read_text(encoding="utf-8") == "v1"


def test_extract_rejects_file_or_symlink_dest(tmp_path: Path):
    zip_path = tmp_path / "file.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("a.md", "test")

    file_dest = tmp_path / "not_a_dir"
    file_dest.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        extract_staging_swap(file_dest, zip_path)
    assert file_dest.read_text(encoding="utf-8") == "keep"

    link_dest = tmp_path / "link_dest"
    link_dest.symlink_to(tmp_path / "missing_target")
    with pytest.raises(FileExistsError):
        extract_staging_swap(link_dest, zip_path)


def test_extract_first_pull_corrupt_or_empty_zip_leaves_no_dest(tmp_path: Path):
    corrupt = tmp_path / "corrupt.zip"
    _make_corrupt_zip(corrupt)
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w"):
        pass

    vault = tmp_path / "vault"
    for bad_zip in (corrupt, empty):
        with pytest.raises(BadZipFile):
            extract_staging_swap(vault, bad_zip)
        assert not vault.exists()
        assert not (tmp_path / "vault.bak").exists()
        assert not (tmp_path / "vault.tmp").exists()


def test_extract_rejects_empty_zip_preserving_dest(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "sana.md").write_text("v1", encoding="utf-8")

    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w"):
        pass

    with pytest.raises(BadZipFile):
        extract_staging_swap(vault, empty_zip)

    assert (vault / "sana.md").read_text(encoding="utf-8") == "v1"
    assert not (tmp_path / "vault.bak").exists()
    assert not (tmp_path / "vault.tmp").exists()


@pytest.mark.parametrize("entry_kind", ["traversal", "absolute", "symlink"])
def test_extract_rejects_unsafe_zip_entries(tmp_path: Path, entry_kind: str):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "sana.md").write_text("v1", encoding="utf-8")

    zip_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        if entry_kind == "traversal":
            zf.writestr("../escape.txt", "pwned")
        elif entry_kind == "absolute":
            zf.writestr("/etc/passwd", "pwned")
        else:
            info = zipfile.ZipInfo("link.txt")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")

    with pytest.raises(BadZipFile):
        extract_staging_swap(vault, zip_path)

    assert (vault / "sana.md").read_text(encoding="utf-8") == "v1"
    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "vault.bak").exists()
    assert not (tmp_path / "vault.tmp").exists()


def test_extract_recovers_orphan_bak_when_dest_missing(tmp_path: Path):
    vault = tmp_path / "vault"
    bak = tmp_path / "vault.bak"
    bak.mkdir()
    (bak / "sana.md").write_text("v1", encoding="utf-8")
    tmp = tmp_path / "vault.tmp"
    tmp.mkdir()
    (tmp / "basura.txt").write_text("parcial", encoding="utf-8")

    zip_path = tmp_path / "roto.zip"
    _make_corrupt_zip(zip_path)

    with pytest.raises(BadZipFile):
        extract_staging_swap(vault, zip_path)

    assert (vault / "sana.md").read_text(encoding="utf-8") == "v1"
    assert not bak.exists()
    assert not tmp.exists()


def test_extract_cleans_stale_bak_when_dest_exists(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "actual.md").write_text("v2", encoding="utf-8")

    bak = tmp_path / "vault.bak"
    bak.mkdir()
    (bak / "viejo.md").write_text("v1", encoding="utf-8")

    corrupt_zip = tmp_path / "roto.zip"
    _make_corrupt_zip(corrupt_zip)

    with pytest.raises(BadZipFile):
        extract_staging_swap(vault, corrupt_zip)

    assert (vault / "actual.md").read_text(encoding="utf-8") == "v2"
    assert not bak.exists()
    assert not (tmp_path / "vault.tmp").exists()


def test_extract_rolls_back_on_swap_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "sana.md").write_text("v1", encoding="utf-8")

    zip_path = tmp_path / "bueno.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("nueva.md", "v2")

    real_rename = os.rename
    calls = {"n": 0}

    def failing_second_rename(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("Simulated swap failure")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", failing_second_rename)

    with pytest.raises(OSError, match="Simulated swap failure"):
        extract_staging_swap(vault, zip_path)

    assert (vault / "sana.md").read_text(encoding="utf-8") == "v1"
    assert not (vault / "nueva.md").exists()
    assert not (tmp_path / "vault.bak").exists()
    assert not (tmp_path / "vault.tmp").exists()


# --- Hashing & Comparación ---

def test_hash_deterministic_and_sensitive_to_content_and_paths(tmp_path: Path):
    tree_a = tmp_path / "a"
    tree_b = tmp_path / "b"
    for root in (tree_a, tree_b):
        (root / "sub").mkdir(parents=True)
        (root / "nota.md").write_text("hola", encoding="utf-8")
        (root / "sub" / "extra.md").write_text("mundo", encoding="utf-8")

    hash_a = deterministic_hashing_from_tree(tree_a)
    assert hash_a == deterministic_hashing_from_tree(tree_b)
    assert hash_comparator(tree_b, hash_a) is True

    # Cambiar contenido altera el hash
    (tree_b / "nota.md").write_text("chau", encoding="utf-8")
    assert hash_comparator(tree_b, hash_a) is False

    # Renombrar ruta con mismo contenido también altera el hash
    (tree_b / "nota.md").write_text("hola", encoding="utf-8")
    (tree_b / "nota.md").rename(tree_b / "otro_nombre.md")
    assert hash_comparator(tree_b, hash_a) is False


def test_hash_respects_excludes_and_skips_symlinks(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "nota.md").write_text("base", encoding="utf-8")
    base_hash = deterministic_hashing_from_tree(vault, excludes=[".git/", "*.tmp"])

    (vault / ".git").mkdir()
    (vault / ".git" / "HEAD").write_text("ref: main", encoding="utf-8")
    (vault / "borrador.tmp").write_text("descartable", encoding="utf-8")
    (vault / "link.md").symlink_to(vault / "nota.md")

    assert deterministic_hashing_from_tree(vault, excludes=[".git/", "*.tmp"]) == base_hash


def test_hash_rejects_non_directory(tmp_path: Path):
    archivo = tmp_path / "solo.md"
    archivo.write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        deterministic_hashing_from_tree(archivo)
    with pytest.raises(NotADirectoryError):
        deterministic_hashing_from_tree(tmp_path / "inexistente")


# --- Compresión ZIP & Round-trip ---

def test_zip_compress_preserves_hierarchy_excludes_and_is_idempotent(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "sub").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    (vault / "a.md").write_text("uno", encoding="utf-8")
    (vault / "sub" / "b.md").write_text("dos", encoding="utf-8")
    (vault / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
    (vault / "ignorar.tmp").write_text("x", encoding="utf-8")
    (vault / "link.md").symlink_to(vault / "a.md")

    zip_path = tmp_path / "out" / "pack.zip"
    excludes = [".obsidian/", "*.tmp"]

    zip_file_compress(vault, zip_path, excludes=excludes)
    zip_file_compress(vault, zip_path, excludes=excludes)

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert zf.namelist() == ["a.md", "sub/b.md"]
        assert zf.read("a.md") == b"uno"
        assert zf.read("sub/b.md") == b"dos"


def test_zip_compress_rejects_non_directory_without_creating_zip(tmp_path: Path):
    zip_path = tmp_path / "out" / "pack.zip"

    with pytest.raises(NotADirectoryError):
        zip_file_compress(tmp_path / "no_existe", zip_path)

    assert not zip_path.exists()


def test_compress_and_extract_roundtrip_preserves_exact_hash(tmp_path: Path):
    src = tmp_path / "src"
    (src / "dir" / "deep").mkdir(parents=True)
    (src / "root.md").write_text("contenido raíz", encoding="utf-8")
    (src / "dir" / "deep" / "nota.md").write_text("contenido anidado", encoding="utf-8")
    (src / "basura.tmp").write_text("ignorar", encoding="utf-8")

    excludes = ["*.tmp"]
    expected_hash = deterministic_hashing_from_tree(src, excludes=excludes)

    zip_path = tmp_path / "snapshot.zip"
    zip_file_compress(src, zip_path, excludes=excludes)

    dest = tmp_path / "restored"
    extract_staging_swap(dest, zip_path)

    assert hash_comparator(dest, expected_hash) is True
    assert not (dest / "basura.tmp").exists()

