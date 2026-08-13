# exp1 Hermes Agent

LangGraph agent with a Textual TUI and a React loop graph. Ollama powers reasoning. A FastAPI gateway streams runs to the terminal and the browser.

You need **two UIs** and **one API**. Do not open the API in the browser expecting a page.

| What | How you start it | Where you use it |
| --- | --- | --- |
| Agent TUI (chat) | `hermes` | The terminal |
| API gateway | Started automatically by `hermes` | `http://127.0.0.1:8765` — JSON API only |
| React loop graph | `npm run dev` **from `web/`** | **http://localhost:5173** |

`http://127.0.0.1:8765/` returns `{"detail":"Not Found"}` by design. There is no HTML there. Health check: `http://127.0.0.1:8765/health`.

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) running, with at least one model pulled (for example `ollama pull qwen2.5-coder:7b`)
- Node.js + npm (only if you want the React graph)

## 1. Python setup

From this folder (`exp1dir/`), not the repo root:

```powershell
cd exp1dir
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env` and set `OLLAMA_BASE_URL` to your Ollama instance (default `http://127.0.0.1:11434`). Optionally set `OLLAMA_MODEL` to pin a default.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `OLLAMA_API_KEY` | *(empty)* | Optional API key |
| `OLLAMA_MODEL` | *(empty)* | Optional default model |
| `GATEWAY_HOST` | `127.0.0.1` | Gateway bind address |
| `GATEWAY_PORT` | `8765` | Gateway port |

Keep the venv activated in any terminal where you run `hermes`. If PowerShell says `hermes` is not recognized, you are not in this folder with `.venv` activated.

## 2. Run the TUI (required)

From `exp1dir/` with the venv active:

```powershell
hermes
```

That starts the gateway on port 8765 if it is not already running, then opens the TUI. On startup the TUI prints Ollama health and the active model.

Type a task in the editor and press **Ctrl+Enter** to send.

### TUI commands

- **`/model`** — list available models (active model marked with `*`)
- **`/model <name>`** — switch the active model
- **Ctrl+C** — interrupt the current run; your next message redirects that run
- **`/memory`**, **`/skills`**, **`/history`**, **`/mcp`**, **`/quit`**

### Optional: gateway in its own process

Use this if you only want the React UI, or to debug the API.

Terminal 1 (`exp1dir/`, venv active):

```powershell
hermes serve
```

Terminal 2 (`exp1dir/`, venv active):

```powershell
hermes
```

## 3. Run the React loop graph (optional)

The React app is in **`exp1dir/web/`**. `npm install` from `exp1dir/` will fail (`package.json` is not there).

## MCP servers

Edit `exp1dir/.hermes/config.json` and add `mcp_servers`. Each entry is either **stdio** (`command` / `args` / `env`) or **HTTP** (`url` / `headers`). Put secrets in `.env` and reference them as `${VAR}` (or `${env:VAR}`).

After editing, run **`/mcp reload`** in the TUI or click **Reload** in React. The **next** task binds the new tools; an in-flight run keeps its snapshot.

- **`/mcp`** — list servers (transport, enabled, connected, tools, errors).
- **`/mcp enable <name>`** / **`/mcp disable <name>`** — persist `enabled` and reload (does not drop `model` or other servers).

Example (do not commit API keys):

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

In React, Act labels MCP calls as `server / tool`. The side list marks servers used this run.

## React loop graph

In a **new** terminal (venv not required):

```powershell
cd exp1dir\web
npm install
npm run dev
```

Open **http://localhost:5173**. That UI talks to the gateway at `http://127.0.0.1:8765` in the background. Leave `hermes` running while you use it.

If you changed `GATEWAY_PORT`, set `VITE_GATEWAY` when starting Vite:

```powershell
$env:VITE_GATEWAY="http://127.0.0.1:9000"; npm run dev
```

## Manual smoke test

1. Start the TUI (`hermes`). Optionally start the React app (`cd web; npm run dev`) and open http://localhost:5173.
2. Ask the agent to **list files in the workspace** (sandbox under `.hermes/workspace/`).
3. Ask it to **remember a fact** (e.g. your favorite color); confirm with `/memory`.
4. Start a **second task** that should reuse that fact without re-stating it.
5. With Vite running, watch the **Reason → Act → Observe → Learn** graph update live.

## Tests

From `exp1dir/` with the venv active:

```powershell
python -m pytest -v
```
