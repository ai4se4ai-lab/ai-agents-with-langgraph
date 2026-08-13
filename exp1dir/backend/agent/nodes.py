import json
import re
import uuid
from backend.agent.events import make_event
from backend.agent.prompts import SYSTEM
from backend.memory.store import MemoryStore, ensure_home
from backend.tools.skill_tool import skill_index

REFLECT_PROMPT = (
    "The task is done (or stopped). What did I learn that would help a future task? "
    "Reply with JSON only: {\"memory\": [{\"action\": \"add|replace|remove\", \"target\": \"MEMORY|USER\", "
    "\"text\": \"...\", \"old_text\": \"\"}], \"skills\": [{\"action\": \"create|update\", \"name\": \"...\", "
    "\"description\": \"...\", \"body\": \"...\"}]}. If nothing durable, use empty arrays."
)


def parse_text_tool_calls(content: str, tool_names: set[str]) -> list[dict]:
    text = (content or "").strip()
    if not text or not tool_names:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    blob = fence.group(1).strip() if fence else text
    try:
        data = json.loads(blob)
        candidates = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        start, end = blob.find("{"), blob.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            candidates = [json.loads(blob[start : end + 1])]
        except json.JSONDecodeError:
            return []
    out = []
    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = item.get("name") or fn.get("name")
        args = item.get("arguments") or item.get("args") or fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name in tool_names and isinstance(args, dict):
            out.append({"id": f"text-{i}", "name": name, "args": args})
    return out


def load_context(state, paths, llm, tools, emit, control=None):
    ensure_home(paths)
    store = MemoryStore(paths)
    snapshot = store.snapshot()
    index = skill_index(paths)
    run_id = state.get("run_id") or uuid.uuid4().hex
    mcp_lines = []
    for name, fn in (tools or {}).items():
        if getattr(fn, "_mcp_server", ""):
            doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
            mcp_lines.append(f"- {name}: {doc}".rstrip(": "))
    mcp_index = "\n".join(mcp_lines) if mcp_lines else "(none)"
    sys_prompt = SYSTEM.format(memory_snapshot=snapshot, skill_index=json.dumps(index), mcp_index=mcp_index)
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": state["task"]}]
    emit(make_event(run_id, "task", text=state["task"], model=state.get("active_model", "")))
    return {
        "run_id": run_id,
        "messages": messages,
        "memory_snapshot": snapshot,
        "skill_index": index,
        "loaded_skills": [],
        "cycle": 0,
        "pending_tool_calls": [],
        "pending_observations": [],
        "last_observation": "",
        "status": "running",
        "final_answer": "",
        "reflection": "",
        "memory_writes": [],
    }


def reason(state, paths, llm, tools, emit, control=None):
    if state.get("status") == "running" and state.get("cycle", 0) >= state.get("max_cycles", 15):
        emit(make_event(state["run_id"], "error", cycle=state["cycle"], text="step limit"))
        return {"status": "capped", "final_answer": state.get("final_answer") or "stopped: step limit"}
    emit(make_event(state["run_id"], "reason", cycle=state.get("cycle", 0), text="thinking", model=state.get("active_model", "")))
    last_err = None
    for _ in range(2):
        try:
            resp = llm.invoke(state["messages"], tools)
            last_err = None
            break
        except Exception as e:
            last_err = e
            emit(make_event(state["run_id"], "error", cycle=state["cycle"], text=str(e), model=state.get("active_model", "")))
    if last_err is not None:
        return {"status": "failed", "final_answer": f"LLM error: {last_err}"}
    pending = [tc.__dict__ if hasattr(tc, "__dict__") else tc for tc in (resp.tool_calls or [])]
    if not pending:
        pending = parse_text_tool_calls(resp.content, set(tools))
    messages = list(state["messages"]) + [{"role": "assistant", "content": resp.content, "tool_calls": pending}]
    emit(make_event(state["run_id"], "reason", cycle=state["cycle"], text=resp.content, model=state.get("active_model", "")))
    if pending:
        return {"messages": messages, "pending_tool_calls": pending, "status": "running"}
    emit(make_event(state["run_id"], "success", cycle=state["cycle"], text=resp.content, model=state.get("active_model", "")))
    return {"messages": messages, "pending_tool_calls": [], "final_answer": resp.content, "status": "success"}


def act(state, paths, llm, tools, emit, control=None):
    observations = []
    for call in state.get("pending_tool_calls") or []:
        name = call["name"] if isinstance(call, dict) else call.name
        args = call["args"] if isinstance(call, dict) else call.args
        cid = call.get("id") if isinstance(call, dict) else call.id
        fn = tools.get(name)
        mcp_server = getattr(fn, "_mcp_server", "") if fn is not None else ""
        mcp_tool = getattr(fn, "_mcp_tool", "") if fn is not None else ""
        emit(make_event(
            state["run_id"], "act", cycle=state["cycle"], tool=name,
            input=json.dumps(args), model=state.get("active_model", ""),
            mcp_server=mcp_server, mcp_tool=mcp_tool,
        ))
        if fn is None:
            obs = f"ERROR: unknown tool {name}"
        else:
            try:
                obs = fn(**args)
            except TypeError:
                obs = fn(*args.values()) if args else fn()
            except Exception as e:
                obs = f"ERROR: {e}"
        if control and (control.get("cancel") or control.get("did_interrupt")):
            obs = f"user interrupted: {control.get('note') or ''}".strip()
            observations.append({"tool_call_id": cid, "name": name, "content": obs})
            status = "stopped" if control.get("hard_stop") else "interrupted"
            return {"pending_observations": observations, "status": status, "last_observation": obs}
        observations.append({"tool_call_id": cid, "name": name, "content": str(obs)})
    return {"pending_observations": observations}


def observe(state, paths, llm, tools, emit, control=None):
    messages = list(state["messages"])
    chunks = []
    for obs in state.get("pending_observations") or []:
        messages.append({"role": "tool", "content": obs["content"], "tool_call_id": obs.get("tool_call_id", "")})
        chunks.append(obs["content"])
        emit(make_event(state["run_id"], "observe", cycle=state["cycle"], tool=obs.get("name", ""), observation=obs["content"], model=state.get("active_model", "")))
    return {
        "messages": messages,
        "last_observation": "\n".join(chunks),
        "pending_tool_calls": [],
        "pending_observations": [],
        "cycle": state.get("cycle", 0) + 1,
    }


def reflect(state, paths, llm, tools, emit, control=None):
    messages = list(state["messages"]) + [{"role": "user", "content": REFLECT_PROMPT}]
    try:
        resp = llm.invoke(messages, tools=[])
        raw = resp.content
    except Exception as e:
        emit(make_event(state["run_id"], "learn", cycle=state["cycle"], text=f"ERROR: {e}"))
        return {"reflection": "", "memory_writes": []}
    writes = []
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        data = json.loads(raw[start : end + 1]) if start >= 0 else {}
        for w in data.get("memory") or []:
            writes.append({**w, "kind": "memory"})
        for s in data.get("skills") or []:
            writes.append({**s, "kind": "skill"})
    except Exception:
        writes = []
    emit(make_event(state["run_id"], "learn", cycle=state["cycle"], text=raw, model=state.get("active_model", "")))
    return {"reflection": raw, "memory_writes": writes}


def update_memory(state, paths, llm, tools, emit, control=None):
    from backend.memory.sessions import SessionStore
    from backend.memory.store import MemoryStore
    from backend.tools.skill_tool import skill_manage
    from backend.tools.memory_tool import memory_tool

    store = MemoryStore(paths)
    applied = []
    for w in state.get("memory_writes") or []:
        kind = w.get("kind") or ("skill" if "name" in w and "body" in w else "memory")
        if kind == "skill":
            applied.append(skill_manage(paths, w.get("action", "create"), w.get("name", ""), w.get("description", ""), w.get("body", "")))
        else:
            applied.append(
                memory_tool(store, w.get("action", "add"), w.get("target", "MEMORY"), w.get("text", ""), w.get("old_text", ""))
            )
    summary = "; ".join(applied) if applied else "none"
    emit(make_event(state["run_id"], "memory_update", cycle=state["cycle"], text=summary, model=state.get("active_model", "")))
    SessionStore(paths).save(state["run_id"], state.get("task", ""), state.get("final_answer", "")[:500], state.get("status", ""))
    return {}


def wait_redirect(state, paths, llm, tools, emit, control=None):
    control = control or {}
    ev = control.get("redirect_event")
    if ev is not None:
        ev.wait(timeout=300)
    control["did_interrupt"] = False
    control["note"] = ""
    text = (control.get("redirect_text") or "").strip()
    messages = list(state["messages"]) + [{"role": "user", "content": text or "(continue)"}]
    return {"messages": messages, "status": "running", "pending_tool_calls": []}


def route_after_observe(state) -> str:
    if state.get("status") == "stopped":
        return "reflect"
    if state.get("status") == "interrupted":
        return "wait_redirect"
    return "reason"


def route_after_reason(state) -> str:
    if state.get("status") in ("success", "failed", "capped"):
        return "reflect"
    if state.get("pending_tool_calls"):
        return "act"
    return "reflect"
