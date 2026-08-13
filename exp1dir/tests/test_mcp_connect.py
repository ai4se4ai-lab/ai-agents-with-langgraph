import time
from pydantic import BaseModel, Field
from backend.tools.mcp_config import ServerSpec
from backend.tools.mcp_connect import connection_for_spec, connect_server


class SearchArgs(BaseModel):
    query: str = Field(description="search query")
    limit: int = Field(default=5)


class FakeTool:
    name = "search"
    description = "s"
    args_schema = SearchArgs

    def invoke(self, kwargs):
        return "ok"


class HungTool:
    name = "slow"
    description = "s"
    args_schema = None

    def invoke(self, kwargs):
        time.sleep(2)


class FakeClient:
    tools = [FakeTool()]

    def __init__(self, servers):
        pass

    async def get_tools(self, server_name=None):
        return list(self.tools)


def test_connection_for_stdio():
    spec = ServerSpec(name="fs", transport="stdio", command="npx", args=["-y", "pkg"], env={"A": "1"}, timeout=30)
    cfg = connection_for_spec(spec)
    assert cfg["transport"] == "stdio"
    assert cfg["command"] == "npx"
    assert cfg["args"] == ["-y", "pkg"]
    assert cfg["env"]["A"] == "1"


def test_connection_for_http():
    spec = ServerSpec(name="web", transport="http", url="https://x/mcp", headers={"Authorization": "Bearer t"}, timeout=45)
    cfg = connection_for_spec(spec)
    assert cfg["transport"] == "streamable_http"
    assert cfg["url"] == "https://x/mcp"
    assert cfg["headers"]["Authorization"] == "Bearer t"


def test_connect_wrappers_copy_args_schema(monkeypatch):
    FakeClient.tools = [FakeTool()]
    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", FakeClient)
    spec = ServerSpec(name="web", transport="http", url="https://x/mcp", timeout=5)
    entries = connect_server(spec)
    fn = entries[0]["fn"]
    assert getattr(fn, "args_schema", None) is SearchArgs


def test_connect_wrapper_does_not_hang_on_timeout(monkeypatch):
    FakeClient.tools = [HungTool()]
    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", FakeClient)
    spec = ServerSpec(name="web", transport="http", url="https://x/mcp", timeout=0.2)
    fn = connect_server(spec)[0]["fn"]
    start = time.monotonic()
    raised = False
    try:
        fn()
    except TimeoutError:
        raised = True
    elapsed = time.monotonic() - start
    assert raised
    assert elapsed < 1.0
