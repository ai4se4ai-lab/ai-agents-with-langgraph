# exp1 MCP Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users add and update MCP servers in `exp1dir/.hermes/config.json`, expose their tools as `server__tool` in the existing Reason ⇄ Act ⇄ Observe loop, and show which MCP the agent used in the React UI.

**Architecture:** Parse `mcp_servers` from config.json. `McpRegistry` uses a connector (fake in tests; `MultiServerMCPClient` in production) to list tools from enabled stdio and Streamable HTTP servers, registers callables with `_mcp_server` / `_mcp_tool` attributes, and snapshots them into the run’s tools dict. Act emits `mcp_server` / `mcp_tool`. TUI `/mcp` and `GET /mcp` expose status. React labels Act and marks used servers.

**Tech Stack:** Existing exp1 stack plus `langchain-mcp-adapters` and `mcp`. Tests use a fake connector (no live MCP, no `npx`).

**Spec:** `docs/superpowers/specs/2026-08-13-exp1-mcp-support-design.md`

**Working directory for all pytest commands:** `exp1dir/` with `.venv` activated (`python -m pytest …`).

---

## File structure (lock this)

```
exp1dir/
  pyproject.toml                          # add langchain-mcp-adapters, mcp
  .env.example                            # commented MCP key example
  README.md                               # how to add/reload MCP
  backend/tools/mcp_config.py             # parse, ${VAR}, flatten names, set_enabled
  backend/tools/mcp.py                    # McpRegistry + default connector
  backend/tools/registry.py               # unchanged API; extra fns merged by callers
  backend/tools/lc.py                     # bindable_tools(dict) for Ollama
  backend/agent/events.py                 # mcp_server, mcp_tool on events
  backend/agent/nodes.py                  # act emits MCP fields
  backend/agent/graph.py                  # run_task(tools=)
  backend/agent/llm_port.py               # bind live tool dict
  backend/agent/prompts.py                # optional MCP tool list in system prompt
  backend/agent/run_manager.py            # snapshot builtin + registry.tool_fns()
  backend/api/app.py                      # GET /mcp, POST reload, POST enabled
  tui/commands.py
  tui/client.py
  tui/app.py
  web/src/mcp.ts                          # actLabel, usedMcps
  web/src/App.tsx
  web/src/index.css
  tests/test_mcp_config.py
  tests/test_mcp_registry.py
  tests/test_mcp_graph.py
  tests/test_mcp_gateway.py
  tests/test_events.py                    # mcp fields default empty
  tests/test_tui_commands.py
  tests/test_graph_map.py                 # mcp.ts helpers exist
docs/exp1-how-the-agent-works.md          # short MCP section
```

Do not add SSE, MCP resources/prompts, a POST-full-server API, file watchers, or a Pick-MCP graph node.

---

### Task 1: Config parse, `${VAR}` expansion, flatten names

**Files:**
- Create: `exp1dir/backend/tools/mcp_config.py`
- Test: `exp1dir/tests/test_mcp_config.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_mcp_config.py
import json
from pathlib import Path
from backend.tools.mcp_config import (
    BUILTIN_TOOL_NAMES,
    expand_vars,
    flatten_tool_name,
    parse_mcp_servers,
    read_config,
)


def test_read_config_missing(tmp_path: Path):
    data, err = read_config(tmp_path / "config.json")
    assert data == {} and err == ""


def test_read_config_invalid_json(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    data, err = read_config(p)
    assert data == {} and "invalid JSON" in err


def test_expand_vars_and_env_prefix():
    env = {"FIRECRAWL_API_KEY": "secret", "TOKEN": "t"}
    assert expand_vars("Bearer ${FIRECRAWL_API_KEY}", env) == "Bearer secret"
    assert expand_vars("Bearer ${env:TOKEN}", env) == "Bearer t"
    assert expand_vars("${MISSING}", env) == "${MISSING}"
    assert expand_vars({"Authorization": "Bearer ${TOKEN}"}, env) == {"Authorization": "Bearer t"}


def test_parse_stdio_http_disabled_and_invalid():
    raw = {
        "mcp_servers": {
            "fs": {"command": "npx", "args": ["-y", "x"], "enabled": False},
            "web": {"url": "https://example/mcp", "headers": {"Authorization": "Bearer ${K}"}},
            "bad": {"command": "npx", "url": "http://x"},
            "empty": {},
        }
    }
    specs = parse_mcp_servers(raw, {"K": "abc"})
    by = {s.name: s for s in specs}
    assert by["fs"].transport == "stdio" and by["fs"].enabled is False
    assert by["web"].transport == "http" and by["web"].headers["Authorization"] == "Bearer abc"
    assert by["web"].enabled is True
    assert by["bad"].error
    assert by["empty"].error


def test_flatten_and_builtins():
    assert flatten_tool_name("firecrawl", "search") == "firecrawl__search"
    assert flatten_tool_name("a b", "x.y") == "a_b__x_y"
    assert "web_fetch" in BUILTIN_TOOL_NAMES
    assert "shell" in BUILTIN_TOOL_NAMES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mcp_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.tools.mcp_config'`

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/tools/mcp_config.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mcp_config.py -v`

Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/mcp_config.py exp1dir/tests/test_mcp_config.py
git commit -m "feat(exp1): parse mcp_servers from config.json"
```

---

### Task 2: Persist enable/disable without dropping other keys

**Files:**
- Modify: `exp1dir/backend/tools/mcp_config.py`
- Modify: `exp1dir/tests/test_mcp_config.py`

- [ ] **Step 1: Write the failing test** (append to `test_mcp_config.py`)

```python
from backend.tools.mcp_config import set_server_enabled


def test_set_server_enabled_preserves_model_and_others(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(
        json.dumps(
            {
                "model": "alpha",
                "mcp_servers": {
                    "web": {"url": "https://x/mcp", "enabled": True},
                    "fs": {"command": "npx", "args": ["x"]},
                },
            }
        ),
        encoding="utf-8",
    )
    set_server_enabled(p, "web", False)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["model"] == "alpha"
    assert data["mcp_servers"]["web"]["enabled"] is False
    assert data["mcp_servers"]["web"]["url"] == "https://x/mcp"
    assert "fs" in data["mcp_servers"]


def test_set_server_enabled_unknown(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"mcp_servers": {"web": {"url": "https://x"}}}), encoding="utf-8")
    try:
        set_server_enabled(p, "nope", True)
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mcp_config.py::test_set_server_enabled_preserves_model_and_others -v`

Expected: FAIL with `ImportError` or `set_server_enabled` not defined

- [ ] **Step 3: Write minimal implementation** (append to `mcp_config.py`)

```python
class UnknownMcpServer(KeyError):
    pass


def write_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def set_server_enabled(path: Path, name: str, enabled: bool) -> dict:
    data, err = read_config(path)
    if err:
        raise ValueError(err)
    servers = data.setdefault("mcp_servers", {})
    if name not in servers or not isinstance(servers[name], dict):
        raise UnknownMcpServer(name)
    servers[name]["enabled"] = bool(enabled)
    write_config(path, data)
    return data
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_mcp_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/mcp_config.py exp1dir/tests/test_mcp_config.py
git commit -m "feat(exp1): persist MCP enabled flag in config.json"
```

---

### Task 3: McpRegistry with fake connector

**Files:**
- Create: `exp1dir/backend/tools/mcp.py`
- Test: `exp1dir/tests/test_mcp_registry.py`

The registry must:

- Skip disabled and invalid specs
- Connect enabled servers via `connector(spec) -> list[{name, fn, description}]`
- On connector exception: `connected=False`, `last_error`, do not block other servers
- Flatten names; skip collisions with builtins and already-registered names; record `skipped_tools`
- `tool_fns()` returns a **new dict** each call (reload replaces internal map; snapshots stay stable)
- Invalid JSON: keep previous map, set `parse_error`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_mcp_registry.py
import json
from pathlib import Path
from backend.paths import HermesPaths
from backend.tools.mcp import McpRegistry


def _write_cfg(root: Path, servers: dict, extra: dict | None = None):
    data = {"model": "alpha", "mcp_servers": servers}
    if extra:
        data.update(extra)
    (root / ".hermes").mkdir(parents=True, exist_ok=True)
    (root / ".hermes" / "config.json").write_text(json.dumps(data), encoding="utf-8")


def _connector(spec):
    if spec.name == "down":
        raise ConnectionError("refused")
    def search(query: str = "") -> str:
        return f"ok:{spec.name}:{query}"
    search.__doc__ = "search"
    return [{"name": "search", "fn": search, "description": "search"}]


def test_registry_skips_disabled_failed_and_collisions(tmp_path: Path):
    _write_cfg(
        tmp_path,
        {
            "web": {"url": "https://x/mcp"},
            "off": {"url": "https://y/mcp", "enabled": False},
            "down": {"url": "https://z/mcp"},
        },
    )

    def connector(spec):
        if spec.name == "down":
            raise ConnectionError("refused")
        if spec.name == "off":
            raise AssertionError("disabled server must not be connected")

        def a(q: str = "") -> str:
            return "a"

        def b(q: str = "") -> str:
            return "b"

        if spec.name == "web":
            return [
                {"name": "search", "fn": a, "description": "s"},
                {"name": "search", "fn": b, "description": "dup"},
            ]
        return []

    reg = McpRegistry(HermesPaths(root=tmp_path), env={}, connector=connector)
    status = {s["name"]: s for s in reg.reload()["servers"]}
    assert status["web"]["connected"] is True
    assert "web__search" in status["web"]["tools"]
    assert "web__search" in status["web"]["skipped_tools"]
    assert status["off"]["enabled"] is False and status["off"]["connected"] is False
    assert status["down"]["connected"] is False and "refused" in status["down"]["last_error"]
    fns = reg.tool_fns()
    assert fns["web__search"]("hi") == "a"
    assert getattr(fns["web__search"], "_mcp_server") == "web"
    assert getattr(fns["web__search"], "_mcp_tool") == "search"


def test_reload_invalid_json_keeps_previous(tmp_path: Path):
    _write_cfg(tmp_path, {"web": {"url": "https://x/mcp"}})
    reg = McpRegistry(HermesPaths(root=tmp_path), env={}, connector=_connector)
    reg.reload()
    snap = reg.tool_fns()
    (tmp_path / ".hermes" / "config.json").write_text("{bad", encoding="utf-8")
    out = reg.reload()
    assert "invalid JSON" in out["parse_error"]
    assert "web__search" in snap
    assert "web__search" in reg.tool_fns()


def test_tool_fns_snapshot_survives_reload(tmp_path: Path):
    _write_cfg(tmp_path, {"web": {"url": "https://x/mcp"}})
    reg = McpRegistry(HermesPaths(root=tmp_path), env={}, connector=_connector)
    reg.reload()
    snap = reg.tool_fns()
    _write_cfg(tmp_path, {"other": {"url": "https://y/mcp"}})
    reg.reload()
    assert "web__search" in snap
    assert snap["web__search"]("q") == "ok:web:q"
    assert "web__search" not in reg.tool_fns()
    assert "other__search" in reg.tool_fns()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mcp_registry.py -v`

Expected: FAIL with `ModuleNotFoundError: backend.tools.mcp`

- [ ] **Step 3: Write `McpRegistry`**

```python
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
```

Task 10 replaces `default_connector` with the real adapter.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_mcp_registry.py tests/test_mcp_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/mcp.py exp1dir/tests/test_mcp_registry.py
git commit -m "feat(exp1): MCP registry with snapshot tool map"
```

---

### Task 4: Act events carry `mcp_server` / `mcp_tool`; graph runs an MCP tool

**Files:**
- Modify: `exp1dir/backend/agent/events.py`
- Modify: `exp1dir/backend/agent/nodes.py` (`act`)
- Modify: `exp1dir/backend/agent/graph.py` (`run_task` accept `tools=`)
- Modify: `exp1dir/tests/test_events.py`
- Create: `exp1dir/tests/test_mcp_graph.py`

- [ ] **Step 1: Write failing tests**

Append to `test_events.py`:

```python
def test_make_event_includes_mcp_fields():
    e = make_event("r", "act", tool="web__search")
    assert e["mcp_server"] == ""
    assert e["mcp_tool"] == ""
    e2 = make_event("r", "act", tool="web__search", mcp_server="web", mcp_tool="search")
    assert e2["mcp_server"] == "web" and e2["mcp_tool"] == "search"
```

Create `tests/test_mcp_graph.py`:

```python
from pathlib import Path
from backend.agent.graph import run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.registry import build_tool_fns


def test_mcp_tool_act_observe_event_fields(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)

    def search(query: str = "") -> str:
        return f"hits:{query}"

    search._mcp_server = "web"
    search._mcp_tool = "search"
    tools = {**build_tool_fns(p), "web__search": search}
    llm = ScriptedLLM(
        [
            LLMResponse(content="search", tool_calls=[ToolCall(id="1", name="web__search", args={"query": "paris"})]),
            LLMResponse(content="paris is fine", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    events = []
    result = run_task(p, llm, "weather in paris", on_event=events.append, tools=tools)
    acts = [e for e in events if e["step"] == "act"]
    assert acts and acts[0]["mcp_server"] == "web" and acts[0]["mcp_tool"] == "search"
    assert acts[0]["tool"] == "web__search"
    obs = [e for e in events if e["step"] == "observe"]
    assert any("hits:paris" in (e.get("observation") or "") for e in obs)
    assert result["status"] == "success"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_events.py::test_make_event_includes_mcp_fields tests/test_mcp_graph.py -v`

Expected: FAIL (`mcp_server` unexpected kwarg and/or `run_task() got unexpected keyword argument 'tools'`)

- [ ] **Step 3: Implement**

`make_event` in `events.py` — add `mcp_server: str = ""`, `mcp_tool: str = ""` and include them in the returned dict.

`act` in `nodes.py` — after resolving `fn`:

```python
mcp_server = getattr(fn, "_mcp_server", "") if fn is not None else ""
mcp_tool = getattr(fn, "_mcp_tool", "") if fn is not None else ""
emit(make_event(
    state["run_id"], "act", cycle=state["cycle"], tool=name,
    input=json.dumps(args), model=state.get("active_model", ""),
    mcp_server=mcp_server, mcp_tool=mcp_tool,
))
```

Move the existing `emit(...)` that currently happens **before** `fn = tools.get(name)` to **after** lookup so attributes are available. Keep emit-before-execution so the UI still lights Act first: look up `fn` first, then emit, then execute.

`graph.py` `run_task`:

```python
def run_task(paths, llm, task: str, max_cycles: int = 15, on_event=None, model: str = "scripted", tools=None):
    ...
    graph = build_graph(paths, llm, emit, tools=tools)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_events.py tests/test_mcp_graph.py tests/test_graph_routing.py -v`

Expected: PASS (existing routing tests still pass)

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/agent/events.py exp1dir/backend/agent/nodes.py exp1dir/backend/agent/graph.py exp1dir/tests/test_events.py exp1dir/tests/test_mcp_graph.py
git commit -m "feat(exp1): emit mcp_server on act events"
```

---

### Task 5: Snapshot MCP tools at run start (RunManager)

**Files:**
- Modify: `exp1dir/backend/agent/run_manager.py`
- Modify: `exp1dir/backend/api/app.py` (construct registry, pass into RunManager)
- Test: `exp1dir/tests/test_mcp_graph.py` (append RunManager test)

- [ ] **Step 1: Write the failing test** (append to `test_mcp_graph.py`)

```python
import json
from backend.agent.run_manager import RunManager
from backend.tools.mcp import McpRegistry


def test_run_manager_snapshots_mcp_tools(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    p.config_file.write_text(
        json.dumps({"mcp_servers": {"web": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )

    def connector(spec):
        def search(query: str = "") -> str:
            return f"ok:{query}"
        search.__doc__ = "search"
        return [{"name": "search", "fn": search, "description": "search"}]

    mcp = McpRegistry(p, env={}, connector=connector)
    mcp.reload()
    llm = ScriptedLLM(
        [
            LLMResponse(content="go", tool_calls=[ToolCall(id="1", name="web__search", args={"query": "hi"})]),
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    mgr = RunManager(p, llm, mcp=mcp)
    run_id = mgr.start("search hi")
    result = mgr.join(run_id, timeout=15)
    acts = [e for e in mgr.runs[run_id]["events"] if e.get("step") == "act"]
    assert result["status"] == "success"
    assert acts and acts[0]["mcp_server"] == "web"
    assert any("ok:hi" in (e.get("observation") or "") for e in mgr.runs[run_id]["events"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mcp_graph.py::test_run_manager_snapshots_mcp_tools -v`

Expected: FAIL (`RunManager.__init__() got an unexpected keyword argument 'mcp'` or unknown tool `web__search`)

- [ ] **Step 3: Implement RunManager + create_app wiring**

`run_manager.py`:

```python
class RunManager:
    def __init__(self, paths, llm, mcp=None):
        self.paths = paths
        self.llm = llm
        self.mcp = mcp
        self.runs = {}
        self.listeners = []

    def start(self, task: str, model: str = "scripted") -> str:
        ...
        def worker():
            extra = self.mcp.tool_fns() if self.mcp else {}
            tools = {**build_tool_fns(self.paths), **extra}
            graph = build_controlled_graph(self.paths, self.llm, emit, tools, control)
            ...
```

In `create_app`:

```python
from backend.tools.mcp import McpRegistry

def create_app(paths, llm, settings: dict):
    ensure_home(paths)
    mcp = McpRegistry(paths)
    mcp.reload()
    mgr = RunManager(paths, llm, mcp=mcp)
    ...
    app.state.mcp = mcp
```

Do not add `/mcp` routes yet. Empty config → `reload()` registers nothing; existing gateway tests stay green.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_mcp_graph.py tests/test_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/agent/run_manager.py exp1dir/backend/api/app.py exp1dir/tests/test_mcp_graph.py
git commit -m "feat(exp1): snapshot MCP tools when a run starts"
```

---

### Task 6: Gateway `GET /mcp`, `POST /mcp/reload`, `POST /mcp/{name}/enabled`

**Files:**
- Modify: `exp1dir/backend/api/app.py`
- Modify: `exp1dir/tests/test_mcp_gateway.py`

- [ ] **Step 1: Write failing tests** (full `test_mcp_gateway.py`)

```python
# exp1dir/tests/test_mcp_gateway.py
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.api.app import create_app
from backend.paths import HermesPaths
from backend.tools.mcp import McpRegistry

SETTINGS = {
    "ollama_base_url": "http://x",
    "ollama_api_key": "",
    "ollama_model": "alpha",
    "gateway_host": "127.0.0.1",
    "gateway_port": 8765,
    "skip_ollama": True,
}


def _connector(spec):
    def search(query: str = "") -> str:
        return f"ok:{spec.name}:{query}"
    search.__doc__ = "search"
    return [{"name": "search", "fn": search, "description": "search"}]


def _app(tmp_path, monkeypatch, llm=None):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])
    paths = HermesPaths(root=tmp_path)
    app = create_app(paths, llm=llm or ScriptedLLM([]), settings=SETTINGS)
    app.state.mcp.connector = _connector
    app.state.mcp.reload()
    return app, paths


def test_get_mcp_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])
    app = create_app(HermesPaths(root=tmp_path), llm=ScriptedLLM([]), settings=SETTINGS)
    assert TestClient(app).get("/mcp").json()["servers"] == []


def test_reload_picks_up_config_edit(tmp_path: Path, monkeypatch):
    app, paths = _app(tmp_path, monkeypatch)
    c = TestClient(app)
    paths.config_file.write_text(
        json.dumps({"model": "alpha", "mcp_servers": {"web": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )
    body = c.post("/mcp/reload").json()
    names = [s["name"] for s in body["servers"]]
    assert "web" in names
    web = next(s for s in body["servers"] if s["name"] == "web")
    assert web["connected"] is True
    assert "web__search" in web["tools"]


def test_enable_disable_persists(tmp_path: Path, monkeypatch):
    app, paths = _app(tmp_path, monkeypatch)
    paths.config_file.write_text(
        json.dumps({"model": "alpha", "mcp_servers": {"web": {"url": "https://x/mcp", "enabled": True}}}),
        encoding="utf-8",
    )
    c = TestClient(app)
    c.post("/mcp/reload")
    off = c.post("/mcp/web/enabled", json={"enabled": False})
    assert off.status_code == 200
    data = json.loads(paths.config_file.read_text(encoding="utf-8"))
    assert data["model"] == "alpha"
    assert data["mcp_servers"]["web"]["enabled"] is False
    web = next(s for s in off.json()["servers"] if s["name"] == "web")
    assert web["enabled"] is False and web["connected"] is False
    missing = c.post("/mcp/nope/enabled", json={"enabled": True})
    assert missing.status_code == 404


def test_run_uses_mcp_tool(tmp_path: Path, monkeypatch):
    llm = ScriptedLLM(
        [
            LLMResponse(content="go", tool_calls=[ToolCall(id="1", name="web__search", args={"query": "hi"})]),
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    app, paths = _app(tmp_path, monkeypatch, llm=llm)
    paths.config_file.write_text(
        json.dumps({"mcp_servers": {"web": {"url": "https://x/mcp"}}}),
        encoding="utf-8",
    )
    c = TestClient(app)
    c.post("/mcp/reload")
    run_id = c.post("/runs", json={"task": "search hi"}).json()["run_id"]
    app.state.mgr.join(run_id, timeout=15)
    acts = [e for e in app.state.mgr.runs[run_id]["events"] if e.get("step") == "act"]
    assert acts and acts[0]["mcp_server"] == "web"
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_mcp_gateway.py -v`

Expected: FAIL (`404` on `/mcp`)

- [ ] **Step 3: Add routes to `create_app` in `app.py`**

```python
from pydantic import BaseModel
from backend.tools.mcp_config import UnknownMcpServer, set_server_enabled

class McpEnabledIn(BaseModel):
    enabled: bool


# inside create_app, after other routes:

@app.get("/mcp")
def mcp_status():
    return app.state.mcp.status()

@app.post("/mcp/reload")
def mcp_reload():
    return app.state.mcp.reload()

@app.post("/mcp/{name}/enabled")
def mcp_enabled(name: str, body: McpEnabledIn):
    try:
        set_server_enabled(paths.config_file, name, body.enabled)
    except UnknownMcpServer:
        raise HTTPException(404, f"unknown MCP server: {name}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return app.state.mcp.reload()
```

`GET /health` stays unchanged.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_mcp_gateway.py tests/test_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/api/app.py exp1dir/tests/test_mcp_gateway.py
git commit -m "feat(exp1): MCP status, reload, and enable API"
```

---

### Task 7: TUI `/mcp` commands

**Files:**
- Modify: `exp1dir/tui/commands.py`
- Modify: `exp1dir/tui/client.py`
- Modify: `exp1dir/tui/app.py`
- Modify: `exp1dir/tests/test_tui_commands.py`

- [ ] **Step 1: Write failing tests**

```python
# replace test_command_table assertion in test_tui_commands.py
def test_command_table():
    names = {c["name"] for c in COMMANDS}
    assert {"model", "memory", "skills", "interrupt", "history", "quit", "mcp"} <= names


def test_parse_mcp():
    assert parse_command("/mcp") == ("mcp", [])
    assert parse_command("/mcp reload") == ("mcp", ["reload"])
    assert parse_command("/mcp enable web") == ("mcp", ["enable", "web"])
    assert parse_command("/mcp disable web") == ("mcp", ["disable", "web"])
```

Add a pure formatter test in `test_mcp_registry.py` or `test_tui_commands.py`:

```python
from backend.tools.mcp import format_mcp_status

def test_format_mcp_status():
    text = format_mcp_status({
        "parse_error": "",
        "servers": [{
            "name": "web", "transport": "http", "enabled": True,
            "connected": True, "tools": ["web__search"], "skipped_tools": [], "last_error": "",
        }],
    })
    assert "web" in text and "connected=true" in text
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_tui_commands.py -v`

Expected: FAIL (`mcp` not in COMMANDS)

- [ ] **Step 3: Implement**

`commands.py` — add `{"name": "mcp", "help": "List, enable, disable, or reload MCP servers"}`.

`mcp.py` — add:

```python
def format_mcp_status(payload: dict) -> str:
    lines = []
    if payload.get("parse_error"):
        lines.append(f"parse_error: {payload['parse_error']}")
    servers = payload.get("servers") or []
    if not servers:
        lines.append("mcp: (none)")
        return "\n".join(lines)
    for s in servers:
        lines.append(
            f"mcp: {s['name']} transport={s.get('transport') or '-'} "
            f"enabled={str(s.get('enabled')).lower()} connected={str(s.get('connected')).lower()} "
            f"tools={len(s.get('tools') or [])} err={s.get('last_error') or '-'}"
        )
        if s.get("tools"):
            lines.append("  tools: " + ", ".join(s["tools"]))
    return "\n".join(lines)
```

`client.py`:

```python
def mcp(self):
    return self._http.get(f"{self.base}/mcp").json()

def mcp_reload(self):
    r = self._http.post(f"{self.base}/mcp/reload")
    r.raise_for_status()
    return r.json()

def mcp_enabled(self, name: str, enabled: bool):
    r = self._http.post(f"{self.base}/mcp/{name}/enabled", json={"enabled": enabled})
    r.raise_for_status()
    return r.json()
```

`app.py` — in the command branch, before `unknown command`:

```python
if name == "mcp":
    from backend.tools.mcp import format_mcp_status
    try:
        if not args:
            data = self.client.mcp()
        elif args[0] == "reload":
            data = self.client.mcp_reload()
        elif args[0] in ("enable", "disable") and len(args) >= 2:
            data = self.client.mcp_enabled(args[1], args[0] == "enable")
        else:
            log.write_line("usage: /mcp | /mcp reload | /mcp enable <name> | /mcp disable <name>")
            return
        log.write_line(format_mcp_status(data))
    except Exception as e:
        log.write_line(f"mcp error: {e}")
    return
```

Also update Act log line in `_stream`:

```python
if step == "act" and e.get("mcp_server"):
    log.write_line(f"[act] {e['mcp_server']} / {e.get('mcp_tool')} ({e.get('tool')}) {e.get('input') or ''}")
else:
    log.write_line(f"[{step}] {e.get('text') or e.get('observation') or e.get('input') or ''}")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tui_commands.py tests/test_mcp_registry.py tests/test_mcp_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/tui/commands.py exp1dir/tui/client.py exp1dir/tui/app.py exp1dir/backend/tools/mcp.py exp1dir/tests/test_tui_commands.py
git commit -m "feat(exp1): TUI /mcp list enable disable reload"
```

---

### Task 8: Bind the live tool dict in OllamaLLM

**Files:**
- Modify: `exp1dir/backend/tools/lc.py`
- Modify: `exp1dir/backend/agent/llm_port.py`
- Test: `exp1dir/tests/test_mcp_bind.py`

Today `OllamaLLM.invoke` ignores the run’s tools dict and always `bind_tools(langchain_tools(HermesPaths.default()))`, so MCP tools never reach the model.

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_mcp_bind.py
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
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_mcp_bind.py -v`

Expected: FAIL (`bindable_tools` not defined)

- [ ] **Step 3: Implement**

Add to `lc.py`:

```python
def bindable_tools(paths, tools: dict):
    from langchain_core.tools import StructuredTool
    builtin = {t.name: t for t in langchain_tools(paths)}
    out = []
    for name, fn in tools.items():
        if name in builtin:
            out.append(builtin[name])
        else:
            out.append(
                StructuredTool.from_function(
                    func=fn,
                    name=name,
                    description=(fn.__doc__ or name),
                )
            )
    return out
```

`OllamaLLM.invoke` — replace the `langchain_tools(HermesPaths.default())` bind with:

```python
        if tools:
            from backend.paths import HermesPaths
            from backend.tools.lc import bindable_tools
            paths = HermesPaths.default()
            if isinstance(tools, dict):
                chat = chat.bind_tools(bindable_tools(paths, tools))
            else:
                chat = chat.bind_tools(tools)
```

`reason` already passes the tools dict. ScriptedLLM ignores it.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_mcp_bind.py tests/test_graph_routing.py tests/test_mcp_graph.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/lc.py exp1dir/backend/agent/llm_port.py exp1dir/tests/test_mcp_bind.py
git commit -m "feat(exp1): bind MCP tools on the Ollama chat call"
```

---

### Task 9: React — Act label and “MCPs this run”

**Files:**
- Create: `exp1dir/web/src/mcp.ts`
- Modify: `exp1dir/web/src/App.tsx`
- Modify: `exp1dir/web/src/index.css`
- Modify: `exp1dir/tests/test_graph_map.py`

- [ ] **Step 1: Write the failing test**

Append to `test_graph_map.py`:

```python
def test_web_mcp_helpers_exist():
    root = Path(__file__).resolve().parent.parent
    mcp = (root / "web" / "src" / "mcp.ts").read_text(encoding="utf-8")
    assert "export function actLabel" in mcp
    assert "export function usedMcps" in mcp
    app = (root / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "MCPs this run" in app
    assert "actLabel" in app
    assert "/mcp/reload" in app or "/mcp" in app
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_graph_map.py::test_web_mcp_helpers_exist -v`

Expected: FAIL (missing `mcp.ts` / string)

- [ ] **Step 3: Implement**

`web/src/mcp.ts`:

```typescript
export type McpEvent = {
  tool?: string;
  mcp_server?: string;
  mcp_tool?: string;
};

export type McpServer = {
  name: string;
  transport?: string;
  enabled?: boolean;
  connected?: boolean;
  tools?: string[];
  last_error?: string;
};

export function actLabel(event: McpEvent): string {
  if (event.mcp_server && event.mcp_tool) {
    return `${event.mcp_server} / ${event.mcp_tool}`;
  }
  return event.tool ?? "";
}

export function usedMcps(events: McpEvent[]): string[] {
  const names = events.map((e) => e.mcp_server).filter((n): n is string => Boolean(n));
  return [...new Set(names)];
}
```

`App.tsx` changes (keep existing layout):

- Extend `LoopEvent` with `mcp_server?: string; mcp_tool?: string; tool?: string` (tool already exists).
- `entryFor`: if `event.step === "act"`, body starts with `actLabel(event)` then input/text.
- State: `mcpServers` list; `used` set of names; clear `used` when sending a new task.
- `applyEvent`: if `event.mcp_server` add to `used`.
- `refreshSide`: also `GET ${API}/mcp`.
- Side panel block:

```tsx
<div>
  <label>MCPs this run</label>
  <button type="button" onClick={() => void reloadMcp()}>Reload</button>
  <ul className="skills mcp-list">
    {mcpServers.length === 0 && <li>(none configured)</li>}
    {mcpServers.map((s) => (
      <li key={s.name} className={used.includes(s.name) ? "used" : ""}>
        <b>{s.name}</b>
        <div>
          {s.connected ? "connected" : s.enabled ? "error" : "disabled"}
          {used.includes(s.name) ? " · used" : ""}
          {s.last_error ? ` · ${s.last_error}` : ""}
        </div>
      </li>
    ))}
  </ul>
</div>
```

`reloadMcp`: `POST ${API}/mcp/reload` then refresh list.

On `send()`, `setUsed([])`.

CSS:

```css
.mcp-list li.used b {
  color: var(--accent);
}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_graph_map.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/web/src/mcp.ts exp1dir/web/src/App.tsx exp1dir/web/src/index.css exp1dir/tests/test_graph_map.py
git commit -m "feat(exp1): show which MCP the agent used in the React UI"
```

---

### Task 10: Real `MultiServerMCPClient` connector + dependency

**Files:**
- Create: `exp1dir/backend/tools/mcp_connect.py`
- Modify: `exp1dir/backend/tools/mcp.py` (`default_connector`)
- Modify: `exp1dir/pyproject.toml`
- Test: `exp1dir/tests/test_mcp_connect.py` (unit-test config mapping only, mock client)

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_mcp_connect.py
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
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_mcp_connect.py -v`

Expected: FAIL (module missing)

- [ ] **Step 3: Implement connector**

Add to `pyproject.toml` dependencies:

```
"langchain-mcp-adapters>=0.1",
"mcp>=1.0",
```

```python
# exp1dir/backend/tools/mcp_connect.py
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import timedelta
from backend.tools.mcp_config import ServerSpec


def connection_for_spec(spec: ServerSpec) -> dict:
    if spec.transport == "stdio":
        return {
            "transport": "stdio",
            "command": spec.command,
            "args": spec.args,
            "env": spec.env,
        }
    return {
        "transport": "streamable_http",
        "url": spec.url,
        "headers": spec.headers,
        "timeout": timedelta(seconds=spec.timeout),
    }


def connect_server(spec: ServerSpec) -> list[dict]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    async def _list():
        client = MultiServerMCPClient({spec.name: connection_for_spec(spec)})
        tools = await client.get_tools(server_name=spec.name)
        out = []
        for t in tools:
            def make(tool=t):
                def fn(**kwargs):
                    def call():
                        return tool.invoke(kwargs)
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(call)
                        try:
                            result = fut.result(timeout=spec.timeout)
                        except FutureTimeout:
                            raise TimeoutError(f"MCP {spec.name}/{tool.name} timed out after {spec.timeout}s")
                    return str(result)
                fn.__doc__ = getattr(tool, "description", None) or tool.name
                fn.__name__ = tool.name
                return fn
            out.append({"name": t.name, "fn": make(), "description": getattr(t, "description", "") or t.name})
        return out

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_list())
    # Called from a thread with no loop in RunManager; if a loop is running (uvicorn),
    # run the coroutine on a new loop in this thread.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_list())
    finally:
        loop.close()
```

Replace `default_connector` in `mcp.py`:

```python
def default_connector(spec):
    from backend.tools.mcp_connect import connect_server
    return connect_server(spec)
```

Then `pip install -e ".[dev]"` in `exp1dir/` so the new deps are present.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_mcp_connect.py tests/test_mcp_registry.py tests/test_mcp_gateway.py -v`

Expected: PASS (gateway tests still inject fake connector)

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/mcp_connect.py exp1dir/backend/tools/mcp.py exp1dir/pyproject.toml exp1dir/tests/test_mcp_connect.py
git commit -m "feat(exp1): connect MCP servers via langchain-mcp-adapters"
```

---

### Task 11: Docs and system-prompt hint

**Files:**
- Modify: `exp1dir/README.md`
- Modify: `exp1dir/.env.example`
- Modify: `docs/exp1-how-the-agent-works.md`
- Modify: `exp1dir/backend/agent/prompts.py` and `nodes.py` `load_context` (list MCP flattened names)

- [ ] **Step 1: Prompt test** (append to `test_mcp_graph.py`)

```python
def test_system_prompt_lists_mcp_tools(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    def search(query: str = "") -> str:
        """Search the web."""
        return "ok"
    search._mcp_server = "web"
    search._mcp_tool = "search"
    tools = {**build_tool_fns(p), "web__search": search}
    llm = ScriptedLLM(
        [
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    result = run_task(p, llm, "hi", tools=tools)
    sysmsg = result["messages"][0]["content"]
    assert "web__search" in sysmsg
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_mcp_graph.py::test_system_prompt_lists_mcp_tools -v`

Expected: FAIL (`web__search` not in system prompt)

- [ ] **Step 3: Implement prompt + docs**

`prompts.py` — add after Skills:

```
## MCP tools
{mcp_index}
MCP tools are named server__tool. Use them for external APIs and web search when they fit the task.
```

`load_context` — build `mcp_index` from tools:

```python
mcp_lines = []
for name, fn in (tools or {}).items():
    if getattr(fn, "_mcp_server", ""):
        doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
        mcp_lines.append(f"- {name}: {doc}".rstrip(": "))
mcp_index = "\n".join(mcp_lines) if mcp_lines else "(none)"
sys_prompt = SYSTEM.format(..., mcp_index=mcp_index)
```

`.env.example` add:

```
# Optional. Referenced from .hermes/config.json as ${FIRECRAWL_API_KEY}
# FIRECRAWL_API_KEY=
```

README — new section **MCP servers** after TUI commands:

- Edit `exp1dir/.hermes/config.json` `mcp_servers` (stdio `command`/`args`/`env` or HTTP `url`/`headers`)
- Put secrets in `.env` as `${VAR}`
- `/mcp reload` or React Reload; next task sees new tools
- `/mcp`, `/mcp enable <name>`, `/mcp disable <name>`
- Example `firecrawl` HTTP block and `filesystem` stdio block from the spec
- React: Act shows `server / tool`; side list marks used servers

`docs/exp1-how-the-agent-works.md` — short subsection: MCP tools are extra callables in `act`; config.json is the source of truth; reload; events `mcp_server`/`mcp_tool`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -v`

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/README.md exp1dir/.env.example exp1dir/backend/agent/prompts.py exp1dir/backend/agent/nodes.py docs/exp1-how-the-agent-works.md exp1dir/tests/test_mcp_graph.py
git commit -m "docs(exp1): MCP config, reload, and prompt listing"
```

---

## Self-review (spec coverage)

| Spec requirement | Task |
| --- | --- |
| Edit `config.json` to add/update servers | 1, 6 (reload), 11 (docs) |
| `${VAR}` / `${env:VAR}` from env | 1 |
| stdio + Streamable HTTP | 1 (parse), 10 (connector) |
| `enabled` default true; disable skips connect | 1, 3, 6 |
| Flatten `server__tool` | 1, 3 |
| Skip builtin / duplicate flattened names | 3 |
| Fake connector in tests; adapters in prod | 3, 10 |
| Snapshot tools at run start; mid-run reload isolated | 3, 5 |
| Invalid JSON keeps previous map | 3 |
| One failed server does not block others | 3 |
| Act events `mcp_server` / `mcp_tool` | 4, 6 |
| Unchanged graph edges | 4 |
| `GET /mcp`, reload, enable/disable persist `model` | 2, 6 |
| No POST full server body; health unchanged | 6 |
| TUI `/mcp` list/enable/disable/reload | 7 |
| React Act label + used list + Reload | 9 |
| Ollama binds live MCP tools | 8 |
| Timeout 60s default | 1 (parse), 10 (executor) |
| No MCP → behavior unchanged | 5, 6 empty list; existing tests |
| README + how-the-agent-works | 11 |
| Interrupt during MCP: wait for timeout | 10 (timeout); existing act cancel between calls |

No SSE, no resources/prompts, no file watcher, no Pick-MCP node.
