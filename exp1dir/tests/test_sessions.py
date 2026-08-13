from pathlib import Path
from backend.memory.sessions import SessionStore
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.sessions_tool import search_sessions


def test_search_sessions(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    store = SessionStore(p)
    store.save("r1", "list workspace", "found notes.txt", "success")
    hits = search_sessions(store, "notes")
    assert "notes.txt" in hits
    assert "r1" in hits
