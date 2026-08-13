from pathlib import Path
from backend.tools.mcp_config import (
    BUILTIN_TOOL_NAMES,
    expand_vars,
    flatten_tool_name,
    parse_mcp_servers,
    read_config,
)


def test_read_config_missing(tmp_path: Path):
    data, err = read_config(tmp_path / "config.json")
    assert data == {} and err == ""


def test_read_config_invalid_json(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    data, err = read_config(p)
    assert data == {} and "invalid JSON" in err


def test_expand_vars_and_env_prefix():
    env = {"FIRECRAWL_API_KEY": "secret", "TOKEN": "t"}
    assert expand_vars("Bearer ${FIRECRAWL_API_KEY}", env) == "Bearer secret"
    assert expand_vars("Bearer ${env:TOKEN}", env) == "Bearer t"
    assert expand_vars("${MISSING}", env) == "${MISSING}"
    assert expand_vars({"Authorization": "Bearer ${TOKEN}"}, env) == {"Authorization": "Bearer t"}


def test_parse_stdio_http_disabled_and_invalid():
    raw = {
        "mcp_servers": {
            "fs": {"command": "npx", "args": ["-y", "x"], "enabled": False},
            "web": {"url": "https://example/mcp", "headers": {"Authorization": "Bearer ${K}"}},
            "bad": {"command": "npx", "url": "http://x"},
            "empty": {},
        }
    }
    specs = parse_mcp_servers(raw, {"K": "abc"})
    by = {s.name: s for s in specs}
    assert by["fs"].transport == "stdio" and by["fs"].enabled is False
    assert by["web"].transport == "http" and by["web"].headers["Authorization"] == "Bearer abc"
    assert by["web"].enabled is True
    assert by["bad"].error
    assert by["empty"].error


def test_flatten_and_builtins():
    assert flatten_tool_name("firecrawl", "search") == "firecrawl__search"
    assert flatten_tool_name("a b", "x.y") == "a_b__x_y"
    assert "web_fetch" in BUILTIN_TOOL_NAMES
    assert "shell" in BUILTIN_TOOL_NAMES
