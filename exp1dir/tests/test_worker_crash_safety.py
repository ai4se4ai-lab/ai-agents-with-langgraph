from pathlib import Path
import backend.agent.run_manager as run_manager_module
from backend.agent.llm_port import ScriptedLLM
from backend.agent.run_manager import RunManager
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


class _ExplodingGraph:
    def invoke(self, initial_state):
        raise RuntimeError("boom: node exploded")


def test_worker_reports_failure_instead_of_hanging_on_node_crash(tmp_path: Path, monkeypatch):
    """If a graph node raises unexpectedly, the run must end as failed with an
    event emitted, not hang forever with status stuck at 'running'."""
    monkeypatch.setattr(run_manager_module, "build_controlled_graph", lambda *a, **k: _ExplodingGraph())

    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    mgr = RunManager(p, ScriptedLLM([]))
    events = []
    mgr.subscribe(events.append)

    run_id = mgr.start("do something")
    result = mgr.join(run_id, timeout=10)

    assert result is not None
    assert result.get("status") == "failed"
    assert mgr.runs[run_id]["status"] == "failed"
    assert any(e.get("step") == "error" for e in events)
