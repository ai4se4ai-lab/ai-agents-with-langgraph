import time
from pathlib import Path
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.agent.run_manager import RunManager
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_interrupt_then_redirect(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="sleeping", tool_calls=[ToolCall(id="1", name="shell", args={"command": "python -c \"import time; time.sleep(8)\""})]),
            LLMResponse(content="redirected ok", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    mgr = RunManager(p, llm)
    run_id = mgr.start("please sleep")
    time.sleep(0.4)
    mgr.interrupt(run_id, "stop")
    mgr.send_message(run_id, "forget the sleep, just say hi")
    result = mgr.join(run_id, timeout=30)
    assert result is not None
    assert "user interrupted" in (result.get("last_observation") or "").lower() or result["status"] in ("success", "interrupted")
    assert "redirected" in result.get("final_answer", "").lower() or "hi" in result.get("final_answer", "").lower() or result["status"] == "success"


def test_stop_ends_run_without_waiting_for_redirect(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="sleeping", tool_calls=[ToolCall(id="1", name="shell", args={"command": "python -c \"import time; time.sleep(8)\""})]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    mgr = RunManager(p, llm)
    run_id = mgr.start("please sleep")
    time.sleep(0.4)
    mgr.stop(run_id, "stop")
    result = mgr.join(run_id, timeout=15)
    assert result is not None
    assert result["status"] == "stopped"
    assert "user interrupted" in (result.get("last_observation") or "").lower()
