from backend.agent.events import EventLog, load_loop_nodes, make_event
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_loop_nodes_cover_steps():
    data = load_loop_nodes()
    for step in ("task", "reason", "act", "observe", "success", "learn", "memory_update", "error"):
        assert step in data["steps"]


def test_event_log_append_and_replay(tmp_path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    log = EventLog(p, "run1")
    e = make_event("run1", "reason", cycle=1, text="thinking", model="m")
    log.append(e)
    replay = log.replay()
    assert replay[0]["step"] == "reason"
    assert replay[0]["text"] == "thinking"


def test_make_event_includes_mcp_fields():
    e = make_event("r", "act", tool="web__search")
    assert e["mcp_server"] == ""
    assert e["mcp_tool"] == ""
    e2 = make_event("r", "act", tool="web__search", mcp_server="web", mcp_tool="search")
    assert e2["mcp_server"] == "web" and e2["mcp_tool"] == "search"
