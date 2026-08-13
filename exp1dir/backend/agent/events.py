import json
from pathlib import Path
from typing import Any
from backend.paths import HermesPaths

LOOP_NODES_PATH = Path(__file__).resolve().parent.parent.parent / "shared" / "loop-nodes.json"


def load_loop_nodes() -> dict:
    return json.loads(LOOP_NODES_PATH.read_text(encoding="utf-8"))


def make_event(
    run_id: str,
    step: str,
    cycle: int = 0,
    tool: str = "",
    input: str = "",
    observation: str = "",
    text: str = "",
    model: str = "",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "step": step,
        "cycle": cycle,
        "tool": tool,
        "input": input,
        "observation": observation,
        "text": text,
        "model": model,
    }


class EventLog:
    def __init__(self, paths: HermesPaths, run_id: str):
        self.path = paths.run_log(run_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def replay(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
