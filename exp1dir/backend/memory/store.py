from pathlib import Path
from backend.paths import HermesPaths

BUNDLED = Path(__file__).resolve().parent.parent / "skills" / "bundled"


def ensure_home(paths: HermesPaths) -> None:
    for d in (paths.home, paths.workspace, paths.memories, paths.skills, paths.runs):
        d.mkdir(parents=True, exist_ok=True)
    if not paths.memory_md.exists():
        paths.memory_md.write_text("# MEMORY\n\n", encoding="utf-8")
    if not paths.user_md.exists():
        paths.user_md.write_text("# USER\n\n", encoding="utf-8")
    if BUNDLED.exists():
        for skill_dir in BUNDLED.iterdir():
            dest = paths.skills / skill_dir.name
            src = skill_dir / "SKILL.md"
            if skill_dir.is_dir() and src.exists() and not (dest / "SKILL.md").exists():
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


class MemoryStore:
    def __init__(self, paths: HermesPaths):
        self.paths = paths
        ensure_home(paths)

    def _file(self, target: str) -> Path:
        key = target.upper()
        if key == "MEMORY":
            return self.paths.memory_md
        if key == "USER":
            return self.paths.user_md
        raise ValueError(f"unknown memory target: {target}")

    def snapshot(self) -> str:
        mem = self.paths.memory_md.read_text(encoding="utf-8")
        user = self.paths.user_md.read_text(encoding="utf-8")
        return f"## MEMORY.md\n{mem}\n## USER.md\n{user}"

    def add(self, target: str, text: str) -> str:
        path = self._file(target)
        current = path.read_text(encoding="utf-8")
        path.write_text(current.rstrip() + "\n- " + text.strip() + "\n", encoding="utf-8")
        return f"added to {target}"

    def replace(self, target: str, new_text: str, old_text: str) -> str:
        path = self._file(target)
        current = path.read_text(encoding="utf-8")
        if old_text not in current:
            return f"ERROR: old_text not found in {target}"
        path.write_text(current.replace(old_text, new_text, 1), encoding="utf-8")
        return f"replaced in {target}"

    def remove(self, target: str, old_text: str) -> str:
        path = self._file(target)
        current = path.read_text(encoding="utf-8")
        if old_text not in current:
            return f"ERROR: old_text not found in {target}"
        path.write_text(current.replace(old_text, "", 1), encoding="utf-8")
        return f"removed from {target}"
