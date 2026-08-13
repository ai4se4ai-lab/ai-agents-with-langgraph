from pathlib import Path
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.shell import run_shell
from backend.tools.web import web_fetch


def test_shell_echo(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    out = run_shell(p, "python -c \"print('hi')\"", timeout=10)
    assert "hi" in out
    assert "exit=" in out


def test_shell_timeout(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    out = run_shell(p, "python -c \"import time; time.sleep(5)\"", timeout=0.2)
    assert "timeout" in out.lower()


def test_web_fetch_mocked(monkeypatch, tmp_path: Path):
    class FakeResp:
        status_code = 200
        text = "<html><body><p>Hello</p></body></html>"
        headers = {"content-type": "text/html"}

    def fake_get(*args, **kwargs):
        return FakeResp()

    monkeypatch.setattr("backend.tools.web.httpx.get", fake_get)
    out = web_fetch("http://example.com")
    assert "Hello" in out


def test_web_fetch_caps_and_errors(monkeypatch):
    class FakeResp:
        status_code = 404
        text = "missing"
        headers = {"content-type": "text/plain"}

    monkeypatch.setattr("backend.tools.web.httpx.get", lambda *a, **k: FakeResp())
    out = web_fetch("http://example.com/nope")
    assert "404" in out
