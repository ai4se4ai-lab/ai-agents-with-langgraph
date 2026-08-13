from langchain_core.tools import tool
from backend.tools.registry import build_tool_fns


def langchain_tools(paths):
    fns = build_tool_fns(paths)

    @tool
    def read_file(path: str) -> str:
        """Read a file under the workspace."""
        return fns["read_file"](path)

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a file under the workspace."""
        return fns["write_file"](path, content)

    @tool
    def list_dir(path: str = ".") -> str:
        """List a directory under the workspace."""
        return fns["list_dir"](path)

    @tool
    def shell(command: str) -> str:
        """Run a shell command in the workspace. Do not use curl/wget; use web_fetch for HTTP."""
        return fns["shell"](command)

    @tool
    def web_fetch(url: str) -> str:
        """HTTP GET a URL and return text."""
        return fns["web_fetch"](url)

    @tool
    def memory(action: str, target: str, text: str = "", old_text: str = "") -> str:
        """add/replace/remove long-term memory. target is MEMORY or USER."""
        return fns["memory"](action, target, text, old_text)

    @tool
    def skill_manage(action: str, name: str, description: str = "", body: str = "") -> str:
        """create/update/delete a skill."""
        return fns["skill_manage"](action, name, description, body)

    @tool
    def load_skill(name: str) -> str:
        """Load a skill body into context."""
        return fns["load_skill"](name)

    @tool
    def search_sessions(query: str) -> str:
        """Search past runs."""
        return fns["search_sessions"](query)

    return [read_file, write_file, list_dir, shell, web_fetch, memory, skill_manage, load_skill, search_sessions]
