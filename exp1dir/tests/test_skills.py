from pathlib import Path
from backend.memory.store import MemoryStore, ensure_home
from backend.paths import HermesPaths
from backend.tools.skill_tool import load_skill, skill_index, skill_manage


def test_bundled_copied_and_index_has_no_body(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    idx = skill_index(p)
    names = {i["name"] for i in idx}
    assert "inspect-workspace" in names
    assert "take-notes" in names
    for item in idx:
        assert "body" not in item
        assert "description" in item


def test_load_skill_returns_body(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    body = load_skill(p, "inspect-workspace")
    assert "workspace" in body.lower()
    assert not body.startswith("ERROR:")


def test_skill_manage_create_update_delete(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    out = skill_manage(p, "create", "demo", "A demo skill", "# Demo\nDo X\n")
    assert "created" in out.lower()
    assert (p.skills / "demo" / "SKILL.md").exists()
    skill_manage(p, "update", "demo", "A demo skill", "# Demo\nDo Y\n")
    assert "Do Y" in (p.skills / "demo" / "SKILL.md").read_text(encoding="utf-8")
    skill_manage(p, "delete", "demo", "", "")
    assert not (p.skills / "demo" / "SKILL.md").exists()


def test_ensure_home_does_not_overwrite_agent_skill(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    dest = p.skills / "inspect-workspace" / "SKILL.md"
    dest.write_text("---\nname: inspect-workspace\ndescription: custom\n---\n# custom\n", encoding="utf-8")
    ensure_home(p)
    assert "custom" in dest.read_text(encoding="utf-8")
