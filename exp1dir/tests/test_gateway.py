import time
from pathlib import Path
from fastapi.testclient import TestClient
from backend.agent.llm_port import LLMResponse, ScriptedLLM
from backend.api.app import create_app
from backend.paths import HermesPaths


SETTINGS = {
    "ollama_base_url": "http://x",
    "ollama_api_key": "",
    "ollama_model": "alpha",
    "gateway_host": "127.0.0.1",
    "gateway_port": 8765,
    "skip_ollama": True,
}


def test_health_and_models(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha", "beta"])
    app = create_app(HermesPaths(root=tmp_path), llm=ScriptedLLM([]), settings={**SETTINGS, "ollama_model": ""})
    c = TestClient(app)
    h = c.get("/health").json()
    assert h["active_model"] in ("alpha", "beta")
    assert c.get("/models").json()["models"] == ["alpha", "beta"]
    bad = c.post("/models/active", json={"model": "nope"})
    assert bad.status_code == 400
    ok = c.post("/models/active", json={"model": "beta"})
    assert ok.json()["model"] == "beta"


def test_run_events_and_two_clients(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])
    llm = ScriptedLLM(
        [
            LLMResponse(content="hello", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    app = create_app(HermesPaths(root=tmp_path), llm=llm, settings=SETTINGS)
    c = TestClient(app)
    run_id = c.post("/runs", json={"task": "say hello"}).json()["run_id"]
    app.state.mgr.join(run_id, timeout=15)
    def collect(ws):
        steps = []
        while True:
            try:
                steps.append(ws.receive_json()["step"])
            except Exception:
                break
        return steps
    with c.websocket_connect(f"/ws/runs/{run_id}") as ws1:
        steps1 = collect(ws1)
    with c.websocket_connect(f"/ws/runs/{run_id}") as ws2:
        steps2 = collect(ws2)
    assert "success" in steps1 and "success" in steps2


def test_ws_stays_open_while_llm_thinks(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])

    class SlowLLM:
        def __init__(self):
            self.i = 0

        def invoke(self, messages, tools):
            self.i += 1
            if self.i == 1:
                time.sleep(1.0)
                return LLMResponse(content="hello", tool_calls=[])
            return LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[])

    app = create_app(HermesPaths(root=tmp_path), llm=SlowLLM(), settings=SETTINGS)
    c = TestClient(app)
    run_id = c.post("/runs", json={"task": "my name is Majid Babaei remember this"}).json()["run_id"]
    with c.websocket_connect(f"/ws/runs/{run_id}") as ws:
        steps = []
        while True:
            try:
                steps.append(ws.receive_json()["step"])
            except Exception:
                break
            if "memory_update" in steps:
                break
    app.state.mgr.join(run_id, timeout=15)
    assert "reason" in steps
    assert "success" in steps
