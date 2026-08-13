# How the exp1 Hermes-style Agent Works

This document explains the agent in `exp1dir/`: how LangGraph is built, how the **ReAct** loop (Reason → Act → Observe) solves a task, and how **short-term memory**, **long-term memory**, and **skills** work together. A full walkthrough of two related tasks is at the end.

You only type a task. The agent decides which tools, memories, and skills to use.

---

## 1. Big picture

```
You (task)
   │
   ├─ Textual TUI (`hermes`)  ──┐
   └─ React UI (browser)      ──┤  HTTP + WebSocket
                                ▼
                   FastAPI gateway (`hermes serve`)
                                ▼
                   LangGraph  (one run per task)
         load_context → reason ⇄ act ⇄ observe
                         → SUCCESS → reflect (“what did I learn?”)
                         → update_memory → END
                                ▼
                   Ollama  +  exp1dir/.hermes/
```

One Python process owns the graph. The TUI and the React app are clients of the same gateway. Every node emits an event (`reason`, `act`, `observe`, `success`, `learn`, `memory_update`). Both UIs render that stream: the TUI as labeled blocks, React as a live loop graph.

Code: `exp1dir/backend/agent/graph.py`, `exp1dir/backend/agent/run_manager.py`, `exp1dir/backend/api/app.py`.

---

## 2. ReAct, mapped onto LangGraph

Classic **ReAct** (Reason + Act) is:

1. **Reason** — think about the task and decide the next action (or that you are done).
2. **Act** — call a tool.
3. **Observe** — read the tool result.
4. Repeat until the answer is ready.

This sample **enforces** that loop with graph edges instead of hoping the model follows a prompt. After success it adds a learning step that Hermes-style agents use:

| Your loop | LangGraph node | What happens |
| --- | --- | --- |
| Task | `load_context` | Load frozen memory + skill index; build the system prompt |
| Reason | `reason` | Call Ollama with tools bound |
| Act | `act` | Execute the tool calls the model requested |
| Observe | `observe` | Append tool results to the message list |
| (repeat) | `observe` → `reason` | Cycle counter increments |
| SUCCESS | `reason` (no tools) | Final answer; status = `success` |
| “What did I learn?” | `reflect` | Second LLM call: propose memory/skill writes |
| Update Memory / Skill | `update_memory` | Write markdown files; save the run to SQLite |
| Future task | next `load_context` | New run; snapshot includes what was learned |

That is why Reason and Act are **separate nodes**. You can watch each hop in the React UI. A prebuilt “ReAct agent” helper would hide those hops inside one black box.

---

## 3. How LangGraph is constructed

### 3.1 State

Every hop reads and writes one shared dict: `AgentState` (`exp1dir/backend/agent/state.py`).

| Field | Role |
| --- | --- |
| `task` | The user’s request for this run |
| `run_id` | Id for events and the jsonl log |
| `messages` | **Short-term memory**: system + user + assistant + tool turns |
| `memory_snapshot` | Frozen `MEMORY.md` + `USER.md` at the start of this run |
| `skill_index` | `[{name, description}, …]` only — no skill bodies |
| `loaded_skills` | Reserved for skill bodies loaded this run |
| `cycle` / `max_cycles` | Loop counter (default cap 15) |
| `pending_tool_calls` | What `reason` asked `act` to run |
| `pending_observations` | What `act` produced for `observe` |
| `last_observation` | Latest tool (or interrupt) text |
| `status` | `running` \| `success` \| `failed` \| `interrupted` \| `capped` |
| `final_answer` | Text returned when the model stops calling tools |
| `reflection` / `memory_writes` | Output of `reflect`, applied by `update_memory` |
| `active_model` | Ollama model name for this run |

LangGraph merges each node’s returned dict into this state. Nodes do not need to return every field.

### 3.2 Two compiled graphs

**Simple graph** (`build_graph` in `graph.py`) — used by unit tests and `run_task`:

```
START → load_context → reason
                          │
          ┌───────────────┴───────────────┐
          │ pending_tool_calls?           │ success / failed / capped?
          ▼                               ▼
         act → observe ──────────────► reason
                                          │
                                          ▼
                                      reflect → update_memory → END
```

Edges in code:

```python
g.add_edge(START, "load_context")
g.add_edge("load_context", "reason")
g.add_conditional_edges("reason", route_after_reason, {"act": "act", "reflect": "reflect"})
g.add_edge("act", "observe")
g.add_edge("observe", "reason")
g.add_edge("reflect", "update_memory")
g.add_edge("update_memory", END)
```

`route_after_reason`:

- If `status` is `success`, `failed`, or `capped` → `reflect`
- Else if there are `pending_tool_calls` → `act`
- Else → `reflect`

**Controlled graph** (`build_controlled_graph` in `run_manager.py`) — used by the live gateway. Same loop, plus interrupt:

```
act → observe → (if interrupted) wait_redirect → reason
              → (otherwise) reason
```

`wait_redirect` blocks on a threading event until you send a follow-up (`POST /runs/{id}/message` or the next Ctrl+Enter in the TUI). Then it appends your text as a user message and returns to `reason`.

Nodes are ordinary Python functions. `functools.partial` binds `paths`, `llm`, `tools`, `emit`, and (in the controlled graph) `control`, so LangGraph only passes `state`.

### 3.3 What each node does

**`load_context`**  
Creates `.hermes/` if needed. Reads long-term memory and the skill catalog. Builds the system prompt (identity + frozen snapshot + skill names/descriptions + ReAct instructions). Starts `messages` with that system turn and the user task. Does **not** call the LLM.

**`reason`**  
If `cycle >= max_cycles`, sets `status=capped` and skips the model. Otherwise calls `llm.invoke(messages, tools)` (Ollama with tools bound). If the model returns tool calls, they go into `pending_tool_calls`. If not, this is SUCCESS: `final_answer` is set and a `success` event is emitted. One retry on LLM errors, then `status=failed`.

**`act`**  
Looks up each pending call in the tool registry and runs it. Path-sandbox errors come back as `ERROR: …` strings, not exceptions. On interrupt, the in-flight shell is killed and the observation becomes `user interrupted: …`.

**`observe`**  
Appends each result as a `role=tool` message, clears pending calls, increments `cycle`, emits `observe`.

**`reflect`**  
Asks: “What did I learn that would help a future task?” Expects JSON with `memory` and `skills` arrays. Invalid JSON → no writes; the task answer is kept.

**`update_memory`**  
Applies those writes to `MEMORY.md` / `USER.md` / `skills/<name>/SKILL.md`, emits `memory_update`, stores a row in `sessions.sqlite`.

---

## 4. Memory and skills

Think of three stores with different lifetimes.

### 4.1 Short-term memory (this run only)

Lives in `state["messages"]` (plus `last_observation` and `pending_*`).

It is the ReAct scratchpad: thoughts, tool calls, and observations. When the run ends, this list is discarded. The next task starts a **new** graph invoke with empty `messages`.

That is why a long tool chain can still “remember” what `list_dir` returned two hops ago: it is sitting in `messages`, not in a file.

### 4.2 Long-term memory (across tasks)

Files under `exp1dir/.hermes/memories/`:

| File | Meaning |
| --- | --- |
| `MEMORY.md` | Durable facts about the project / environment |
| `USER.md` | Preferences about you |

**Frozen snapshot (Hermes pattern).** At `load_context`, both files are concatenated into `memory_snapshot` and injected into the system prompt. That snapshot **does not change mid-run**, so the prompt prefix stays stable.

The `memory` tool (`add` / `replace` / `remove`) still writes disk **immediately**. The model sees the live file contents in the **tool observation**. The **system prompt** only picks up those writes on the **next** task’s `load_context`. That is the “Future Task → Reuse knowledge” edge.

After SUCCESS, `reflect` may also propose memory writes. `update_memory` applies them the same way as the `memory` tool.

`search_sessions` is a third long-term channel: SQLite rows of past `task` + `summary`, searchable with LIKE.

### 4.3 Skills (procedural memory)

Skills are how-to documents, not facts. They follow a SKILL.md layout:

```markdown
---
name: inspect-workspace
description: List and summarize files in the workspace
---
# Inspect workspace
Use `list_dir` then `read_file` ...
```

**Progressive disclosure:**

1. At `load_context`, only **name + description** go into the system prompt (`skill_index`). Bodies stay off the context window.
2. If a description looks relevant, the model calls `load_skill(name)`. The full markdown comes back as an observation (short-term).
3. If the agent invents a reusable procedure, `skill_manage` create/update writes `exp1dir/.hermes/skills/<name>/SKILL.md`. `reflect` can do the same after success.

On first launch, bundled skills are copied from `backend/skills/bundled/` into `.hermes/skills/` **only if that skill does not already exist**, so agent-edited skills are not overwritten.

Shipped starters:

- `inspect-workspace` — list then read files in the sandbox
- `take-notes` — write durable facts with the `memory` tool

### 4.4 How they cooperate on a task

```
load_context
   │  long-term facts  → system prompt (frozen)
   │  skill catalog    → system prompt (names only)
   ▼
reason  ← short-term messages (grows each hop)
   │  may load_skill     → body enters messages
   │  may memory add     → disk now; prompt next run
   │  may list_dir/shell → observation in messages
   ▼
SUCCESS → reflect → update_memory → files for the next run
```

The model is never told “use tool X”. It sees the catalog, the frozen facts, and the ReAct instruction, then chooses.

---

## 5. Tools the model can choose

All of these are registered in `build_tool_fns` (`exp1dir/backend/tools/registry.py`):

| Tool | Sandbox / notes |
| --- | --- |
| `list_dir`, `read_file`, `write_file` | Only under `.hermes/workspace/` |
| `shell` | cwd = workspace, 30s timeout; not a network jail |
| `web_fetch` | HTTP GET, HTML→text, ~50 KB cap |
| `memory` | `MEMORY` or `USER` markdown |
| `load_skill` / `skill_manage` | `.hermes/skills/` |
| `search_sessions` | Past runs in SQLite |

File and shell paths that escape the workspace return `ERROR: path is outside sandbox: …`.

### 5.1 MCP tools

MCP tools are extra callables in **`act`**, not a new graph node. The source of truth is `exp1dir/.hermes/config.json` (`mcp_servers`). Enabled stdio and HTTP servers flatten as `server__tool` and are listed in the system prompt. Reload (`/mcp reload` or React Reload) reconnects; the **next** task sees the new map. Act events include `mcp_server` and `mcp_tool` so the TUI and React can label `server / tool`.

---

## 6. Worked example (step by step)

Two tasks in one TUI session. Each task is a **new run** and therefore a new `load_context`. That is how reuse shows up without restarting the process.

Assume `.hermes/` was just created: empty `MEMORY.md` / `USER.md`, bundled skills copied in, empty `workspace/`.

---

### Task A — “List the workspace and remember that this project is exp1”

#### Step A0 — You send the task

TUI: type the sentence, Ctrl+Enter.  
Gateway: `POST /runs` with `{ "task": "List the workspace and remember that this project is exp1" }`.  
`RunManager.start` compiles the controlled graph and `invoke`s it on a background thread. Events stream to the TUI and to React.

#### Step A1 — `load_context` (Task)

- `ensure_home` creates directories and copies bundled skills if missing.
- Snapshot is essentially empty (`# MEMORY` / `# USER`).
- Skill index includes at least:

```json
[
  {"name": "inspect-workspace", "description": "List and summarize files in the workspace"},
  {"name": "take-notes", "description": "Write durable facts into MEMORY.md with the memory tool"}
]
```

- System prompt = ReAct instructions + that snapshot + that index.
- `messages` = `[system, user]`.
- React lights **Task**, then moves to **Reason**. No LLM call yet.

#### Step A2 — `reason` (cycle 0)

Ollama sees: empty memory, a skill named `inspect-workspace` that matches “list the workspace”, and `take-notes` that matches “remember”.

A typical decision (the model chooses; this is a representative trace):

1. `load_skill("inspect-workspace")` — pull the procedure.
2. Then list files, then write the fact.

Suppose it starts with the skill:

- `pending_tool_calls` = `[{name: "load_skill", args: {name: "inspect-workspace"}}]`
- Event: `step=reason`, text such as “I’ll load the inspect-workspace skill.”
- Router: tools pending → **act**.

#### Step A3 — `act` then `observe` (cycle 0 → 1)

**Act** runs `load_skill`. The observation is the full SKILL.md body (“Use `list_dir` then `read_file`…”).

**Observe** appends that as a tool message. Short-term memory now contains the procedure. `cycle` becomes 1. Back to **reason**.

#### Step A4 — `reason` (cycle 1) → list the folder

Following the skill, the model calls `list_dir` with `path="."`.

**Act** lists `.hermes/workspace/` (empty → `"(empty)"`).  
**Observe** puts `"(empty)"` into `messages`. `cycle` = 2.

#### Step A5 — `reason` (cycle 2) → remember the fact

The listing is enough. For “remember that this project is exp1” the model can:

- call `memory(action="add", target="MEMORY", text="project is exp1")` **now**, and/or
- wait for `reflect` to propose the same write.

If it calls `memory` now:

- Disk `MEMORY.md` gains `- project is exp1` immediately.
- The **system prompt snapshot is still empty** for the rest of this run.
- The tool result `"added to MEMORY"` is in short-term `messages`, so the model knows the write succeeded.

#### Step A6 — `reason` (cycle 3) — SUCCESS

No more tools. The model answers, for example: “The workspace is empty. I stored that this project is exp1.”

- `status = success`, `final_answer` set.
- Event `step=success` → React node **SUCCESS**.
- Router → **reflect** (not another act).

#### Step A7 — `reflect` (“What did I learn?”)

A second LLM call, **without** tools, asks for JSON only. Example:

```json
{
  "memory": [
    {"action": "add", "target": "MEMORY", "text": "project is exp1"}
  ],
  "skills": []
}
```

If the `memory` tool already added that line, you may get a duplicate bullet; that is harmless for this sample. If the model skipped the tool and only learned here, this is the write that matters.

Event `step=learn` → React node **What did I learn?**

#### Step A8 — `update_memory`

Applies `memory_writes`, emits `memory_update`, inserts a SQLite row (`task`, first 500 chars of the answer, `success`). Graph **END**.

React lights **Update Memory / Skill**, then the display-only **Future Task / Reuse** node (not a LangGraph node — it means “disk is ready for the next run”).

Short-term `messages` for Task A are now gone. Long-term `MEMORY.md` still has `project is exp1`.

---

### Task B — “What project is this?”

You type a **new** task. That is a new `run_id` and a new `load_context`.

#### Step B1 — `load_context` again

Snapshot now includes:

```
## MEMORY.md
# MEMORY

- project is exp1
```

The system prompt **tells** the model the fact before any tool is used. Skill index is still there, but this question may not need a skill.

#### Step B2 — `reason`

The fact is already in context. The model can answer “This project is exp1” with **no tools**.

- `success` immediately.
- `reflect` might return empty arrays (`nothing durable`).
- `update_memory` writes `"none"` and still saves the run.

That is reuse: Task A wrote long-term memory; Task B’s frozen snapshot made the goal trivial.

If the model is unsure, it could still call `search_sessions("exp1")` or `memory` — it does not have to. The design is that **it decides**.

---

### What you would see in the UIs

**TUI**

```
[reason] I’ll load inspect-workspace, then list files.
[act]    load_skill {"name": "inspect-workspace"}
[observe] ---
name: inspect-workspace
...
[reason] Listing the workspace.
[act]    list_dir {"path": "."}
[observe] (empty)
[reason] Recording the project name.
[act]    memory {"action": "add", "target": "MEMORY", "text": "project is exp1"}
[observe] added to MEMORY
[success] Workspace is empty. Noted that this project is exp1.
[learn]  {"memory":[...],"skills":[]}
```

**React graph** (same events)

`Task → Reason ⇄ Act ⇄ Observe → SUCCESS → Learn → Update Memory → Reuse`

Nodes highlight as events arrive. A failed observe is drawn red.

---

## 7. Interrupt (optional path)

If you press Ctrl+C / Stop during **act**:

1. `kill_current_shell()` stops the subprocess.
2. Observation becomes `user interrupted: …`, `status=interrupted`.
3. `observe` → `wait_redirect` (controlled graph only).
4. Your next message is appended as a user turn; `reason` continues **the same run**.

A brand-new task (`POST /runs`) is a different run, not a redirect.

---

## 8. Where to read the code

| Topic | File |
| --- | --- |
| State | `exp1dir/backend/agent/state.py` |
| Nodes + routers | `exp1dir/backend/agent/nodes.py` |
| Simple graph | `exp1dir/backend/agent/graph.py` |
| Live graph + interrupt | `exp1dir/backend/agent/run_manager.py` |
| System prompt | `exp1dir/backend/agent/prompts.py` |
| Tool registry | `exp1dir/backend/tools/registry.py` |
| Long-term markdown | `exp1dir/backend/memory/store.py` |
| Skills | `exp1dir/backend/tools/skill_tool.py` |
| Gateway | `exp1dir/backend/api/app.py` |
| How to run | `exp1dir/README.md` |

Related design notes: `docs/superpowers/specs/2026-08-12-exp1-hermes-agent-design.md`.
