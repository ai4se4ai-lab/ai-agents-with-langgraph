import json
from pathlib import Path
from backend.llm.ollama import ModelError, list_models, resolve_active, set_active
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_resolve_order_config_then_env_then_first(tmp_path: Path, monkeypatch):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    tags = ["alpha", "beta"]
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert resolve_active(p, tags, env_model="") == "alpha"
    p.config_file.write_text(json.dumps({"model": "beta"}), encoding="utf-8")
    assert resolve_active(p, tags, env_model="alpha") == "beta"
    p.config_file.write_text(json.dumps({"model": "gone"}), encoding="utf-8")
    assert resolve_active(p, tags, env_model="alpha") == "alpha"


def test_set_active_rejects_unknown(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    try:
        set_active(p, "nope", ["alpha"])
        assert False
    except ModelError:
        pass
    set_active(p, "alpha", ["alpha"])
    assert json.loads(p.config_file.read_text(encoding="utf-8"))["model"] == "alpha"


def test_list_models_http(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "llama3.1:latest"}, {"name": "qwen2.5"}]}

    monkeypatch.setattr("backend.llm.ollama.httpx.get", lambda *a, **k: FakeResp())
    assert list_models("http://ollama:11434") == ["llama3.1:latest", "qwen2.5"]
