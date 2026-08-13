from pathlib import Path
from backend.agent.graph import run_task
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


def test_leaves_task_before_llm_returns(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    events = []
    seen_during_llm = {}

    class Probe:
        def invoke(self, messages, tools):
            if "steps" not in seen_during_llm:
                seen_during_llm["steps"] = [e["step"] for e in events]
            if not getattr(self, "n", 0):
                self.n = 1
                return LLMResponse(content="ok", tool_calls=[])
            return LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[])

    run_task(p, Probe(), "my name is Majid Babaei remember this", on_event=events.append)
    assert "task" in seen_during_llm["steps"]
    assert "reason" in seen_during_llm["steps"]


def test_json_text_tool_call_writes_user_memory(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(
                content='```json\n{"name": "memory", "arguments": {"action": "add", "target": "USER", "text": "Majid Babaei"}}\n```',
                tool_calls=[],
            ),
            LLMResponse(content="I'll remember that your name is Majid Babaei.", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    events = []
    result = run_task(p, llm, "my name is Majid Babaei remember this", on_event=events.append)
    assert "Majid Babaei" in p.user_md.read_text(encoding="utf-8")
    assert "act" in [e["step"] for e in events]
    assert result["status"] == "success"
    assert "Majid" in result["final_answer"]
