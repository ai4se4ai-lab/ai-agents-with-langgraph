from pathlib import Path
from backend.agent.events import load_loop_nodes


def test_react_loop_map_matches_shared():
    data = load_loop_nodes()
    ts = Path(__file__).resolve().parent.parent / "web" / "src" / "loopMap.ts"
    text = ts.read_text(encoding="utf-8")
    for node in data["nodes"]:
        assert node in text
    for step in data["steps"]:
        assert step in text


def test_web_mcp_helpers_exist():
    root = Path(__file__).resolve().parent.parent
    mcp = (root / "web" / "src" / "mcp.ts").read_text(encoding="utf-8")
    assert "export function actLabel" in mcp
    assert "export function usedMcps" in mcp
    app = (root / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "MCPs this run" in app
    assert "actLabel" in app
    assert "/mcp/reload" in app or "/mcp" in app

