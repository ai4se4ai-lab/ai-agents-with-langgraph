# exp1dir/backend/tools/mcp.py
from __future__ import annotations
import os
from dataclasses import asdict, dataclass, field
from backend.paths import HermesPaths
from backend.tools.mcp_config import (
    BUILTIN_TOOL_NAMES,
    flatten_tool_name,
    parse_mcp_servers,
    read_config,
)


@dataclass
class ServerStatus:
    name: str
    transport: str
    enabled: bool
    connected: bool
    tools: list[str] = field(default_factory=list)
    skipped_tools: list[str] = field(default_factory=list)
    last_error: str = ""


def _attach(fn, server: str, mcp_tool: str):
    fn._mcp_server = server
    fn._mcp_tool = mcp_tool
    return fn


class McpRegistry:
    def __init__(self, paths: HermesPaths, env: dict | None = None, connector=None):
        self.paths = paths
        self.env = env if env is not None else dict(os.environ)
        self.connector = connector or default_connector
        self._tools: dict = {}
        self._status: list[ServerStatus] = []
        self._parse_error = ""

    def status(self) -> dict:
        return {
            "servers": [asdict(s) for s in self._status],
            "parse_error": self._parse_error,
        }

    def tool_fns(self) -> dict:
        return dict(self._tools)

    def reload(self) -> dict:
        data, err = read_config(self.paths.config_file)
        if err:
            self._parse_error = err
            return self.status()
        self._parse_error = ""
        specs = parse_mcp_servers(data, self.env)
        new_tools: dict = {}
        statuses: list[ServerStatus] = []
        for spec in specs:
            st = ServerStatus(
                name=spec.name,
                transport=spec.transport,
                enabled=spec.enabled,
                connected=False,
                last_error=spec.error,
            )
            if spec.error or not spec.enabled:
                statuses.append(st)
                continue
            try:
                listed = self.connector(spec) or []
            except Exception as e:
                st.last_error = str(e)
                statuses.append(st)
                continue
            st.connected = True
            for item in listed:
                raw_name = item["name"]
                flat = flatten_tool_name(spec.name, raw_name)
                fn = item["fn"]
                if item.get("description") and not getattr(fn, "__doc__", None):
                    fn.__doc__ = item["description"]
                if flat in BUILTIN_TOOL_NAMES or flat in new_tools:
                    st.skipped_tools.append(flat)
                    continue
                new_tools[flat] = _attach(fn, spec.name, raw_name)
                st.tools.append(flat)
            statuses.append(st)
        self._tools = new_tools
        self._status = statuses
        return self.status()


def default_connector(spec):
    raise RuntimeError("MCP connector not wired; pass connector= in tests")
