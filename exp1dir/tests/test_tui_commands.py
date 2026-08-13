from tui.commands import COMMANDS, parse_command


def test_command_table():
    names = {c["name"] for c in COMMANDS}
    assert {"model", "memory", "skills", "interrupt", "history", "quit"} <= names


def test_parse_model():
    assert parse_command("/model") == ("model", [])
    assert parse_command("/model llama3.1") == ("model", ["llama3.1"])
    assert parse_command("not a command") is None
