# exp1 Hermes Agent

LangGraph agent with a Textual TUI and React loop graph. Ollama powers reasoning; the FastAPI gateway streams runs to the terminal and browser.

## Setup

From the repo root:

```powershell
cd exp1dir
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Copy the example env file and point it at your Ollama instance:

```powershell
copy .env.example .env
```

Edit `.env` and set `OLLAMA_BASE_URL` (and optionally `OLLAMA_MODEL` to pin a default). Other variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `OLLAMA_API_KEY` | *(empty)* | Optional API key |
| `OLLAMA_MODEL` | *(empty)* | Optional default model |
| `GATEWAY_HOST` | `127.0.0.1` | Gateway bind address |
| `GATEWAY_PORT` | `8765` | Gateway port |

## Run the TUI

After `pip install -e .`, the `hermes` console script is on your PATH (defined in `pyproject.toml` as `tui.main:main`).

**Option A — gateway + TUI in one step** (auto-starts the gateway if it is not running):

```powershell
hermes
```

**Option B — separate gateway process** (useful for React-only or debugging):

Terminal 1:

```powershell
hermes serve
# equivalent: python -m tui.main serve
```

Terminal 2:

```powershell
hermes
```

On startup the TUI prints Ollama health and the active model.

### TUI usage

- **`/model`** — list available models (active model marked with `*`).
- **`/model <name>`** — switch the active model.
- Type a task in the editor and press **Ctrl+Enter** to send.
- **Ctrl+C** interrupts the current run; your next message redirects that run.

Other commands: `/memory`, `/skills`, `/history`, `/quit`.

## React loop graph

In another terminal (with the gateway running):

```powershell
cd web
npm install
npm run dev
```

Open the Vite dev URL (default **http://localhost:5173**). The UI connects to `http://127.0.0.1:8765` by default.

If you changed `GATEWAY_PORT`, set `VITE_GATEWAY` when starting Vite:

```powershell
$env:VITE_GATEWAY="http://127.0.0.1:9000"; npm run dev
```

## Manual smoke test

1. Start the gateway and TUI (`hermes` or `hermes serve` + `hermes`).
2. Ask the agent to **list files in the workspace** (sandbox under `.hermes/workspace/`).
3. Ask it to **remember a fact** (e.g. your favorite color); confirm with `/memory`.
4. Start a **second task** that should reuse that fact without re-stating it.
5. With `npm run dev` running, watch the **Reason → Act → Observe → Learn** graph update live.

## Tests

```powershell
python -m pytest -v
```
