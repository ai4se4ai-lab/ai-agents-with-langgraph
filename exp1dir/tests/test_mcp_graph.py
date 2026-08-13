from pathlib import Path
from backend.agent.graph import run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.registry import build_tool_fns


def test_mcp_tool_act_observe_event_fields(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)

    def search(query: str = "") -> str:
        return f"hits:{query}"

    search._mcp_server = "web"
    search._mcp_tool = "search"
    tools = {**build_tool_fns(p), "web__search": search}
    llm = ScriptedLLM(
        [
            LLMResponse(content="search", tool_calls=[ToolCall(id="1", name="web__search", args={"query": "paris"})]),
            LLMResponse(content="paris is fine", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    events = []
    result = run_task(p, llm, "weather in paris", on_event=events.append, tools=tools)
    acts = [e for e in events if e["step"] == "act"]
    assert acts and acts[0]["mcp_server"] == "web" and acts[0]["mcp_tool"] == "search"
    assert acts[0]["tool"] == "web__search"
    obs = [e for e in events if e["step"] == "observe"]
    assert any("hits:paris" in (e.get("observation") or "") for e in obs)
    assert result["status"] == "success"
