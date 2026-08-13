from backend.memory.sessions import SessionStore
from backend.memory.store import MemoryStore
from backend.paths import HermesPaths
from backend.tools.files import list_dir, read_file, write_file
from backend.tools.memory_tool import memory_tool
from backend.tools.sessions_tool import search_sessions
from backend.tools.shell import run_shell
from backend.tools.skill_tool import load_skill, skill_manage
from backend.tools.web import web_fetch


def build_tool_fns(paths: HermesPaths) -> dict:
    mem = MemoryStore(paths)
    sessions = SessionStore(paths)

    def _memory(action: str, target: str, text: str = "", old_text: str = "") -> str:
        return memory_tool(mem, action, target, text, old_text)

    def _skill_manage(action: str, name: str, description: str = "", body: str = "") -> str:
        return skill_manage(paths, action, name, description, body)

    def _load_skill(name: str) -> str:
        return load_skill(paths, name)

    def _search(query: str) -> str:
        return search_sessions(sessions, query)

    return {
        "read_file": lambda path: read_file(paths, path),
        "write_file": lambda path, content: write_file(paths, path, content),
        "list_dir": lambda path=".": list_dir(paths, path),
        "shell": lambda command: run_shell(paths, command),
        "web_fetch": lambda url: web_fetch(url),
        "memory": _memory,
        "skill_manage": _skill_manage,
        "load_skill": _load_skill,
        "search_sessions": _search,
    }
