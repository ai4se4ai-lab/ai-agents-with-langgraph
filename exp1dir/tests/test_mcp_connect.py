from backend.tools.mcp_config import ServerSpec
from backend.tools.mcp_connect import connection_for_spec


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
