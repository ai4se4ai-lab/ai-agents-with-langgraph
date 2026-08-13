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
