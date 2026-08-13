import subprocess
from backend.paths import HermesPaths

MAX = 50_000


def run_shell(paths: HermesPaths, command: str, timeout: float = 30.0) -> str:
    paths.workspace.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=paths.workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout after {timeout}s"
    out = (proc.stdout or "") + (proc.stderr or "")
    if len(out) > MAX:
        out = out[:MAX] + "\n...[truncated]"
    return f"exit={proc.returncode}\n{out}"
