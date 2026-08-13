def event_body(event: dict) -> str:
    if event.get("step") == "act" and event.get("mcp_server"):
        label = f"{event.get('mcp_server')} / {event.get('mcp_tool') or ''} ({event.get('tool') or ''})".strip()
        rest = event.get("input") or event.get("text") or ""
        return f"{label} {rest}".strip()
    return event.get("text") or event.get("observation") or event.get("input") or ""


def classify_step(step: str) -> str:
    if step == "task":
        return "task"
    if step == "success":
        return "final"
    return "thinking"


def split_events(events: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {"task": [], "thinking": [], "final": []}
    for event in events:
        buckets[classify_step(event.get("step", ""))].append(event)
    return buckets
