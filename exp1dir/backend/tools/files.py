from backend.paths import HermesPaths
from backend.tools.sandbox import SandboxError, resolve_under


def write_file(paths: HermesPaths, path: str, content: str) -> str:
    try:
        target = resolve_under(paths.workspace, path)
    except SandboxError as e:
        return f"ERROR: {e}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"wrote {path} ({len(content)} bytes)"


def read_file(paths: HermesPaths, path: str) -> str:
    try:
        target = resolve_under(paths.workspace, path)
    except SandboxError as e:
        return f"ERROR: {e}"
    if not target.exists():
        return f"ERROR: not found: {path}"
    return target.read_text(encoding="utf-8")


def list_dir(paths: HermesPaths, path: str) -> str:
    try:
        target = resolve_under(paths.workspace, path)
    except SandboxError as e:
        return f"ERROR: {e}"
    if not target.exists():
        return f"ERROR: not found: {path}"
    if not target.is_dir():
        return f"ERROR: not a directory: {path}"
    names = sorted(child.name + ("/" if child.is_dir() else "") for child in target.iterdir())
    return "\n".join(names) if names else "(empty)"
