from backend.memory.store import MemoryStore


def memory_tool(store: MemoryStore, action: str, target: str, text: str = "", old_text: str = "") -> str:
    action = action.lower()
    try:
        if action == "add":
            return store.add(target, text)
        if action == "replace":
            return store.replace(target, text, old_text)
        if action == "remove":
            return store.remove(target, old_text)
        return f"ERROR: unknown action {action}"
    except ValueError as e:
        return f"ERROR: {e}"
