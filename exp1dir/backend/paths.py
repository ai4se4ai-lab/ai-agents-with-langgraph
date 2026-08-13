from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HermesPaths:
    root: Path

    @classmethod
    def default(cls) -> "HermesPaths":
        return cls(root=Path(__file__).resolve().parent.parent)

    @property
    def home(self) -> Path:
        return self.root / ".hermes"

    @property
    def workspace(self) -> Path:
        return self.home / "workspace"

    @property
    def memories(self) -> Path:
        return self.home / "memories"

    @property
    def skills(self) -> Path:
        return self.home / "skills"

    @property
    def runs(self) -> Path:
        return self.home / "runs"

    @property
    def config_file(self) -> Path:
        return self.home / "config.json"

    @property
    def sessions_db(self) -> Path:
        return self.home / "sessions.sqlite"

    @property
    def memory_md(self) -> Path:
        return self.memories / "MEMORY.md"

    @property
    def user_md(self) -> Path:
        return self.memories / "USER.md"

    def run_log(self, run_id: str) -> Path:
        return self.runs / f"{run_id}.jsonl"
