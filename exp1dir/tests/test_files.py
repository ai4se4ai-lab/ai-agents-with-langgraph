# exp1dir/tests/test_files.py
from pathlib import Path
from backend.paths import HermesPaths
from backend.tools.files import list_dir, read_file, write_file


def _paths(tmp_path: Path) -> HermesPaths:
    p = HermesPaths(root=tmp_path)
    p.workspace.mkdir(parents=True)
    return p


def test_write_read_list(tmp_path: Path):
    p = _paths(tmp_path)
    assert "wrote" in write_file(p, "a.txt", "hello").lower()
    assert read_file(p, "a.txt") == "hello"
    listing = list_dir(p, ".")
    assert "a.txt" in listing


def test_file_escape_is_error_string(tmp_path: Path):
    p = _paths(tmp_path)
    out = read_file(p, "../memories/MEMORY.md")
    assert out.startswith("ERROR:")
