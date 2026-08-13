from tui.commands import COMMANDS, parse_command
from backend.tools.mcp import format_mcp_status


def test_command_table():
    names = {c["name"] for c in COMMANDS}
    assert {"model", "memory", "skills", "interrupt", "history", "quit", "mcp"} <= names


def test_parse_model():
    assert parse_command("/model") == ("model", [])
    assert parse_command("/model llama3.1") == ("model", ["llama3.1"])
    assert parse_command("not a command") is None


def test_parse_mcp():
    assert parse_command("/mcp") == ("mcp", [])
    assert parse_command("/mcp reload") == ("mcp", ["reload"])
    assert parse_command("/mcp enable web") == ("mcp", ["enable", "web"])
    assert parse_command("/mcp disable web") == ("mcp", ["disable", "web"])


def test_format_mcp_status():
    text = format_mcp_status({
        "parse_error": "",
        "servers": [{
            "name": "web", "transport": "http", "enabled": True,
            "connected": True, "tools": ["web__search"], "skipped_tools": [], "last_error": "",
        }],
    })
    assert "web" in text and "connected=true" in text
