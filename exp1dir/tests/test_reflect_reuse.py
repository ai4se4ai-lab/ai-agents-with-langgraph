from pathlib import Path
from backend.agent.graph import run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_reflect_writes_memory(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(
                content='{"memory": [{"action": "add", "target": "MEMORY", "text": "project is exp1"}], "skills": []}',
                tool_calls=[],
            ),
        ]
    )
    result = run_task(p, llm, "remember this is exp1")
    assert "exp1" in p.memory_md.read_text(encoding="utf-8")
    assert result["status"] == "success"


def test_invalid_reflect_json_skips_write(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    before = p.memory_md.read_text(encoding="utf-8")
    llm = ScriptedLLM(
        [
            LLMResponse(content="answer", tool_calls=[]),
            LLMResponse(content="not json", tool_calls=[]),
        ]
    )
    result = run_task(p, llm, "say hi")
    assert result["final_answer"] == "answer"
    assert p.memory_md.read_text(encoding="utf-8") == before


def test_reuse_on_second_run(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm1 = ScriptedLLM(
        [
            LLMResponse(content="ok", tool_calls=[]),
            LLMResponse(
                content='{"memory": [{"action": "add", "target": "MEMORY", "text": "the secret code is 42"}], "skills": []}',
                tool_calls=[],
            ),
        ]
    )
    run_task(p, llm1, "remember the code")
    captured = {}

    class Capture(ScriptedLLM):
        def invoke(self, messages, tools):
            captured["sys"] = messages[0]["content"]
            return super().invoke(messages, tools)

    llm2 = Capture(
        [
            LLMResponse(content="the code is 42", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    result = run_task(p, llm2, "what is the secret code?")
    assert "42" in captured["sys"]
    assert "42" in result["final_answer"]
