import json

import websockets
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Footer, Header, Static, TextArea
from tui.client import GatewayClient
from tui.commands import parse_command
from tui.display import classify_step, event_body


class HermesApp(App):
    CSS = "TextArea { height: 8; } #log { height: 1fr; } Collapsible { margin-bottom: 1; }"
    BINDINGS = [Binding("ctrl+enter", "submit", "Send"), Binding("ctrl+c", "interrupt", "Interrupt")]

    def __init__(self, client: GatewayClient):
        super().__init__()
        self.client = client
        self.run_id = None
        self.awaiting_redirect = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield TextArea(id="in")
        yield Footer()

    def _write(self, text: str) -> None:
        log = self.query_one("#log", VerticalScroll)
        log.mount(Static(text))
        log.scroll_end(animate=False)

    def on_mount(self):
        h = self.client.health()
        self._write(f"Ollama {h.get('ollama')} model={h.get('active_model')} err={h.get('error')}")

    def action_interrupt(self):
        if self.run_id:
            self.client.interrupt(self.run_id, "")
            self.awaiting_redirect = True
            self._write("[interrupt] next send redirects this run")

    def action_submit(self):
        box = self.query_one("#in", TextArea)
        text = box.text.strip()
        box.text = ""
        if not text:
            return
        parsed = parse_command(text)
        if parsed:
            name, args = parsed
            if name == "quit":
                self.exit()
                return
            if name == "model" and not args:
                data = self.client.models()
                self._write(
                    "models: "
                    + ", ".join(
                        f"{'*' + m if m == data.get('active') else m}" for m in data.get("models", [])
                    )
                )
                return
            if name == "model" and args:
                try:
                    got = self.client.set_model(args[0])
                    self._write(f"active model: {got['model']}")
                except Exception as e:
                    self._write(f"model error: {e}")
                return
            if name == "memory":
                self._write(self.client.memory()["snapshot"])
                self._write("(disk writes apply on the next task)")
                return
            if name == "skills":
                self._write(json.dumps(self.client.skills(), indent=2))
                return
            if name == "history":
                self._write(json.dumps(self.client.history(), indent=2))
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
                        self._write("usage: /mcp | /mcp reload | /mcp enable <name> | /mcp disable <name>")
                        return
                    self._write(format_mcp_status(data))
                except Exception as e:
                    self._write(f"mcp error: {e}")
                return
            self._write(f"unknown command /{name}")
            return
        if self.awaiting_redirect and self.run_id:
            self.client.message(self.run_id, text)
            self.awaiting_redirect = False
            return
        self.run_id = self.client.start(text)
        self.run_worker(self._stream(self.run_id), exclusive=False)

    async def _stream(self, run_id: str):
        log = self.query_one("#log", VerticalScroll)
        thinking = None
        url = self.client.base.replace("http", "ws") + f"/ws/runs/{run_id}"
        async with websockets.connect(url) as ws:
            async for raw in ws:
                e = json.loads(raw)
                step = e.get("step", "")
                body = event_body(e)
                block = Static(f"[{step}]\n{body}" if body else f"[{step}]")
                kind = classify_step(step)
                if kind == "thinking":
                    if thinking is None:
                        thinking = Collapsible(title="thinking", collapsed=True)
                        await log.mount(thinking)
                    await thinking.mount(block)
                else:
                    await log.mount(block)
                log.scroll_end(animate=False)
