# exp1dir/tests/test_mcp_registry.py
import json
from pathlib import Path
from backend.paths import HermesPaths
from backend.tools.mcp import McpRegistry


def _write_cfg(root: Path, servers: dict, extra: dict | None = None):
    data = {"model": "alpha", "mcp_servers": servers}
    if extra:
        data.update(extra)
    (root / ".hermes").mkdir(parents=True, exist_ok=True)
    (root / ".hermes" / "config.json").write_text(json.dumps(data), encoding="utf-8")


def _connector(spec):
    if spec.name == "down":
        raise ConnectionError("refused")
    def search(query: str = "") -> str:
        return f"ok:{spec.name}:{query}"
    search.__doc__ = "search"
    return [{"name": "search", "fn": search, "description": "search"}]


def test_registry_skips_disabled_failed_and_collisions(tmp_path: Path):
    _write_cfg(
        tmp_path,
        {
            "web": {"url": "https://x/mcp"},
            "off": {"url": "https://y/mcp", "enabled": False},
            "down": {"url": "https://z/mcp"},
        },
    )

    def connector(spec):
        if spec.name == "down":
            raise ConnectionError("refused")
        if spec.name == "off":
            raise AssertionError("disabled server must not be connected")

        def a(q: str = "") -> str:
            return "a"

        def b(q: str = "") -> str:
            return "b"

        if spec.name == "web":
            return [
                {"name": "search", "fn": a, "description": "s"},
                {"name": "search", "fn": b, "description": "dup"},
            ]
        return []

    reg = McpRegistry(HermesPaths(root=tmp_path), env={}, connector=connector)
    status = {s["name"]: s for s in reg.reload()["servers"]}
    assert status["web"]["connected"] is True
    assert "web__search" in status["web"]["tools"]
    assert "web__search" in status["web"]["skipped_tools"]
    assert status["off"]["enabled"] is False and status["off"]["connected"] is False
    assert status["down"]["connected"] is False and "refused" in status["down"]["last_error"]
    fns = reg.tool_fns()
    assert fns["web__search"]("hi") == "a"
    assert getattr(fns["web__search"], "_mcp_server") == "web"
    assert getattr(fns["web__search"], "_mcp_tool") == "search"


def test_reload_invalid_json_keeps_previous(tmp_path: Path):
    _write_cfg(tmp_path, {"web": {"url": "https://x/mcp"}})
    reg = McpRegistry(HermesPaths(root=tmp_path), env={}, connector=_connector)
    reg.reload()
    snap = reg.tool_fns()
    (tmp_path / ".hermes" / "config.json").write_text("{bad", encoding="utf-8")
    out = reg.reload()
    assert "invalid JSON" in out["parse_error"]
    assert "web__search" in snap
    assert "web__search" in reg.tool_fns()


def test_tool_fns_snapshot_survives_reload(tmp_path: Path):
    _write_cfg(tmp_path, {"web": {"url": "https://x/mcp"}})
    reg = McpRegistry(HermesPaths(root=tmp_path), env={}, connector=_connector)
    reg.reload()
    snap = reg.tool_fns()
    _write_cfg(tmp_path, {"other": {"url": "https://y/mcp"}})
    reg.reload()
    assert "web__search" in snap
    assert snap["web__search"]("q") == "ok:web:q"
    assert "web__search" not in reg.tool_fns()
    assert "other__search" in reg.tool_fns()
