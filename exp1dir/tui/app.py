import json

import websockets
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Log, TextArea
from tui.client import GatewayClient
from tui.commands import parse_command


class HermesApp(App):
    CSS = "TextArea { height: 8; } Log { height: 1fr; }"
    BINDINGS = [Binding("ctrl+enter", "submit", "Send"), Binding("ctrl+c", "interrupt", "Interrupt")]

    def __init__(self, client: GatewayClient):
        super().__init__()
        self.client = client
        self.run_id = None
        self.awaiting_redirect = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="log")
        yield TextArea(id="in")
        yield Footer()

    def on_mount(self):
        h = self.client.health()
        self.query_one("#log", Log).write_line(
            f"Ollama {h.get('ollama')} model={h.get('active_model')} err={h.get('error')}"
        )

    def action_interrupt(self):
        if self.run_id:
            self.client.interrupt(self.run_id, "")
            self.awaiting_redirect = True
            self.query_one("#log", Log).write_line("[interrupt] next send redirects this run")

    def action_submit(self):
        box = self.query_one("#in", TextArea)
        text = box.text.strip()
        box.text = ""
        if not text:
            return
        parsed = parse_command(text)
        log = self.query_one("#log", Log)
        if parsed:
            name, args = parsed
            if name == "quit":
                self.exit()
                return
            if name == "model" and not args:
                data = self.client.models()
                log.write_line(
                    "models: "
                    + ", ".join(
                        f"{'*' + m if m == data.get('active') else m}" for m in data.get("models", [])
                    )
                )
                return
            if name == "model" and args:
                try:
                    got = self.client.set_model(args[0])
                    log.write_line(f"active model: {got['model']}")
                except Exception as e:
                    log.write_line(f"model error: {e}")
                return
            if name == "memory":
                log.write_line(self.client.memory()["snapshot"])
                log.write_line("(disk writes apply on the next task)")
                return
            if name == "skills":
                log.write_line(json.dumps(self.client.skills(), indent=2))
                return
            if name == "history":
                log.write_line(json.dumps(self.client.history(), indent=2))
                return
            if name == "interrupt":
                self.action_interrupt()
                return
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
            log.write_line(f"unknown command /{name}")
            return
        if self.awaiting_redirect and self.run_id:
            self.client.message(self.run_id, text)
            self.awaiting_redirect = False
            return
        self.run_id = self.client.start(text)
        self.run_worker(self._stream(self.run_id), exclusive=False)

    async def _stream(self, run_id: str):
        log = self.query_one("#log", Log)
        url = self.client.base.replace("http", "ws") + f"/ws/runs/{run_id}"
        async with websockets.connect(url) as ws:
            async for raw in ws:
                e = json.loads(raw)
                step = e.get("step", "")
                if step == "act" and e.get("mcp_server"):
                    log.write_line(f"[act] {e['mcp_server']} / {e.get('mcp_tool')} ({e.get('tool')}) {e.get('input') or ''}")
                else:
                    log.write_line(f"[{step}] {e.get('text') or e.get('observation') or e.get('input') or ''}")
