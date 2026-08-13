from pathlib import Path


class SandboxError(ValueError):
    pass


def resolve_under(root: Path, user_path: str) -> Path:
    root = root.resolve()
    candidate = (root / user_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SandboxError(f"path is outside sandbox: {user_path}") from exc
    return candidate
