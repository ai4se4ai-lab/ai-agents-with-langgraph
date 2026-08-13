# exp1dir/tests/test_mcp_gateway.py
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
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


def _connector(spec):
    def search(query: str = "") -> str:
        return f"ok:{spec.name}:{query}"
    search.__doc__ = "search"
    return [{"name": "search", "fn": search, "description": "search"}]


def _app(tmp_path, monkeypatch, llm=None):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])
    paths = HermesPaths(root=tmp_path)
    app = create_app(paths, llm=llm or ScriptedLLM([]), settings=SETTINGS)
    app.state.mcp.connector = _connector
    app.state.mcp.reload()
    return app, paths


def test_get_mcp_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])
    app = create_app(HermesPaths(root=tmp_path), llm=ScriptedLLM([]), settings=SETTINGS)
    assert TestClient(app).get("/mcp").json()["servers"] == []


def test_reload_picks_up_config_edit(tmp_path: Path, monkeypatch):
    app, paths = _app(tmp_path, monkeypatch)
    c = TestClient(app)
    paths.config_file.write_text(
        json.dumps({"model": "alpha", "mcp_servers": {"web": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )
    body = c.post("/mcp/reload").json()
    names = [s["name"] for s in body["servers"]]
    assert "web" in names
    web = next(s for s in body["servers"] if s["name"] == "web")
    assert web["connected"] is True
    assert "web__search" in web["tools"]


def test_enable_disable_persists(tmp_path: Path, monkeypatch):
    app, paths = _app(tmp_path, monkeypatch)
    paths.config_file.write_text(
        json.dumps({"model": "alpha", "mcp_servers": {"web": {"url": "https://x/mcp", "enabled": True}}}),
        encoding="utf-8",
    )
    c = TestClient(app)
    c.post("/mcp/reload")
    off = c.post("/mcp/web/enabled", json={"enabled": False})
    assert off.status_code == 200
    data = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert data["model"] == "alpha"
    assert data["mcp_servers"]["web"]["enabled"] is False
    web = next(s for s in off.json()["servers"] if s["name"] == "web")
    assert web["enabled"] is False and web["connected"] is False
    missing = c.post("/mcp/nope/enabled", json={"enabled": True})
    assert missing.status_code == 404


def test_run_uses_mcp_tool(tmp_path: Path, monkeypatch):
    llm = ScriptedLLM(
        [
            LLMResponse(content="go", tool_calls=[ToolCall(id="1", name="web__search", args={"query": "hi"})]),
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    app, paths = _app(tmp_path, monkeypatch, llm=llm)
    paths.config_file.write_text(
        json.dumps({"mcp_servers": {"web": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )
    c = TestClient(app)
    c.post("/mcp/reload")
    run_id = c.post("/runs", json={"task": "search hi"}).json()["run_id"]
    app.state.mgr.join(run_id, timeout=15)
    acts = [e for e in app.state.mgr.runs[run_id]["events"] if e.get("step") == "act"]
    assert acts and acts[0]["mcp_server"] == "web"
