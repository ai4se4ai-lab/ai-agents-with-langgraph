from pathlib import Path
from backend.paths import HermesPaths


def test_hermes_paths_layout(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    assert p.home == tmp_path / ".hermes"
    assert p.workspace == tmp_path / ".hermes" / "workspace"
    assert p.memories == tmp_path / ".hermes" / "memories"
    assert p.skills == tmp_path / ".hermes" / "skills"
    assert p.runs == tmp_path / ".hermes" / "runs"
    assert p.config_file == tmp_path / ".hermes" / "config.json"
    assert p.sessions_db == tmp_path / ".hermes" / "sessions.sqlite"
    assert p.memory_md == tmp_path / ".hermes" / "memories" / "MEMORY.md"
    assert p.user_md == tmp_path / ".hermes" / "memories" / "USER.md"


def test_default_root_is_exp1dir():
    p = HermesPaths.default()
    assert p.root.name == "exp1dir"
    assert (p.root / "pyproject.toml").exists() or p.root.is_dir()
