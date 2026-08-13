from pathlib import Path

from backend.paths import HermesPaths
from backend.tools.sandbox import SandboxError, resolve_under


def test_resolve_under_allows_child(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    p.workspace.mkdir(parents=True)
    got = resolve_under(p.workspace, "notes/a.txt")
    assert got == (p.workspace / "notes" / "a.txt").resolve()


def test_resolve_under_rejects_escape(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    p.workspace.mkdir(parents=True)
    try:
        resolve_under(p.workspace, "../memories/MEMORY.md")
        assert False, "should have raised"
    except SandboxError as e:
        assert "outside" in str(e).lower()
