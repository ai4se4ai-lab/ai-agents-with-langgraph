from pydantic import BaseModel, Field
from backend.tools.lc import bindable_tools
from backend.tools.registry import build_tool_fns
from backend.paths import HermesPaths
from backend.memory.store import ensure_home


class SearchArgs(BaseModel):
    query: str = Field(description="search query")
    limit: int = Field(default=5)


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


def test_bindable_tools_preserves_args_schema(tmp_path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)

    def search(**kwargs) -> str:
        """Search."""
        return kwargs.get("query", "")

    search.args_schema = SearchArgs
    search._mcp_server = "web"
    tools = {**build_tool_fns(p), "web__search": search}
    bound = {t.name: t for t in bindable_tools(p, tools)}
    schema = bound["web__search"].args_schema
    js = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema.schema()
    props = js.get("properties") or {}
    assert "query" in props
    assert "kwargs" not in props
