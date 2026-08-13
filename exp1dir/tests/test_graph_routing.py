from pathlib import Path
from backend.agent.graph import build_graph, run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_tool_then_final_answer(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="I will list", tool_calls=[ToolCall(id="1", name="list_dir", args={"path": "."})]),
            LLMResponse(content="workspace is empty", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    events = []
    result = run_task(p, llm, "list the workspace", on_event=events.append)
    steps = [e["step"] for e in events]
    assert steps.count("reason") >= 2
    assert "act" in steps and "observe" in steps
    assert "success" in steps
    assert result["status"] == "success"
    assert "empty" in result["final_answer"].lower() or "workspace" in result["final_answer"].lower()


def test_cycle_cap(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    forever = LLMResponse(content="loop", tool_calls=[ToolCall(id="1", name="list_dir", args={"path": "."})])
    llm = ScriptedLLM([forever] * 20 + [LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[])])
    result = run_task(p, llm, "loop forever", max_cycles=3, on_event=lambda e: None)
    assert result["status"] == "capped"
    assert result["cycle"] >= 3
