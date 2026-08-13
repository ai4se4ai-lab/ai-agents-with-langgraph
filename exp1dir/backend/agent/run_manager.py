import threading
import uuid
from functools import partial
from langgraph.graph import END, START, StateGraph
from backend.agent.events import EventLog
from backend.agent.nodes import (
    act,
    load_context,
    observe,
    reason,
    reflect,
    route_after_observe,
    route_after_reason,
    update_memory,
    wait_redirect,
)
from backend.agent.state import AgentState
from backend.tools.registry import build_tool_fns
from backend.tools.shell import kill_current_shell


def build_controlled_graph(paths, llm, emit, tools, control):
    def wrap(fn):
        return partial(fn, paths=paths, llm=llm, tools=tools, emit=emit, control=control)

    g = StateGraph(AgentState)
    g.add_node("load_context", wrap(load_context))
    g.add_node("reason", wrap(reason))
    g.add_node("act", wrap(act))
    g.add_node("observe", wrap(observe))
    g.add_node("wait_redirect", wrap(wait_redirect))
    g.add_node("reflect", wrap(reflect))
    g.add_node("update_memory", wrap(update_memory))
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "reason")
    g.add_conditional_edges("reason", route_after_reason, {"act": "act", "reflect": "reflect"})
    g.add_edge("act", "observe")
    g.add_conditional_edges(
        "observe", route_after_observe, {"wait_redirect": "wait_redirect", "reason": "reason", "reflect": "reflect"}
    )
    g.add_edge("wait_redirect", "reason")
    g.add_edge("reflect", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile()


class RunManager:
    def __init__(self, paths, llm, mcp=None):
        self.paths = paths
        self.llm = llm
        self.mcp = mcp
        self.runs = {}
        self.listeners = []

    def subscribe(self, fn):
        self.listeners.append(fn)

    def unsubscribe(self, fn):
        try:
            self.listeners.remove(fn)
        except ValueError:
            pass

    def start(self, task: str, model: str = "scripted") -> str:
        run_id = uuid.uuid4().hex
        control = {
            "cancel": False,
            "note": "",
            "redirect_event": threading.Event(),
            "redirect_text": "",
            "did_interrupt": False,
            "hard_stop": False,
        }
        rec = {"id": run_id, "control": control, "result": None, "events": [], "thread": None, "status": "running"}
        self.runs[run_id] = rec

        def emit(event):
            event = dict(event)
            event["run_id"] = run_id
            EventLog(self.paths, run_id).append(event)
            rec["events"].append(event)
            for fn in list(self.listeners):
                fn(event)

        def worker():
            extra = self.mcp.tool_fns() if self.mcp else {}
            tools = {**build_tool_fns(self.paths), **extra}
            graph = build_controlled_graph(self.paths, self.llm, emit, tools, control)
            rec["result"] = graph.invoke(
                {
                    "task": task,
                    "run_id": run_id,
                    "messages": [],
                    "memory_snapshot": "",
                    "skill_index": [],
                    "loaded_skills": [],
                    "cycle": 0,
                    "max_cycles": 15,
                    "pending_tool_calls": [],
                    "pending_observations": [],
                    "last_observation": "",
                    "status": "running",
                    "final_answer": "",
                    "reflection": "",
                    "memory_writes": [],
                    "active_model": model,
                }
            )
            rec["status"] = rec["result"].get("status", "success")

        t = threading.Thread(target=worker, daemon=True)
        rec["thread"] = t
        t.start()
        return run_id

    def interrupt(self, run_id: str, note: str = "") -> None:
        rec = self.runs[run_id]
        rec["control"]["cancel"] = True
        rec["control"]["note"] = note
        rec["control"]["did_interrupt"] = True
        kill_current_shell()

    def stop(self, run_id: str, note: str = "") -> None:
        """Hard stop: cancel the in-flight tool and end the run instead of waiting to redirect."""
        rec = self.runs[run_id]
        rec["control"]["cancel"] = True
        rec["control"]["note"] = note
        rec["control"]["did_interrupt"] = True
        rec["control"]["hard_stop"] = True
        kill_current_shell()

    def send_message(self, run_id: str, text: str) -> None:
        rec = self.runs[run_id]
        rec["control"]["redirect_text"] = text
        rec["control"]["cancel"] = False
        rec["control"]["redirect_event"].set()

    def join(self, run_id: str, timeout: float = 60):
        self.runs[run_id]["thread"].join(timeout=timeout)
        return self.runs[run_id]["result"]
