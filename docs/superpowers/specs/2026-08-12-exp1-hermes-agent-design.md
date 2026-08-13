# exp1 Hermes-style LangGraph Agent — Design

Date: 2026-08-12  
Location: `exp1dir/`  
Status: approved in conversation; awaiting spec review

## Goal

Build a sample but usable Hermes-style AI agent in `exp1dir/`: the user types a task; the agent decides how to use tools, short-term memory, long-term memory, and skills. The same run is visible as a live Reason → Act → Observe → Learn graph in React, and as a full TUI in the terminal. After success the agent asks “What did I learn?”, updates memory and/or skills, and reuses that knowledge on later tasks.

## Non-goals

- Not a clone of full Hermes (no MCP, messaging gateways, 60+ tools, cron, subagents, voice).
- No browser E2E suite in v1.
- No vector database; long-term memory is markdown files plus SQLite session search.
- Shell cwd is the workspace with a 30s timeout and path sandbox. There is no container/network namespace (especially on Windows); the agent is told to use `web_fetch` for HTTP, not `curl`/`wget`.
- No `HERMES_HOME` override; memory is always `exp1dir/.hermes/`.

## Constraints (locked)

| Decision | Choice |
| --- | --- |
| Purpose | Usable Hermes-style agent **and** rich React loop visualization |
| Tools | Files, sandboxed shell, web fetch, memory, skills, session search |
| CLI | Full TUI (multiline editor, autocomplete, interrupt-and-redirect, history) |
| Memory home | Project-local `exp1dir/.hermes/` |
| Runtime | One LangGraph server; TUI and React are WebSocket clients |
| LLM | Ollama via `OLLAMA_BASE_URL`; models switched with `/model` |

## Architecture

One Python process is the agent brain. The Textual TUI (`hermes`) and the React app are clients.

```
You (task)
   │
   ├─ Textual TUI  (`hermes`)  ──┐
   └─ React UI     (browser)   ──┤  WebSocket
                                 ▼
                    FastAPI gateway
                                 ▼
                    LangGraph agent
         load_context → reason ⇄ act ⇄ observe
                         → SUCCESS → reflect (“what did I learn?”)
                         → update_memory
                                 ▼
                    Ollama  (OLLAMA_BASE_URL + active model)
                    .hermes/  (MEMORY.md, USER.md, skills/, sessions, config)
                    workspace/ (sandboxed files + shell)
```

The `hermes` CLI starts the gateway if it is not already running, then attaches. `hermes serve` starts only the gateway (for React-only use). React talks to the same gateway. A run started in either client is streamed to all attached clients. Tools execute once per act, never twice because two UIs are watching.

Each submitted task is a new **run** (`run_id`). A TUI process may send many tasks; each run calls `load_context` again so the next task sees memory/skills written by the previous run. That is the “Future Task → Reuse knowledge” edge. (Hermes freezes the snapshot for a whole CLI session; this sample freezes per run so reuse is visible without restarting.)

## Directory layout

```
exp1dir/
  .env.example
  .env                          # gitignored; user supplies Ollama address
  README.md
  pyproject.toml
  backend/
    api/                        # FastAPI gateway
    agent/                      # LangGraph graph, state, nodes
    tools/                      # file, shell, web, memory, skill, sessions
    memory/                     # markdown + sqlite helpers
    llm/                        # Ollama client, model list/switch
    skills/bundled/             # starter SKILL.md files copied on first launch
  tui/                          # Textual app
  web/                          # React (Vite)
  tests/
  .hermes/                      # created at runtime if missing
    config.json                 # active model, last session
    memories/MEMORY.md
    memories/USER.md
    skills/<name>/SKILL.md
    sessions.sqlite
    workspace/                  # sandbox root for file + shell tools
    runs/<run_id>.jsonl         # event log for reconnect replay
```

## Config

`.env` (not committed):

```
OLLAMA_BASE_URL=http://host:11434
OLLAMA_API_KEY=                 # optional; empty if the server needs none
OLLAMA_MODEL=                   # optional default if config.json has no model yet
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=8765
```

`HERMES_HOME` is not required. Memory always lives at `exp1dir/.hermes/` (absolute path resolved from the package root).

`.hermes/config.json` stores the last selected model. `/model <name>` updates this file so the next process start reuses it.

Startup order for the active model:

1. `.hermes/config.json` `model` if set and still present on the server
2. else `OLLAMA_MODEL` if set and present
3. else the first model returned by Ollama `/api/tags`
4. else fail with “no models available at OLLAMA_BASE_URL”

## LangGraph

### State

```python
class AgentState:
    task: str
    session_id: str
    messages: list          # short-term: reason/act/observe transcript
    memory_snapshot: str    # frozen MEMORY.md + USER.md at this run's load_context
    skill_index: list       # [{name, description}, ...] at this run's load_context
    loaded_skills: list     # full SKILL.md bodies loaded this run
    cycle: int
    max_cycles: int         # default 15
    pending_tool_calls: list
    last_observation: str
    status: str             # running | success | failed | interrupted | capped
    final_answer: str
    reflection: str
    memory_writes: list     # planned durable updates from reflect or tools
    active_model: str
```

Short-term memory is `messages`, `last_observation`, and `loaded_skills`. It dies with the run.

Long-term memory is files under `.hermes/`. Tool writes persist immediately. The system-prompt snapshot does not change mid-run. Tool responses show live file state. The next task’s `load_context` injects the new snapshot.

### Nodes and edges

```
load_context → reason
reason → act          if the model requested tool calls
reason → reflect      if the model produced a final answer (SUCCESS)
reason → reflect      if cycle >= max_cycles (status=capped)
act → observe
observe → reason      cycle += 1
reflect → update_memory
update_memory → END
```

Interrupt (explicit):
1. `POST /runs/{id}/interrupt` cancels in-flight `act` (kill subprocess if needed).
2. Set `last_observation` to `user interrupted: <note or empty>`, `status=interrupted`, emit `observe`.
3. Wait for the next user message on that same `run_id` (TUI: next Ctrl+Enter; React: task box while run is interrupted).
4. That message is appended as a human turn; `status=running`; go to `reason`.
5. If the user sends `/quit` or starts a **new** task (`POST /runs`) instead, this run ENDs without `reflect` unless it already reached success.

### Node contracts

**load_context**  
Read MEMORY.md, USER.md, skill index (name + description only). Do not load skill bodies. Build the system prompt: identity, frozen memory, skill index, tool instructions, the loop policy (reason before acting; observe before the next reason; after success, reflect).

**reason**  
Call Ollama with tools bound. Emit a `reason` event with the model’s thoughts/text. If tool calls: stash them in `pending_tool_calls`. If final answer: set `final_answer` and `status=success`. If the LLM call fails: emit `error`, retry once; if it still fails, set `status=failed` and go to `reflect`.

**act**  
Execute pending tool calls sequentially. Each call emits an `act` event (tool name + input). Path sandbox: every file/shell path is resolved and must stay under `.hermes/workspace/` (or under `.hermes/memories/` and `.hermes/skills/` for memory/skill tools only).

**observe**  
Append tool results to `messages`, set `last_observation`, emit `observe`. Clear `pending_tool_calls`.

**reflect**  
Prompt: “The task is done (or stopped). What did I learn that would help a future task? Propose zero or more memory entries and/or a skill create/update. If nothing durable, say so.” Emit `learn`. Parse structured output (JSON) into `memory_writes`. Invalid JSON → empty writes, keep `final_answer`.

**update_memory**  
Apply `memory_writes` to MEMORY.md, USER.md, and/or `skills/<name>/SKILL.md`. Emit `memory_update` with a diff summary. Persist the run to `sessions.sqlite` and close the jsonl log.

## Tools

The model chooses tools. The user never selects a tool.

| Tool | Behavior |
| --- | --- |
| `read_file` | Read a file under workspace |
| `write_file` | Create/overwrite under workspace |
| `list_dir` | List a directory under workspace |
| `shell` | Run a command with cwd=workspace, timeout 30s, capture stdout/stderr/exit. Path sandbox only; not a network jail. |
| `web_fetch` | HTTP GET, return text (html→markdown if possible), cap ~50 KB |
| `memory` | `add` / `replace` / `remove` on MEMORY.md or USER.md (substring match for replace/remove, Hermes-style) |
| `skill_manage` | `create` / `update` / `delete` a skill directory + SKILL.md |
| `load_skill` | Read a SKILL.md body into `loaded_skills` for this run |
| `search_sessions` | FTS/LIKE search over past run summaries in SQLite |

Skill files use agentskills.io-style frontmatter:

```markdown
---
name: inspect-workspace
description: List and summarize files in the workspace
---
# Inspect workspace
...
```

Ship two starter skills in `backend/skills/bundled/`: `inspect-workspace` and `take-notes` (how to write durable facts into MEMORY.md). On first launch, copy any bundled skill that is not already in `.hermes/skills/`. Do not overwrite agent-created skills of the same name.

## Gateway API

- `GET /health` — gateway + Ollama reachability + active model
- `GET /models` — proxy of Ollama `/api/tags`
- `POST /models/active` — `{ "model": "..." }` validate against tags, persist config, return active
- `POST /runs` — `{ "task": "..." }` → `{ "run_id" }` (always a new run; `load_context` runs)
- `POST /runs/{run_id}/message` — `{ "text": "..." }` used after interrupt to redirect the same run
- `WS /ws/runs/{run_id}` — stream events; on connect, replay jsonl then live
- `WS /ws/events` — optional hub: all run events for the React graph when watching live TUI runs
- `POST /runs/{run_id}/interrupt` — `{ "note": optional }`
- `GET /memory` — current MEMORY.md + USER.md
- `GET /skills` — skill index
- `GET /runs` — recent runs from sqlite

Event payload:

```json
{
  "run_id": "...",
  "step": "reason | act | observe | success | learn | memory_update | error",
  "cycle": 2,
  "tool": "shell",
  "input": "...",
  "observation": "...",
  "text": "...",
  "model": "llama3.1"
}
```

`step=success` is emitted when `reason` produces a final answer, before `reflect`. The React graph node labeled SUCCESS lights on that event. LEARN lights on `learn`. UPDATE MEMORY / SKILL lights on `memory_update`. FUTURE TASK / REUSE is a display-only node: it lights after `memory_update` to show knowledge is ready for the next run; it is not a LangGraph node.

## TUI (Textual)

Hermes-like full TUI:

- Multiline editor, send on a dedicated key (Ctrl+Enter); Enter inserts newline
- Streaming transcript with labeled blocks: Reason / Act / Observe / Success / Learn
- Slash-command autocomplete:
  - `/model` — list models from the server, mark active
  - `/model <name>` — switch, persist
  - `/memory` — show this run’s frozen snapshot; note that disk writes apply on the next task
  - `/skills` — list skills
  - `/interrupt` — stop current act; next Ctrl+Enter redirects this run
  - `/history` — past runs
  - `/quit`
- Multiple tasks in one TUI process: each Ctrl+Enter that is not an interrupt-redirect starts a **new** run (fresh `load_context`). Transcript keeps prior runs visible as history.
- Interrupt-and-redirect: `/interrupt`, then type the new instruction; that text is `POST /runs/{id}/message`, not a new run.

Starting `hermes` with the gateway down starts it in the background on `GATEWAY_HOST:GATEWAY_PORT`, then connects. If that port is occupied by a non-gateway process, exit with the port and a hint. `hermes serve` runs the gateway in the foreground.

## React UI

Vite + React. Connects to the gateway WebSocket.

- Task input (start a run from the browser)
- Live graph of the loop: Task → Reason ⇄ Act ⇄ Observe → SUCCESS → What did I learn? → Update Memory/Skill → Future Task / Reuse knowledge. The active node is highlighted; failed observe is red
- Transcript panel mirroring TUI blocks
- Side panel: active model (dropdown = `/model`), memory files, skill list
- Stop button = interrupt

Both UIs are first-class. Neither is a screenshot of the other; both consume the same events.

## Error handling

- Ollama unreachable at start: no run; clients show “cannot reach Ollama at {url}”
- `/model` unknown name: error, keep current model
- Mid-run LLM error: `error` event; reason retries once, then `status=failed` and `reflect`
- Path escape: tool returns an error string, does not raise
- Shell timeout / non-zero: observation includes stdout, stderr, exit code. Shell is not a network jail.
- `web_fetch` non-200 or oversized: truncated error / first 50 KB
- Max cycles: `status=capped`, still run `reflect`; apply memory writes only if the model proposed them
- Missing/corrupt MEMORY.md or SKILL.md: treat as empty, warn, do not abort
- Invalid reflect JSON: skip writes, still return `final_answer`
- WebSocket drop: reconnect and replay jsonl
- Two clients: same stream, single tool execution

## Testing

Backend pytest with a fake Ollama (no live server required for CI):

- Routing: tool call → act → observe → reason; final answer → reflect → update_memory
- Cycle cap forces stop
- Path escape rejected; shell timeout mocked; web_fetch mocked
- memory add/replace/remove changes files
- skill_manage writes valid SKILL.md; load_context does not include bodies until load_skill
- Reflect stub “I learned X” updates files; invalid JSON does not
- Reuse: run 1 writes memory/skill; run 2 load_context contains it
- Model list/switch: mocked tags; bad name keeps current
- Interrupt: mid-act cancel; next reason sees interrupt observation
- Gateway: event order; two websocket clients, tools once

TUI/React: wiring tests only (command table includes `/model` and `/interrupt`; graph maps each `step` to a node).

Manual check after tests: set `.env`, `/model`, task that lists workspace and remembers a fact, confirm MEMORY.md, second task reuses the fact, React shows the live graph.

## Success criteria

1. User supplies only `OLLAMA_BASE_URL` (and optional key/default model) in `.env`.
2. User types a task; the agent alone chooses tools, short-term context, long-term memory, and skills.
3. The loop Task → Reason → Act → Observe (repeat) → SUCCESS → Learn → Update Memory/Skill is executed in LangGraph and visualized in React and the TUI.
4. `/model` lists Ollama models and switches the active one without restarting.
5. A later task reuses knowledge written after the first success.
6. File and shell tools cannot leave `exp1dir/.hermes/workspace/` (memory/skill tools may write only under `.hermes/memories/` and `.hermes/skills/`).
