import json
from pathlib import Path
from backend.agent.graph import run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.agent.run_manager import RunManager
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.mcp import McpRegistry
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


def test_run_manager_snapshots_mcp_tools(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    p.config_file.write_text(
        json.dumps({"mcp_servers": {"web": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )

    def connector(spec):
        def search(query: str = "") -> str:
            return f"ok:{query}"
        search.__doc__ = "search"
        return [{"name": "search", "fn": search, "description": "search"}]

    mcp = McpRegistry(p, env={}, connector=connector)
    mcp.reload()
    llm = ScriptedLLM(
        [
            LLMResponse(content="go", tool_calls=[ToolCall(id="1", name="web__search", args={"query": "hi"})]),
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    mgr = RunManager(p, llm, mcp=mcp)
    run_id = mgr.start("search hi")
    result = mgr.join(run_id, timeout=15)
    acts = [e for e in mgr.runs[run_id]["events"] if e.get("step") == "act"]
    assert result["status"] == "success"
    assert acts and acts[0]["mcp_server"] == "web"
    assert any("ok:hi" in (e.get("observation") or "") for e in mgr.runs[run_id]["events"])
