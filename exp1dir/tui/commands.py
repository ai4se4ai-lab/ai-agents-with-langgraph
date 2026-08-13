COMMANDS = [
    {"name": "model", "help": "List or switch Ollama models"},
    {"name": "memory", "help": "Show frozen memory snapshot"},
    {"name": "skills", "help": "List skills"},
    {"name": "interrupt", "help": "Stop current act and wait to redirect"},
    {"name": "history", "help": "Past runs"},
    {"name": "quit", "help": "Exit"},
]


def parse_command(text: str):
    if not text.startswith("/"):
        return None
    parts = text[1:].strip().split()
    if not parts:
        return None
    return parts[0], parts[1:]
