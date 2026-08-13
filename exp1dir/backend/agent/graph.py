from functools import partial
from langgraph.graph import END, START, StateGraph
from backend.agent.nodes import act, load_context, observe, reason, reflect, route_after_reason, update_memory
from backend.agent.state import AgentState
from backend.tools.registry import build_tool_fns


def build_graph(paths, llm, emit, tools=None):
    tools = tools or build_tool_fns(paths)

    def wrap(fn):
        return partial(fn, paths=paths, llm=llm, tools=tools, emit=emit)

    g = StateGraph(AgentState)
    g.add_node("load_context", wrap(load_context))
    g.add_node("reason", wrap(reason))
    g.add_node("act", wrap(act))
    g.add_node("observe", wrap(observe))
    g.add_node("reflect", wrap(reflect))
    g.add_node("update_memory", wrap(update_memory))
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "reason")
    g.add_conditional_edges("reason", route_after_reason, {"act": "act", "reflect": "reflect"})
    g.add_edge("act", "observe")
    g.add_edge("observe", "reason")
    g.add_edge("reflect", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile()


def run_task(paths, llm, task: str, max_cycles: int = 15, on_event=None, model: str = "scripted", tools=None):
    events = []

    def emit(event):
        events.append(event)
        if on_event:
            on_event(event)

    graph = build_graph(paths, llm, emit, tools=tools)
    result = graph.invoke(
        {
            "task": task,
            "run_id": "",
            "messages": [],
            "memory_snapshot": "",
            "skill_index": [],
            "loaded_skills": [],
            "cycle": 0,
            "max_cycles": max_cycles,
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
    result["_events"] = events
    return result
