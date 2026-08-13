from backend.memory.sessions import SessionStore


def search_sessions(store: SessionStore, query: str) -> str:
    rows = store.search(query)
    if not rows:
        return "(no matches)"
    return "\n".join(f"{rid}: {task} [{status}] {summary}" for rid, task, summary, status in rows)
