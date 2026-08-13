from pathlib import Path
from backend.agent.nodes import act
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.registry import build_tool_fns


def test_act_survives_malformed_args_for_required_param_tool(tmp_path: Path):
    """A tool call with empty args against a tool that requires params must not crash act()."""
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    tools = build_tool_fns(p)
    state = {
        "run_id": "r1",
        "cycle": 0,
        "pending_tool_calls": [{"id": "1", "name": "memory", "args": {}}],
        "active_model": "test",
    }
    result = act(state, paths=p, llm=None, tools=tools, emit=lambda e: None)
    obs = result["pending_observations"]
    assert len(obs) == 1
    assert obs[0]["content"].startswith("ERROR")
