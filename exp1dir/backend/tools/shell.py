import subprocess
import sys
from backend.paths import HermesPaths

MAX = 50_000
CURRENT_PROC = []


def run_shell(paths: HermesPaths, command: str, timeout: float = 30.0) -> str:
    paths.workspace.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=paths.workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    CURRENT_PROC.append(proc)
    try:
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"ERROR: timeout after {timeout}s"
        out = out or ""
        if len(out) > MAX:
            out = out[:MAX] + "\n...[truncated]"
        if proc.returncode not in (0, None) and proc.returncode < 0:
            return f"exit={proc.returncode}\nuser interrupted: process killed\n{out}"
        return f"exit={proc.returncode}\n{out}"
    finally:
        if proc in CURRENT_PROC:
            CURRENT_PROC.remove(proc)


def kill_current_shell() -> None:
    for proc in list(CURRENT_PROC):
        proc.kill()
        if sys.platform == "win32" and proc.pid:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                text=True,
            )
