from pathlib import Path
from backend.memory.store import MemoryStore, ensure_home
from backend.paths import HermesPaths
from backend.tools.memory_tool import memory_tool


def test_ensure_home_creates_files(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    assert p.memory_md.exists()
    assert p.user_md.exists()
    assert p.workspace.is_dir()


def test_memory_add_replace_remove(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    store = MemoryStore(p)
    assert "added" in memory_tool(store, "add", "MEMORY", "project is exp1").lower()
    assert "exp1" in p.memory_md.read_text(encoding="utf-8")
    assert "replaced" in memory_tool(store, "replace", "MEMORY", "project is exp1dir", old_text="project is exp1").lower()
    assert "exp1dir" in p.memory_md.read_text(encoding="utf-8")
    assert "removed" in memory_tool(store, "remove", "MEMORY", old_text="project is exp1dir").lower()
    assert "exp1dir" not in p.memory_md.read_text(encoding="utf-8")


def test_snapshot_concatenates(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    p.memory_md.write_text("# Memory\nfact\n", encoding="utf-8")
    p.user_md.write_text("# User\npref\n", encoding="utf-8")
    snap = MemoryStore(p).snapshot()
    assert "fact" in snap and "pref" in snap
