# exp1 MCP support — Design

Date: 2026-08-13  
Location: `exp1dir/`  
Status: approved in conversation; awaiting spec review  
Supersedes: the “no MCP” non-goal in `2026-08-12-exp1-hermes-agent-design.md` (all other exp1 constraints still apply)

## Goal

Let the user plug Model Context Protocol (MCP) servers into the exp1 Hermes-style agent so the model can call external tools (search, APIs, local processes) during the existing Reason → Act → Observe loop. The user adds and updates servers by editing `.hermes/config.json`. The React UI shows which MCP server the agent used for a task.

## Non-goals

- SSE transport (stdio + Streamable HTTP only)
- MCP resources, prompts, or sampling
- A form or API that POSTs a full server definition (command/url/headers live in the file)
- Auto-reload on file save (explicit `/mcp reload` or `POST /mcp/reload`)
- Parallel MCP tool calls (act stays sequential)
- Changing LangGraph topology (no Pick-MCP node)

## Constraints (locked)

| Decision | Choice |
| --- | --- |
| How users add/update servers | Edit `.hermes/config.json`; `/mcp` lists, enable/disable, reload |
| Transports | stdio (`command`/`args`/`env`) and Streamable HTTP (`url`/`headers`) |
| Tool exposure | Flatten enabled servers as `server__tool` next to built-in tools |
| Library | `langchain-mcp-adapters` `MultiServerMCPClient`, wrapped into the existing tools dict |
| Web visualization | Same Act node; label `server / tool`; side list marks MCPs used this run |
| Secrets | `${VAR}` from `.env`; do not commit keys |
| Graph | Unchanged edges; MCP is extra tools + event fields |

## Architecture

MCP is extra tools in the same LangGraph loop. The gateway owns MCP sessions. TUI and React are clients.

```
.hermes/config.json  (mcp_servers)
        │
        ▼
   MCP registry  ── MultiServerMCPClient (stdio | streamable HTTP)
        │              enabled servers only
        ▼
   tools dict = built-in + firecrawl__search + …
        │
        ▼
   reason ⇄ act ⇄ observe     (unchanged edges)
        │
        │  act event: tool, mcp_server, mcp_tool
        ▼
   TUI  /mcp list|enable|disable|reload
   React  Act label + “MCPs this run” side list
```

The gateway process holds the live tool map. On start and on reload it reads `config.json`, connects enabled servers, and registers callables. `load_context` / `reason` of a run bind whatever map exists at run start. A mid-run reload does not change that run’s tools.

Calling `firecrawl__search` is how the agent “picks” Firecrawl. There is no separate selection step.

## Config

Source of truth: `exp1dir/.hermes/config.json`. Keep the existing `model` key. Add `mcp_servers`.

Users add, change, or remove a server by editing this file, then reload. First launch does not invent example servers. README documents a copy-paste example.

```json
{
  "model": "qwen2.5-coder:7b",
  "mcp_servers": {
    "firecrawl": {
      "url": "https://mcp.firecrawl.dev/mcp",
      "headers": { "Authorization": "Bearer ${FIRECRAWL_API_KEY}" },
      "enabled": true
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "env": {},
      "enabled": false
    }
  }
}
```

| Field | Applies to | Meaning |
| --- | --- | --- |
| `command` | stdio | Executable |
| `args` | stdio | Argument list (default `[]`) |
| `env` | stdio | Extra env for the subprocess (default `{}`) |
| `url` | HTTP | Streamable HTTP endpoint |
| `headers` | HTTP | Request headers (default `{}`) |
| `enabled` | both | If omitted, treat as `true`. Disabled servers are not connected and their tools are not bound |
| `timeout` | both | Per-call timeout seconds (default `60`) |

A server is stdio if `command` is set, HTTP if `url` is set. If both are set, that server is invalid: skip it and record an error. If neither is set, skip it and record an error.

`${VAR}` and `${env:VAR}` expand from process environment (loaded from `exp1dir/.env`). Unknown vars stay as the literal string; that server may then fail auth.

`/mcp enable|disable` writes `enabled` on that entry and reloads. It must not drop unrelated keys (`model`, other servers, extra fields).

## Components

### MCP registry — `backend/tools/mcp.py`

Owns config parse, `MultiServerMCPClient`, and the live MCP callable map.

On start and on reload:

1. Read `mcp_servers` from disk (empty dict if missing).
2. Expand `${VAR}` in string fields (`url`, `headers`, `command`, `args`, `env` values).
3. Build adapter connections for enabled, valid servers.
4. List tools; register each as `server__tool` (server name, `__`, MCP tool name with non-identifier chars replaced by `_`).
5. Record status per server: `name`, `transport` (`stdio` or `http`), `enabled`, `connected`, `tools` (registered flattened names), `skipped_tools`, `last_error`.

A thin async bridge runs adapter calls from the sync `act` node (dedicated event loop in the gateway process, or equivalent). Do not `asyncio.run` per call if that would nest loops.

`build_tool_fns` (or a wrapper used by `RunManager`) returns built-in tools plus the current MCP map. `OllamaLLM.invoke` must bind that **live** list, not a hardcoded `langchain_tools()` that ignores MCP.

### Act / events

`act` stays sequential. For an MCP tool, `make_event` gains optional fields:

- `mcp_server`: server key from config (e.g. `firecrawl`)
- `mcp_tool`: original MCP tool name (e.g. `search`)
- `tool`: flattened name (`firecrawl__search`) as today

Built-in tools omit `mcp_server` / `mcp_tool` (empty string).

### Gateway API

| Endpoint | Role |
| --- | --- |
| `GET /mcp` | `{ "servers": [ { name, transport, enabled, connected, tools, skipped_tools, last_error } ] }` |
| `POST /mcp/reload` | Re-read `config.json`, reconnect; return same shape as `GET /mcp` |
| `POST /mcp/{name}/enabled` | Body `{ "enabled": bool }`. Unknown name → 404. Writes `config.json` then reloads. |

No POST of a full server body.

`GET /health` is unchanged in v1. MCP status is only `GET /mcp`.

### TUI

Slash commands (autocomplete table):

- `/mcp` — list servers (enabled, connected, tool count, last error)
- `/mcp enable <name>`
- `/mcp disable <name>`
- `/mcp reload` — after the user edits `config.json`

Act transcript blocks for MCP calls show `server / tool` plus the flattened name.

### React

Keep the loop graph. On `act` with `mcp_server`:

- Act node / transcript label: `{mcp_server} / {mcp_tool}`
- Side panel (next to models / skills) lists `GET /mcp` servers; mark those whose `mcp_server` appeared in this run’s events as used

A small Reload button calls `POST /mcp/reload` and refreshes the list.

## Data flow

1. Gateway starts → parse config → connect enabled servers → merge MCP callables into the tool map.
2. User edits `config.json` (add/update/remove) → `/mcp reload` or `POST /mcp/reload` → reconnect → **next** run binds the new list.
3. User submits a task → `reason` sees built-in + MCP tools → model may call `firecrawl__search`.
4. `act` executes that callable, emits `tool`, `mcp_server`, `mcp_tool`.
5. React lights Act, labels `firecrawl / search`, checks that server in “MCPs this run.” TUI shows the same in the Act block.
6. `observe` appends the result like any other tool. Loop continues until SUCCESS.

Reload does not re-execute tools. Two UIs still share one execution.

## Error handling

- Missing `mcp_servers` → no MCP tools; agent behaves as today.
- Invalid JSON in `config.json` → reload fails; keep the previous live map; API/TUI show the parse error. `/model` still works (same file).
- One server fails to connect → skip it, connect the others, set `connected: false` and `last_error`.
- Unknown `${VAR}` → leave literal; server may fail; error is per-server.
- MCP tool exception or timeout → observation `ERROR: …` (same as `web_fetch`). Default timeout 60s.
- Flattened name collides with a built-in (`read_file`, `write_file`, `list_dir`, `shell`, `web_fetch`, `memory`, `skill_manage`, `load_skill`, `search_sessions`) or with an already registered MCP tool → skip the new tool. The server stays `connected: true`; skipped names appear in that server’s status (`skipped_tools`), not as a connection failure.
- Mid-run reload → current run keeps its tool map; next run uses the new one.
- Interrupt during an MCP call → cancel if the adapter/session allows; otherwise wait until timeout; observation `user interrupted: …`.

## Testing

Pytest with a fake MCP client / fake tools (no live server, no `npx`):

- Parse stdio vs HTTP; `enabled: false` is omitted from the client
- `${VAR}` and `${env:VAR}` expand from env
- Flattened names `server__tool`; built-in names win on collision
- Graph: MCP tool call → act → observe; event includes `mcp_server` and `mcp_tool`
- Failed server does not block others
- Reload reads updated `config.json`; an in-flight run still uses the old map
- `GET /mcp` shape; enable/disable persists `enabled` without dropping `model` or other servers
- TUI command table includes `/mcp`
- React mapping: `mcp_server` on Act; used-server set derived from events

Manual check: add a server to `config.json`, `/mcp reload`, run a task that needs it, confirm React Act label and side list.

## Success criteria

1. User can add or update MCP servers by editing `.hermes/config.json` and running `/mcp reload` (or `POST /mcp/reload`) without restarting the gateway.
2. Enabled stdio and Streamable HTTP servers’ tools appear to the model as `server__tool` and execute in `act`.
3. `/mcp`, `/mcp enable|disable`, and `/mcp reload` work in the TUI; React lists servers and marks which ones this run used.
4. A failed MCP server does not take down built-in tools or other servers.
5. Existing exp1 behavior with no `mcp_servers` key is unchanged.
