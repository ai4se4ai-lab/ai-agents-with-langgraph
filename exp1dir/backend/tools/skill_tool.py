import re
from backend.paths import HermesPaths

FRONT = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def _parse(text: str) -> tuple[str, str, str]:
    m = FRONT.match(text)
    if not m:
        return "", "", text
    meta, body = m.group(1), m.group(2)
    name = description = ""
    for line in meta.splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
    return name, description, body


def skill_index(paths: HermesPaths) -> list[dict]:
    items = []
    if not paths.skills.exists():
        return items
    for skill_dir in sorted(paths.skills.iterdir()):
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        name, description, _ = _parse(md.read_text(encoding="utf-8"))
        items.append({"name": name or skill_dir.name, "description": description})
    return items


def load_skill(paths: HermesPaths, name: str) -> str:
    md = paths.skills / name / "SKILL.md"
    if not md.exists():
        return f"ERROR: unknown skill {name}"
    return md.read_text(encoding="utf-8")


def skill_manage(paths: HermesPaths, action: str, name: str, description: str, body: str) -> str:
    dest = paths.skills / name
    md = dest / "SKILL.md"
    action = action.lower()
    if action == "delete":
        if md.exists():
            md.unlink()
            try:
                dest.rmdir()
            except OSError:
                pass
            return f"deleted skill {name}"
        return f"ERROR: unknown skill {name}"
    if action in ("create", "update"):
        dest.mkdir(parents=True, exist_ok=True)
        md.write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n{body.rstrip()}\n",
            encoding="utf-8",
        )
        return f"{'created' if action == 'create' else 'updated'} skill {name}"
    return f"ERROR: unknown action {action}"
