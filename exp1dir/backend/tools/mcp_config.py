from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

BUILTIN_TOOL_NAMES = frozenset(
    {
        "read_file",
        "write_file",
        "list_dir",
        "shell",
        "web_fetch",
        "memory",
        "skill_manage",
        "load_skill",
        "search_sessions",
    }
)

_VAR = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}|\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def read_config(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {}, f"invalid JSON: {e}"
    if not isinstance(data, dict):
        return {}, "config.json must be an object"
    return data, ""


def expand_vars(value, env: dict[str, str]):
    if isinstance(value, str):
        def repl(m):
            name = m.group(1) or m.group(2)
            return env.get(name, m.group(0))
        return _VAR.sub(repl, value)
    if isinstance(value, list):
        return [expand_vars(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_vars(v, env) for k, v in value.items()}
    return value


def _ident(s: str) -> str:
    out = [(ch if ch.isalnum() or ch in "_-" else "_") for ch in s]
    return "".join(out) or "tool"


def flatten_tool_name(server: str, tool: str) -> str:
    return f"{_ident(server)}__{_ident(tool)}"


@dataclass
class ServerSpec:
    name: str
    transport: str = ""
    enabled: bool = True
    command: str | None = None
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)
    url: str | None = None
    headers: dict = field(default_factory=dict)
    timeout: float = 60.0
    error: str = ""


def parse_mcp_servers(data: dict, env: dict[str, str]) -> list[ServerSpec]:
    raw = data.get("mcp_servers") or {}
    if not isinstance(raw, dict):
        return []
    out = []
    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            out.append(ServerSpec(name=str(name), error="server config must be an object"))
            continue
        cfg = expand_vars(cfg, env)
        enabled = cfg.get("enabled", True)
        command = cfg.get("command") or None
        url = cfg.get("url") or None
        args = cfg.get("args") or []
        env_map = cfg.get("env") or {}
        headers = cfg.get("headers") or {}
        timeout = float(cfg.get("timeout", 60))
        spec = ServerSpec(
            name=str(name),
            enabled=bool(enabled),
            command=command,
            args=list(args) if isinstance(args, list) else [],
            env=dict(env_map) if isinstance(env_map, dict) else {},
            url=url,
            headers=dict(headers) if isinstance(headers, dict) else {},
            timeout=timeout,
        )
        if command and url:
            spec.error = "set command (stdio) or url (http), not both"
        elif command:
            spec.transport = "stdio"
        elif url:
            spec.transport = "http"
        else:
            spec.error = "missing command or url"
        out.append(spec)
    return out
