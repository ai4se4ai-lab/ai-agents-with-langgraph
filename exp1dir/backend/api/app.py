import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.agent.events import EventLog
from backend.agent.run_manager import RunManager
from backend.llm.ollama import ModelError, list_models, resolve_active, set_active
from backend.memory.sessions import SessionStore
from backend.memory.store import MemoryStore, ensure_home
from backend.tools.mcp import McpRegistry
from backend.tools.mcp_config import UnknownMcpServer, set_server_enabled
from backend.tools.skill_tool import skill_index


class TaskIn(BaseModel):
    task: str


class ModelIn(BaseModel):
    model: str


class MessageIn(BaseModel):
    text: str


class InterruptIn(BaseModel):
    note: str = ""


class McpEnabledIn(BaseModel):
    enabled: bool


def create_app(paths, llm, settings: dict):
    ensure_home(paths)
    mcp = McpRegistry(paths)
    mcp.reload()
    mgr = RunManager(paths, llm, mcp=mcp)

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.mgr = mgr
    app.state.paths = paths
    app.state.settings = settings
    app.state.mcp = mcp

    def tags():
        return list_models(settings["ollama_base_url"], settings.get("ollama_api_key", ""))

    def active():
        try:
            return resolve_active(paths, tags(), settings.get("ollama_model", ""))
        except ModelError:
            return ""

    @app.get("/health")
    def health():
        try:
            models = tags()
            err = ""
        except Exception as e:
            models, err = [], str(e)
        return {
            "ok": not err,
            "ollama": settings["ollama_base_url"],
            "active_model": active() if models else "",
            "error": err,
        }

    @app.get("/models")
    def models():
        try:
            return {"models": tags(), "active": active()}
        except Exception as e:
            raise HTTPException(502, f"cannot reach Ollama at {settings['ollama_base_url']}: {e}")

    @app.post("/models/active")
    def set_model(body: ModelIn):
        try:
            name = set_active(paths, body.model, tags())
        except ModelError as e:
            raise HTTPException(400, str(e))
        return {"model": name}

    @app.post("/runs")
    def start_run(body: TaskIn):
        skip = settings.get("skip_ollama")
        model = ""
        try:
            model = active()
        except Exception as e:
            if not skip:
                raise HTTPException(502, f"cannot reach Ollama at {settings['ollama_base_url']}: {e}")
        if not skip and not model:
            raise HTTPException(502, f"cannot reach Ollama at {settings['ollama_base_url']}")
        run_id = mgr.start(body.task, model=model or "scripted")
        return {"run_id": run_id}

    @app.post("/runs/{run_id}/interrupt")
    def interrupt(run_id: str, body: InterruptIn):
        mgr.interrupt(run_id, body.note)
        return {"ok": True}

    @app.post("/runs/{run_id}/message")
    def message(run_id: str, body: MessageIn):
        mgr.send_message(run_id, body.text)
        return {"ok": True}

    @app.get("/memory")
    def memory():
        return {"snapshot": MemoryStore(paths).snapshot()}

    @app.get("/skills")
    def skills():
        return {"skills": skill_index(paths)}

    @app.get("/runs")
    def runs():
        rows = SessionStore(paths).recent()
        return {"runs": [{"id": r[0], "task": r[1], "summary": r[2], "status": r[3]} for r in rows]}

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

    def _run_finished(run_id: str, events: list) -> bool:
        if any(e.get("step") == "memory_update" for e in events):
            return True
        rec = mgr.runs.get(run_id)
        if rec is None:
            return True
        thread = rec.get("thread")
        return bool(thread and not thread.is_alive())

    def _event_key(event: dict) -> tuple:
        return (
            event.get("run_id"),
            event.get("step"),
            event.get("cycle"),
            event.get("text"),
            event.get("tool"),
            event.get("observation"),
            event.get("input"),
        )

    def _push(loop: asyncio.AbstractEventLoop, q: asyncio.Queue, event: dict) -> None:
        try:
            loop.call_soon_threadsafe(q.put_nowait, event)
        except RuntimeError:
            pass

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: str):
        await ws.accept()
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            if event.get("run_id") == run_id:
                _push(loop, q, event)

        mgr.subscribe(on_event)
        sent: set[tuple] = set()
        try:

            async def send_event(event: dict) -> bool:
                key = _event_key(event)
                if key in sent:
                    return False
                sent.add(key)
                await ws.send_json(event)
                return event.get("step") == "memory_update"

            for event in EventLog(paths, run_id).replay():
                if await send_event(event):
                    return
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    logged = EventLog(paths, run_id).replay()
                    for event in logged:
                        if await send_event(event):
                            return
                    if _run_finished(run_id, logged):
                        return
                    continue
                if await send_event(event):
                    return
        except WebSocketDisconnect:
            pass
        finally:
            mgr.unsubscribe(on_event)
            try:
                await ws.close()
            except Exception:
                pass

    @app.websocket("/ws/events")
    async def ws_all(ws: WebSocket):
        await ws.accept()
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            _push(loop, q, event)

        mgr.subscribe(on_event)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    continue
                await ws.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            mgr.unsubscribe(on_event)
            try:
                await ws.close()
            except Exception:
                pass

    return app
