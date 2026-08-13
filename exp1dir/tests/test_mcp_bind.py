from backend.tools.lc import bindable_tools
from backend.tools.registry import build_tool_fns
from backend.paths import HermesPaths
from backend.memory.store import ensure_home


def test_bindable_tools_includes_mcp_extra(tmp_path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)

    def search(query: str = "") -> str:
        """Search the web."""
        return "ok"

    search._mcp_server = "web"
    tools = {**build_tool_fns(p), "web__search": search}
    bound = bindable_tools(p, tools)
    names = [t.name for t in bound]
    assert "list_dir" in names
    assert "web__search" in names
