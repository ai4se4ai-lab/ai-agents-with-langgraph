# exp1 Hermes-style LangGraph Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a usable Hermes-style agent in `exp1dir/` where the user types a task, LangGraph runs Reason ⇄ Act ⇄ Observe then Learn/Update Memory, and both a Textual TUI and a React UI stream the same run (Ollama via `.env`, `/model` to switch).

**Architecture:** One FastAPI gateway owns a LangGraph graph. TUI and React are WebSocket clients. Memory/skills live in `exp1dir/.hermes/`. File/shell tools are sandboxed to `.hermes/workspace/`. Interrupt is a `RunManager` that kills the in-flight subprocess and resumes `reason` with a user message (not LangGraph `interrupt()`, which cannot kill a shell).

**Tech Stack:** Python 3.11+, LangGraph, langchain-ollama, FastAPI, uvicorn, httpx, python-dotenv, Textual, pytest, pytest-asyncio, React + Vite.

**Spec:** `docs/superpowers/specs/2026-08-12-exp1-hermes-agent-design.md`

**Working directory for all commands:** `exp1dir/` unless noted.

---

## File structure (lock this)

```
exp1dir/
  pyproject.toml
  .gitignore
  .env.example
  README.md
  shared/loop-nodes.json
  backend/
    __init__.py
    paths.py              # HermesPaths
    settings.py           # load .env
    llm/ollama.py         # list/switch models + ChatOllama adapter
    memory/store.py       # MEMORY.md, USER.md, ensure_home, bundled skills
    memory/sessions.py    # sqlite
    tools/sandbox.py
    tools/files.py
    tools/shell.py
    tools/web.py
    tools/memory_tool.py
    tools/skill_tool.py
    tools/sessions_tool.py
    tools/registry.py
    agent/state.py
    agent/events.py
    agent/prompts.py
    agent/llm_port.py     # LLMResponse, ScriptedLLM, OllamaLLM
    agent/nodes.py
    agent/graph.py
    agent/run_manager.py
    api/app.py
    skills/bundled/inspect-workspace/SKILL.md
    skills/bundled/take-notes/SKILL.md
  tui/main.py
  tui/app.py
  tui/commands.py
  tui/client.py
  web/                    # Vite React app
  tests/
```

Do not add MCP, cron, subagents, vector DBs, or extra tools.

---

### Task 1: Scaffold + HermesPaths

**Files:**
- Create: `exp1dir/pyproject.toml`
- Create: `exp1dir/.gitignore`
- Create: `exp1dir/backend/__init__.py`
- Create: `exp1dir/backend/paths.py`
- Create: `exp1dir/tests/test_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_paths.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd exp1dir; python -m pytest tests/test_paths.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend'`

- [ ] **Step 3: Write minimal implementation**

`exp1dir/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "exp1-hermes"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "langgraph>=0.6",
  "langchain-core>=0.3",
  "langchain-ollama>=0.3",
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "httpx>=0.27",
  "python-dotenv>=1.0",
  "textual>=1.0",
  "html2text>=2024.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[project.scripts]
hermes = "tui.main:main"

[tool.setuptools.packages.find]
include = ["backend*", "tui*"]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
```

`exp1dir/.gitignore`:

```
.env
.hermes/
__pycache__/
*.pyc
.venv/
node_modules/
web/dist/
.pytest_cache/
```

`exp1dir/backend/__init__.py`: empty

`exp1dir/backend/paths.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `cd exp1dir; python -m pytest tests/test_paths.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/pyproject.toml exp1dir/.gitignore exp1dir/backend/__init__.py exp1dir/backend/paths.py exp1dir/tests/test_paths.py
git commit -m "feat(exp1): add HermesPaths scaffold"
```

---

### Task 2: Path sandbox

**Files:**
- Create: `exp1dir/backend/tools/__init__.py`
- Create: `exp1dir/backend/tools/sandbox.py`
- Create: `exp1dir/tests/test_sandbox.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_sandbox.py
from pathlib import Path
from backend.paths import HermesPaths
from backend.tools.sandbox import SandboxError, resolve_under


def test_resolve_under_allows_child(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    p.workspace.mkdir(parents=True)
    got = resolve_under(p.workspace, "notes/a.txt")
    assert got == (p.workspace / "notes" / "a.txt").resolve()


def test_resolve_under_rejects_escape(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    p.workspace.mkdir(parents=True)
    try:
        resolve_under(p.workspace, "../memories/MEMORY.md")
        assert False, "should have raised"
    except SandboxError as e:
        assert "outside" in str(e).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sandbox.py -v`

Expected: FAIL `ModuleNotFoundError: backend.tools.sandbox`

- [ ] **Step 3: Write minimal implementation**

`exp1dir/backend/tools/__init__.py`: empty

`exp1dir/backend/tools/sandbox.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sandbox.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/__init__.py exp1dir/backend/tools/sandbox.py exp1dir/tests/test_sandbox.py
git commit -m "feat(exp1): sandbox paths under a root"
```

---

### Task 3: File tools

**Files:**
- Create: `exp1dir/backend/tools/files.py`
- Create: `exp1dir/tests/test_files.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_files.py
from pathlib import Path
from backend.paths import HermesPaths
from backend.tools.files import list_dir, read_file, write_file


def _paths(tmp_path: Path) -> HermesPaths:
    p = HermesPaths(root=tmp_path)
    p.workspace.mkdir(parents=True)
    return p


def test_write_read_list(tmp_path: Path):
    p = _paths(tmp_path)
    assert "wrote" in write_file(p, "a.txt", "hello").lower()
    assert read_file(p, "a.txt") == "hello"
    listing = list_dir(p, ".")
    assert "a.txt" in listing


def test_file_escape_is_error_string(tmp_path: Path):
    p = _paths(tmp_path)
    out = read_file(p, "../memories/MEMORY.md")
    assert out.startswith("ERROR:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_files.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/tools/files.py
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_files.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/files.py exp1dir/tests/test_files.py
git commit -m "feat(exp1): workspace file tools"
```

---

### Task 4: Memory store + memory tool

**Files:**
- Create: `exp1dir/backend/memory/__init__.py`
- Create: `exp1dir/backend/memory/store.py`
- Create: `exp1dir/backend/tools/memory_tool.py`
- Create: `exp1dir/tests/test_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_memory.py
from pathlib import Path
from backend.memory.store import MemoryStore, ensure_home
from backend.paths import HermesPaths
from backend.tools.memory_tool import memory_tool


def test_ensure_home_creates_files(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    assert p.memory_md.exists()
    assert p.user_md.exists()
    assert p.workspace.is_dir()


def test_memory_add_replace_remove(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    store = MemoryStore(p)
    assert "added" in memory_tool(store, "add", "MEMORY", "project is exp1").lower()
    assert "exp1" in p.memory_md.read_text(encoding="utf-8")
    assert "replaced" in memory_tool(store, "replace", "MEMORY", "project is exp1dir", old_text="project is exp1").lower()
    assert "exp1dir" in p.memory_md.read_text(encoding="utf-8")
    assert "removed" in memory_tool(store, "remove", "MEMORY", old_text="project is exp1dir").lower()
    assert "exp1dir" not in p.memory_md.read_text(encoding="utf-8")


def test_snapshot_concatenates(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    p.memory_md.write_text("# Memory\nfact\n", encoding="utf-8")
    p.user_md.write_text("# User\npref\n", encoding="utf-8")
    snap = MemoryStore(p).snapshot()
    assert "fact" in snap and "pref" in snap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_memory.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/memory/__init__.py
```

```python
# exp1dir/backend/memory/store.py
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
```

```python
# exp1dir/backend/tools/memory_tool.py
from backend.memory.store import MemoryStore


def memory_tool(store: MemoryStore, action: str, target: str, text: str = "", old_text: str = "") -> str:
    action = action.lower()
    try:
        if action == "add":
            return store.add(target, text)
        if action == "replace":
            return store.replace(target, text, old_text)
        if action == "remove":
            return store.remove(target, old_text)
        return f"ERROR: unknown action {action}"
    except ValueError as e:
        return f"ERROR: {e}"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_memory.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/memory exp1dir/backend/tools/memory_tool.py exp1dir/tests/test_memory.py
git commit -m "feat(exp1): markdown memory store and tool"
```

---

### Task 5: Skills + skill tools

**Files:**
- Create: `exp1dir/backend/skills/bundled/inspect-workspace/SKILL.md`
- Create: `exp1dir/backend/skills/bundled/take-notes/SKILL.md`
- Create: `exp1dir/backend/tools/skill_tool.py`
- Create: `exp1dir/tests/test_skills.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_skills.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skills.py -v`

Expected: FAIL import or missing bundled skills

- [ ] **Step 3: Write minimal implementation**

`exp1dir/backend/skills/bundled/inspect-workspace/SKILL.md`:

```markdown
---
name: inspect-workspace
description: List and summarize files in the workspace
---
# Inspect workspace

Use `list_dir` then `read_file` on interesting files. Stay under the workspace sandbox. Summarize what you find for the user.
```

`exp1dir/backend/skills/bundled/take-notes/SKILL.md`:

```markdown
---
name: take-notes
description: Write durable facts into MEMORY.md with the memory tool
---
# Take notes

When you learn a durable fact about the user or project, call `memory` with action=add, target=MEMORY. Use target=USER for preferences. Do not dump the whole transcript into memory.
```

```python
# exp1dir/backend/tools/skill_tool.py
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_skills.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/skills exp1dir/backend/tools/skill_tool.py exp1dir/tests/test_skills.py
git commit -m "feat(exp1): bundled skills and skill tools"
```

---

### Task 6: Session search

**Files:**
- Create: `exp1dir/backend/memory/sessions.py`
- Create: `exp1dir/backend/tools/sessions_tool.py`
- Create: `exp1dir/tests/test_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_sessions.py
from pathlib import Path
from backend.memory.sessions import SessionStore
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.sessions_tool import search_sessions


def test_search_sessions(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    store = SessionStore(p)
    store.save("r1", "list workspace", "found notes.txt", "success")
    hits = search_sessions(store, "notes")
    assert "notes.txt" in hits
    assert "r1" in hits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sessions.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/memory/sessions.py
import sqlite3
from backend.paths import HermesPaths


class SessionStore:
    def __init__(self, paths: HermesPaths):
        self.paths = paths
        self.paths.home.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.paths.sessions_db)

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, task TEXT, summary TEXT, status TEXT)"
            )

    def save(self, run_id: str, task: str, summary: str, status: str) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO runs (id, task, summary, status) VALUES (?, ?, ?, ?)",
                (run_id, task, summary, status),
            )

    def search(self, query: str) -> list[tuple[str, str, str, str]]:
        q = f"%{query}%"
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, task, summary, status FROM runs WHERE task LIKE ? OR summary LIKE ?",
                (q, q),
            ).fetchall()
        return rows

    def recent(self, limit: int = 20) -> list[tuple[str, str, str, str]]:
        with self._connect() as con:
            return con.execute(
                "SELECT id, task, summary, status FROM runs ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
```

```python
# exp1dir/backend/tools/sessions_tool.py
from backend.memory.sessions import SessionStore


def search_sessions(store: SessionStore, query: str) -> str:
    rows = store.search(query)
    if not rows:
        return "(no matches)"
    return "\n".join(f"{rid}: {task} [{status}] {summary}" for rid, task, summary, status in rows)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_sessions.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/memory/sessions.py exp1dir/backend/tools/sessions_tool.py exp1dir/tests/test_sessions.py
git commit -m "feat(exp1): sqlite session search"
```

---

### Task 7: Shell + web_fetch

**Files:**
- Create: `exp1dir/backend/tools/shell.py`
- Create: `exp1dir/backend/tools/web.py`
- Create: `exp1dir/tests/test_shell_web.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_shell_web.py
from pathlib import Path
from backend.memory.store import ensure_home
from backend.paths import HermesPaths
from backend.tools.shell import run_shell
from backend.tools.web import web_fetch


def test_shell_echo(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    out = run_shell(p, "python -c \"print('hi')\"", timeout=10)
    assert "hi" in out
    assert "exit=" in out


def test_shell_timeout(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    out = run_shell(p, "python -c \"import time; time.sleep(5)\"", timeout=0.2)
    assert "timeout" in out.lower()


def test_web_fetch_mocked(monkeypatch, tmp_path: Path):
    class FakeResp:
        status_code = 200
        text = "<html><body><p>Hello</p></body></html>"
        headers = {"content-type": "text/html"}

    def fake_get(url, timeout, headers):
        return FakeResp()

    monkeypatch.setattr("backend.tools.web.httpx.get", fake_get)
    out = web_fetch("http://example.com")
    assert "Hello" in out


def test_web_fetch_caps_and_errors(monkeypatch):
    class FakeResp:
        status_code = 404
        text = "missing"
        headers = {"content-type": "text/plain"}

    monkeypatch.setattr("backend.tools.web.httpx.get", lambda *a, **k: FakeResp())
    out = web_fetch("http://example.com/nope")
    assert "404" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_shell_web.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/tools/shell.py
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
```

```python
# exp1dir/backend/tools/web.py
import html2text
import httpx

MAX = 50_000


def web_fetch(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=20.0, headers={"User-Agent": "exp1-hermes/0.1"}, follow_redirects=True)
    except httpx.HTTPError as e:
        return f"ERROR: {e}"
    body = resp.text or ""
    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" in ctype:
        body = html2text.html2text(body)
    if len(body) > MAX:
        body = body[:MAX] + "\n...[truncated]"
    if resp.status_code != 200:
        return f"ERROR: HTTP {resp.status_code}\n{body}"
    return body
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_shell_web.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/tools/shell.py exp1dir/backend/tools/web.py exp1dir/tests/test_shell_web.py
git commit -m "feat(exp1): sandboxed shell and web_fetch"
```

---

### Task 8: Ollama model list + switch

**Files:**
- Create: `exp1dir/backend/settings.py`
- Create: `exp1dir/backend/llm/__init__.py`
- Create: `exp1dir/backend/llm/ollama.py`
- Create: `exp1dir/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_models.py
import json
from pathlib import Path
from backend.llm.ollama import ModelError, list_models, resolve_active, set_active
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_resolve_order_config_then_env_then_first(tmp_path: Path, monkeypatch):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    tags = ["alpha", "beta"]
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert resolve_active(p, tags, env_model="") == "alpha"
    p.config_file.write_text(json.dumps({"model": "beta"}), encoding="utf-8")
    assert resolve_active(p, tags, env_model="alpha") == "beta"
    p.config_file.write_text(json.dumps({"model": "gone"}), encoding="utf-8")
    assert resolve_active(p, tags, env_model="alpha") == "alpha"


def test_set_active_rejects_unknown(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    try:
        set_active(p, "nope", ["alpha"])
        assert False
    except ModelError:
        pass
    set_active(p, "alpha", ["alpha"])
    assert json.loads(p.config_file.read_text(encoding="utf-8"))["model"] == "alpha"


def test_list_models_http(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "llama3.1:latest"}, {"name": "qwen2.5"}]}

    monkeypatch.setattr("backend.llm.ollama.httpx.get", lambda *a, **k: FakeResp())
    assert list_models("http://ollama:11434") == ["llama3.1:latest", "qwen2.5"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv
from backend.paths import HermesPaths


def load_settings(paths: HermesPaths | None = None) -> dict:
    paths = paths or HermesPaths.default()
    load_dotenv(paths.root / ".env")
    return {
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        "ollama_api_key": os.environ.get("OLLAMA_API_KEY", ""),
        "ollama_model": os.environ.get("OLLAMA_MODEL", ""),
        "gateway_host": os.environ.get("GATEWAY_HOST", "127.0.0.1"),
        "gateway_port": int(os.environ.get("GATEWAY_PORT", "8765")),
    }
```

```python
# exp1dir/backend/llm/__init__.py
```

```python
# exp1dir/backend/llm/ollama.py
import json
import httpx
from backend.paths import HermesPaths


class ModelError(ValueError):
    pass


def list_models(base_url: str, api_key: str = "") -> list[str]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", headers=headers, timeout=10.0)
    resp.raise_for_status()
    models = resp.json().get("models") or []
    return [m.get("name") or m.get("model") for m in models if m.get("name") or m.get("model")]


def resolve_active(paths: HermesPaths, tags: list[str], env_model: str) -> str:
    if not tags:
        raise ModelError("no models available at OLLAMA_BASE_URL")
    cfg_model = ""
    if paths.config_file.exists():
        try:
            cfg_model = json.loads(paths.config_file.read_text(encoding="utf-8")).get("model") or ""
        except json.JSONDecodeError:
            cfg_model = ""
    if cfg_model in tags:
        return cfg_model
    if env_model in tags:
        return env_model
    return tags[0]


def set_active(paths: HermesPaths, name: str, tags: list[str]) -> str:
    if name not in tags:
        raise ModelError(f"unknown model: {name}")
    paths.home.mkdir(parents=True, exist_ok=True)
    data = {}
    if paths.config_file.exists():
        try:
            data = json.loads(paths.config_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["model"] = name
    paths.config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return name
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/settings.py exp1dir/backend/llm exp1dir/tests/test_models.py
git commit -m "feat(exp1): Ollama model list and /model persistence"
```

---

### Task 9: Events + loop node map

**Files:**
- Create: `exp1dir/shared/loop-nodes.json`
- Create: `exp1dir/backend/agent/__init__.py`
- Create: `exp1dir/backend/agent/events.py`
- Create: `exp1dir/tests/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_events.py
import json
from pathlib import Path
from backend.agent.events import EventLog, load_loop_nodes, make_event
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_loop_nodes_cover_steps():
    data = load_loop_nodes()
    for step in ("reason", "act", "observe", "success", "learn", "memory_update", "error"):
        assert step in data["steps"]


def test_event_log_append_and_replay(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    log = EventLog(p, "run1")
    e = make_event("run1", "reason", cycle=1, text="thinking", model="m")
    log.append(e)
    replay = log.replay()
    assert replay[0]["step"] == "reason"
    assert replay[0]["text"] == "thinking"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_events.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`exp1dir/shared/loop-nodes.json`:

```json
{
  "nodes": ["task", "reason", "act", "observe", "success", "learn", "memory_update", "reuse"],
  "steps": {
    "reason": "reason",
    "act": "act",
    "observe": "observe",
    "success": "success",
    "learn": "learn",
    "memory_update": "memory_update",
    "error": "observe"
  }
}
```

```python
# exp1dir/backend/agent/__init__.py
```

```python
# exp1dir/backend/agent/events.py
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_events.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/shared/loop-nodes.json exp1dir/backend/agent exp1dir/tests/test_events.py
git commit -m "feat(exp1): run event log and loop node map"
```

---

### Task 10: LangGraph routing with ScriptedLLM

**Files:**
- Create: `exp1dir/backend/agent/state.py`
- Create: `exp1dir/backend/agent/llm_port.py`
- Create: `exp1dir/backend/agent/prompts.py`
- Create: `exp1dir/backend/tools/registry.py`
- Create: `exp1dir/backend/agent/nodes.py`
- Create: `exp1dir/backend/agent/graph.py`
- Create: `exp1dir/tests/test_graph_routing.py`

This task builds the graph so a scripted model that requests `list_dir` then answers routes `reason → act → observe → reason → reflect → update_memory`. Use a no-op reflect/update until Task 11, but the edges must already go there.

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_graph_routing.py
from pathlib import Path
from backend.agent.graph import build_graph, run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_tool_then_final_answer(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="I will list", tool_calls=[ToolCall(id="1", name="list_dir", args={"path": "."})]),
            LLMResponse(content="workspace is empty", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    events = []
    result = run_task(p, llm, "list the workspace", on_event=events.append)
    steps = [e["step"] for e in events]
    assert steps.count("reason") >= 2
    assert "act" in steps and "observe" in steps
    assert "success" in steps
    assert result["status"] == "success"
    assert "empty" in result["final_answer"].lower() or "workspace" in result["final_answer"].lower()


def test_cycle_cap(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    forever = LLMResponse(content="loop", tool_calls=[ToolCall(id="1", name="list_dir", args={"path": "."})])
    llm = ScriptedLLM([forever] * 20 + [LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[])])
    result = run_task(p, llm, "loop forever", max_cycles=3, on_event=lambda e: None)
    assert result["status"] == "capped"
    assert result["cycle"] >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_graph_routing.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
# exp1dir/backend/agent/llm_port.py
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class ScriptedLLM:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.i = 0

    def invoke(self, messages: list, tools: list) -> LLMResponse:
        if self.i >= len(self.responses):
            return LLMResponse(content="(script exhausted)", tool_calls=[])
        item = self.responses[self.i]
        self.i += 1
        return item
```

```python
# exp1dir/backend/agent/state.py
from typing import Any, Callable, TypedDict
from backend.agent.llm_port import ToolCall


class AgentState(TypedDict):
    task: str
    run_id: str
    messages: list
    memory_snapshot: str
    skill_index: list
    loaded_skills: list
    cycle: int
    max_cycles: int
    pending_tool_calls: list
    last_observation: str
    status: str
    final_answer: str
    reflection: str
    memory_writes: list
    active_model: str
```

```python
# exp1dir/backend/agent/prompts.py
SYSTEM = """You are a Hermes-style agent. The user gives a task. You decide which tools, memories, and skills to use.

Loop: Reason, then Act (tools), then Observe, then Reason again until the task is done.
After you finish, you will be asked what you learned.

Use web_fetch for HTTP, not curl/wget in the shell.
File and shell tools only work inside the workspace.
Memory snapshot below is frozen for this run. Skill index lists name+description; call load_skill to read a body.

## Memory snapshot
{memory_snapshot}

## Skills
{skill_index}
"""
```

```python
# exp1dir/backend/tools/registry.py
from backend.memory.sessions import SessionStore
from backend.memory.store import MemoryStore
from backend.paths import HermesPaths
from backend.tools.files import list_dir, read_file, write_file
from backend.tools.memory_tool import memory_tool
from backend.tools.sessions_tool import search_sessions
from backend.tools.shell import run_shell
from backend.tools.skill_tool import load_skill, skill_manage
from backend.tools.web import web_fetch


def build_tool_fns(paths: HermesPaths) -> dict:
    mem = MemoryStore(paths)
    sessions = SessionStore(paths)

    def _memory(action: str, target: str, text: str = "", old_text: str = "") -> str:
        return memory_tool(mem, action, target, text, old_text)

    def _skill_manage(action: str, name: str, description: str = "", body: str = "") -> str:
        return skill_manage(paths, action, name, description, body)

    def _load_skill(name: str) -> str:
        return load_skill(paths, name)

    def _search(query: str) -> str:
        return search_sessions(sessions, query)

    return {
        "read_file": lambda path: read_file(paths, path),
        "write_file": lambda path, content: write_file(paths, path, content),
        "list_dir": lambda path=".": list_dir(paths, path),
        "shell": lambda command: run_shell(paths, command),
        "web_fetch": lambda url: web_fetch(url),
        "memory": _memory,
        "skill_manage": _skill_manage,
        "load_skill": _load_skill,
        "search_sessions": _search,
    }
```

`exp1dir/backend/agent/nodes.py` — implement `load_context`, `reason`, `act`, `observe`, `route_after_reason`. For this task `reflect` returns empty writes and `update_memory` is a no-op that sets status if missing. Full reflect is Task 11; include stub functions with the real names so Task 11 only fills their bodies.

```python
# exp1dir/backend/agent/nodes.py
import json
import uuid
from backend.agent.events import make_event
from backend.agent.prompts import SYSTEM
from backend.memory.store import MemoryStore, ensure_home
from backend.tools.skill_tool import skill_index


def load_context(state, paths, llm, tools, emit):
    ensure_home(paths)
    store = MemoryStore(paths)
    snapshot = store.snapshot()
    index = skill_index(paths)
    run_id = state.get("run_id") or uuid.uuid4().hex
    sys_prompt = SYSTEM.format(memory_snapshot=snapshot, skill_index=json.dumps(index))
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": state["task"]}]
    return {
        "run_id": run_id,
        "messages": messages,
        "memory_snapshot": snapshot,
        "skill_index": index,
        "loaded_skills": [],
        "cycle": 0,
        "pending_tool_calls": [],
        "last_observation": "",
        "status": "running",
        "final_answer": "",
        "reflection": "",
        "memory_writes": [],
    }


def reason(state, paths, llm, tools, emit):
    if state.get("status") == "running" and state.get("cycle", 0) >= state.get("max_cycles", 15):
        emit(make_event(state["run_id"], "error", cycle=state["cycle"], text="step limit"))
        return {"status": "capped", "final_answer": state.get("final_answer") or "stopped: step limit"}
    last_err = None
    for _ in range(2):
        try:
            resp = llm.invoke(state["messages"], tools)
            last_err = None
            break
        except Exception as e:
            last_err = e
            emit(make_event(state["run_id"], "error", cycle=state["cycle"], text=str(e), model=state.get("active_model", "")))
    if last_err is not None:
        return {"status": "failed", "final_answer": f"LLM error: {last_err}"}
    pending = [tc.__dict__ if hasattr(tc, "__dict__") else tc for tc in (resp.tool_calls or [])]
    messages = list(state["messages"]) + [{"role": "assistant", "content": resp.content, "tool_calls": pending}]
    emit(make_event(state["run_id"], "reason", cycle=state["cycle"], text=resp.content, model=state.get("active_model", "")))
    if pending:
        return {"messages": messages, "pending_tool_calls": pending, "status": "running"}
    emit(make_event(state["run_id"], "success", cycle=state["cycle"], text=resp.content, model=state.get("active_model", "")))
    return {"messages": messages, "pending_tool_calls": [], "final_answer": resp.content, "status": "success"}


def act(state, paths, llm, tools, emit):
    observations = []
    for call in state.get("pending_tool_calls") or []:
        name = call["name"] if isinstance(call, dict) else call.name
        args = call["args"] if isinstance(call, dict) else call.args
        cid = call.get("id") if isinstance(call, dict) else call.id
        emit(make_event(state["run_id"], "act", cycle=state["cycle"], tool=name, input=json.dumps(args), model=state.get("active_model", "")))
        fn = tools.get(name)
        if fn is None:
            obs = f"ERROR: unknown tool {name}"
        else:
            try:
                obs = fn(**args)
            except TypeError:
                obs = fn(*args.values()) if args else fn()
            except Exception as e:
                obs = f"ERROR: {e}"
        observations.append({"tool_call_id": cid, "name": name, "content": str(obs)})
    return {"pending_observations": observations}


def observe(state, paths, llm, tools, emit):
    messages = list(state["messages"])
    chunks = []
    for obs in state.get("pending_observations") or []:
        messages.append({"role": "tool", "content": obs["content"], "tool_call_id": obs.get("tool_call_id", "")})
        chunks.append(obs["content"])
        emit(make_event(state["run_id"], "observe", cycle=state["cycle"], tool=obs.get("name", ""), observation=obs["content"], model=state.get("active_model", "")))
    return {
        "messages": messages,
        "last_observation": "\n".join(chunks),
        "pending_tool_calls": [],
        "pending_observations": [],
        "cycle": state.get("cycle", 0) + 1,
    }


def reflect(state, paths, llm, tools, emit):
    emit(make_event(state["run_id"], "learn", cycle=state["cycle"], text="(no learning yet)", model=state.get("active_model", "")))
    return {"reflection": "", "memory_writes": []}


def update_memory(state, paths, llm, tools, emit):
    emit(make_event(state["run_id"], "memory_update", cycle=state["cycle"], text="none", model=state.get("active_model", "")))
    return {}


def route_after_reason(state) -> str:
    if state.get("status") in ("success", "failed", "capped"):
        return "reflect"
    if state.get("pending_tool_calls"):
        return "act"
    return "reflect"
```

```python
# exp1dir/backend/agent/graph.py
from functools import partial
from langgraph.graph import END, START, StateGraph
from backend.agent.nodes import act, load_context, observe, reason, reflect, route_after_reason, update_memory
from backend.agent.state import AgentState
from backend.tools.registry import build_tool_fns


def build_graph(paths, llm, emit, tools=None):
    tools = tools or build_tool_fns(paths)

    def wrap(fn):
        return partial(fn, paths=paths, llm=llm, tools=tools, emit=emit)

    g = StateGraph(AgentState)
    g.add_node("load_context", wrap(load_context))
    g.add_node("reason", wrap(reason))
    g.add_node("act", wrap(act))
    g.add_node("observe", wrap(observe))
    g.add_node("reflect", wrap(reflect))
    g.add_node("update_memory", wrap(update_memory))
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "reason")
    g.add_conditional_edges("reason", route_after_reason, {"act": "act", "reflect": "reflect"})
    g.add_edge("act", "observe")
    g.add_edge("observe", "reason")
    g.add_edge("reflect", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile()


def run_task(paths, llm, task: str, max_cycles: int = 15, on_event=None, model: str = "scripted"):
    events = []

    def emit(event):
        events.append(event)
        if on_event:
            on_event(event)

    graph = build_graph(paths, llm, emit)
    result = graph.invoke(
        {
            "task": task,
            "run_id": "",
            "messages": [],
            "memory_snapshot": "",
            "skill_index": [],
            "loaded_skills": [],
            "cycle": 0,
            "max_cycles": max_cycles,
            "pending_tool_calls": [],
            "last_observation": "",
            "status": "running",
            "final_answer": "",
            "reflection": "",
            "memory_writes": [],
            "active_model": model,
        }
    )
    result["_events"] = events
    return result
```

Do not emit events from `load_context`. `reason` emits `success` when there are no tool calls. After the cap, `reason` sets `status=capped` without calling the LLM.

`test_tool_then_final_answer` expects `success` in steps. `reason` emits success when no tool calls. After first tool response, second scripted response has no tool_calls → success → reflect. Third scripted response is unused until Task 11. Good.

`test_cycle_cap`: after 3 observe increments, cycle>=3 on next reason → capped → reflect. ScriptedLLM still has forever responses; reflect stub does not call llm. Good.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_graph_routing.py -v`

Expected: PASS. If `load_context` emit pollutes steps, remove it as noted.

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/agent exp1dir/backend/tools/registry.py exp1dir/tests/test_graph_routing.py
git commit -m "feat(exp1): LangGraph reason-act-observe loop"
```

---

### Task 11: Reflect, update_memory, reuse

**Files:**
- Modify: `exp1dir/backend/agent/nodes.py` (`reflect`, `update_memory`)
- Create: `exp1dir/tests/test_reflect_reuse.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_reflect_reuse.py
from pathlib import Path
from backend.agent.graph import run_task
from backend.agent.llm_port import LLMResponse, ScriptedLLM
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_reflect_writes_memory(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="done", tool_calls=[]),
            LLMResponse(
                content='{"memory": [{"action": "add", "target": "MEMORY", "text": "project is exp1"}], "skills": []}',
                tool_calls=[],
            ),
        ]
    )
    result = run_task(p, llm, "remember this is exp1")
    assert "exp1" in p.memory_md.read_text(encoding="utf-8")
    assert result["status"] == "success"


def test_invalid_reflect_json_skips_write(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    before = p.memory_md.read_text(encoding="utf-8")
    llm = ScriptedLLM(
        [
            LLMResponse(content="answer", tool_calls=[]),
            LLMResponse(content="not json", tool_calls=[]),
        ]
    )
    result = run_task(p, llm, "say hi")
    assert result["final_answer"] == "answer"
    assert p.memory_md.read_text(encoding="utf-8") == before


def test_reuse_on_second_run(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm1 = ScriptedLLM(
        [
            LLMResponse(content="ok", tool_calls=[]),
            LLMResponse(
                content='{"memory": [{"action": "add", "target": "MEMORY", "text": "the secret code is 42"}], "skills": []}',
                tool_calls=[],
            ),
        ]
    )
    run_task(p, llm1, "remember the code")
    captured = {}

    class Capture(ScriptedLLM):
        def invoke(self, messages, tools):
            captured["sys"] = messages[0]["content"]
            return super().invoke(messages, tools)

    llm2 = Capture(
        [
            LLMResponse(content="the code is 42", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    result = run_task(p, llm2, "what is the secret code?")
    assert "42" in captured["sys"]
    assert "42" in result["final_answer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reflect_reuse.py -v`

Expected: FAIL (`exp1` not in MEMORY.md) because reflect is a stub

- [ ] **Step 3: Replace reflect and update_memory in `exp1dir/backend/agent/nodes.py`**

```python
REFLECT_PROMPT = (
    "The task is done (or stopped). What did I learn that would help a future task? "
    "Reply with JSON only: {\"memory\": [{\"action\": \"add|replace|remove\", \"target\": \"MEMORY|USER\", "
    "\"text\": \"...\", \"old_text\": \"\"}], \"skills\": [{\"action\": \"create|update\", \"name\": \"...\", "
    "\"description\": \"...\", \"body\": \"...\"}]}. If nothing durable, use empty arrays."
)


def reflect(state, paths, llm, tools, emit):
    messages = list(state["messages"]) + [{"role": "user", "content": REFLECT_PROMPT}]
    try:
        resp = llm.invoke(messages, tools=[])
        raw = resp.content
    except Exception as e:
        emit(make_event(state["run_id"], "learn", cycle=state["cycle"], text=f"ERROR: {e}"))
        return {"reflection": "", "memory_writes": []}
    writes = []
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        data = json.loads(raw[start : end + 1]) if start >= 0 else {}
        for w in data.get("memory") or []:
            writes.append({**w, "kind": "memory"})
        for s in data.get("skills") or []:
            writes.append({**s, "kind": "skill"})
    except Exception:
        writes = []
    emit(make_event(state["run_id"], "learn", cycle=state["cycle"], text=raw, model=state.get("active_model", "")))
    return {"reflection": raw, "memory_writes": writes}


def update_memory(state, paths, llm, tools, emit):
    from backend.memory.sessions import SessionStore
    from backend.memory.store import MemoryStore
    from backend.tools.skill_tool import skill_manage

    store = MemoryStore(paths)
    applied = []
    for w in state.get("memory_writes") or []:
        kind = w.get("kind") or ("skill" if "name" in w and "body" in w else "memory")
        if kind == "skill":
            applied.append(skill_manage(paths, w.get("action", "create"), w.get("name", ""), w.get("description", ""), w.get("body", "")))
        else:
            from backend.tools.memory_tool import memory_tool
            applied.append(
                memory_tool(store, w.get("action", "add"), w.get("target", "MEMORY"), w.get("text", ""), w.get("old_text", ""))
            )
    summary = "; ".join(applied) if applied else "none"
    emit(make_event(state["run_id"], "memory_update", cycle=state["cycle"], text=summary, model=state.get("active_model", "")))
    SessionStore(paths).save(state["run_id"], state.get("task", ""), state.get("final_answer", "")[:500], state.get("status", ""))
    return {}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_reflect_reuse.py tests/test_graph_routing.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/agent/nodes.py exp1dir/tests/test_reflect_reuse.py
git commit -m "feat(exp1): reflect and persist memory for reuse"
```

---

### Task 12: Interrupt

**Files:**
- Create: `exp1dir/backend/agent/run_manager.py`
- Create: `exp1dir/tests/test_interrupt.py`
- Modify: `exp1dir/backend/tools/shell.py` to accept an optional `cancel_event` and `proc_holder` list so the manager can kill the process.

Interrupt is owned by `RunManager`, not LangGraph `interrupt()`.

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_interrupt.py
import threading
import time
from pathlib import Path
from backend.agent.llm_port import LLMResponse, ScriptedLLM, ToolCall
from backend.agent.run_manager import RunManager
from backend.memory.store import ensure_home
from backend.paths import HermesPaths


def test_interrupt_then_redirect(tmp_path: Path):
    p = HermesPaths(root=tmp_path)
    ensure_home(p)
    llm = ScriptedLLM(
        [
            LLMResponse(content="sleeping", tool_calls=[ToolCall(id="1", name="shell", args={"command": "python -c \"import time; time.sleep(8)\""})]),
            LLMResponse(content="redirected ok", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    mgr = RunManager(p, llm)
    run_id = mgr.start("please sleep")
    time.sleep(0.4)
    mgr.interrupt(run_id, "stop")
    mgr.send_message(run_id, "forget the sleep, just say hi")
    result = mgr.join(run_id, timeout=30)
    assert "user interrupted" in (result.get("last_observation") or "").lower() or result["status"] in ("success", "interrupted")
    assert "redirected" in result.get("final_answer", "").lower() or "hi" in result.get("final_answer", "").lower() or result["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_interrupt.py -v`

Expected: FAIL import error

- [ ] **Step 3: Implementation**

Update `run_shell` in `exp1dir/backend/tools/shell.py` to use `Popen` and a module-level holder:

```python
# exp1dir/backend/tools/shell.py
import subprocess
import time
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
```

```python
# exp1dir/backend/agent/run_manager.py
import threading
import uuid
from backend.agent.events import EventLog, make_event
from backend.agent.graph import build_graph
from backend.tools.registry import build_tool_fns
from backend.tools.shell import kill_current_shell


class RunManager:
    def __init__(self, paths, llm):
        self.paths = paths
        self.llm = llm
        self.runs = {}
        self.listeners = []

    def subscribe(self, fn):
        self.listeners.append(fn)

    def _emit(self, run_id, event):
        EventLog(self.paths, run_id).append(event)
        rec = self.runs.get(run_id)
        if rec is not None:
            rec["events"].append(event)
        for fn in list(self.listeners):
            fn(event)

    def start(self, task: str, model: str = "scripted") -> str:
        run_id = uuid.uuid4().hex
        rec = {
            "id": run_id,
            "status": "running",
            "events": [],
            "result": None,
            "redirect": threading.Event(),
            "redirect_text": "",
            "thread": None,
        }
        self.runs[run_id] = rec

        def emit(event):
            event = dict(event)
            event["run_id"] = run_id
            self._emit(run_id, event)

        def worker():
            tools = build_tool_fns(self.paths)
            graph = build_graph(self.paths, self.llm, emit, tools)
            state = {
                "task": task,
                "run_id": run_id,
                "messages": [],
                "memory_snapshot": "",
                "skill_index": [],
                "loaded_skills": [],
                "cycle": 0,
                "max_cycles": 15,
                "pending_tool_calls": [],
                "last_observation": "",
                "status": "running",
                "final_answer": "",
                "reflection": "",
                "memory_writes": [],
                "active_model": model,
            }
            try:
                result = graph.invoke(state)
            except Exception:
                kill_current_shell()
                rec["result"] = {**state, "status": "interrupted", "last_observation": rec.get("last_obs", "user interrupted")}
                rec["status"] = "interrupted"
                rec["redirect"].wait(timeout=120)
                if not rec["redirect_text"]:
                    return
                state = rec.get("paused_state") or state
                state["status"] = "running"
                state["last_observation"] = f"user interrupted: {rec['redirect_text']}"
                state["messages"] = list(state.get("messages") or []) + [
                    {"role": "user", "content": rec["redirect_text"]}
                ]
                state["pending_tool_calls"] = []
                graph2 = build_graph(self.paths, self.llm, emit, tools)
                result = graph2.invoke(state)
            rec["result"] = result
            rec["status"] = result.get("status", "success")

        t = threading.Thread(target=worker, daemon=True)
        rec["thread"] = t
        t.start()
        return run_id

    def interrupt(self, run_id: str, note: str = "") -> None:
        rec = self.runs[run_id]
        rec["last_obs"] = f"user interrupted: {note}".strip()
        kill_current_shell()

    def send_message(self, run_id: str, text: str) -> None:
        rec = self.runs[run_id]
        rec["redirect_text"] = text
        rec["redirect"].set()

    def join(self, run_id: str, timeout: float = 60):
        rec = self.runs[run_id]
        rec["thread"].join(timeout=timeout)
        return rec["result"] or {"status": rec["status"]}
```

The test needs a reliable interrupt path. Simpler approach that still matches the spec: **do not cancel the graph via exception**. Instead, `act` checks a `cancel_flag` on the manager.

Replace `RunManager` with this tighter version and thread the cancel flag into `act` via a dict `control = {"cancel": False, "note": ""}` closed over by wrapped nodes.

Modify `act` in `nodes.py` to take `control=None`:

```python
def act(state, paths, llm, tools, emit, control=None):
    if control and control.get("cancel"):
        note = control.get("note") or ""
        obs = f"user interrupted: {note}".strip()
        emit(make_event(state["run_id"], "observe", cycle=state["cycle"], observation=obs, model=state.get("active_model", "")))
        return {
            "pending_observations": [{"tool_call_id": "", "name": "interrupt", "content": obs}],
            "status": "interrupted",
            "last_observation": obs,
        }
    # ... existing tool loop, and inside the loop if control and control.get("cancel"): kill_current_shell(); break
```

And `route_after_reason` stays. After observe, reason runs again. `send_message` appends a user message by setting `control["inbox"]` which `reason` prepends.

Even simpler for the test: `interrupt` kills the shell so `run_shell` returns quickly with interrupted output; then `send_message` is not required for the first assertion. But the spec requires redirect.

Implement `RunManager` as:

1. `start` runs `graph.invoke` on a thread.
2. `interrupt` sets `control["cancel"]=True` and `kill_current_shell()`.
3. `act` sees cancel, returns interrupted observation.
4. `observe` then `reason` — but reason would call LLM immediately. Spec says **wait** for the next user message.

So after interrupt, the graph must pause. Use a `threading.Event` inside a new node `wait_redirect` OR block inside `observe` when status interrupted.

Add node `wait_redirect` between observe and reason when status==interrupted:

```python
def wait_redirect(state, paths, llm, tools, emit, control=None):
    control = control or {}
    event = control.get("redirect_event")
    if event:
        event.wait(timeout=300)
    text = control.get("redirect_text") or ""
    messages = list(state["messages"]) + [{"role": "user", "content": text}]
    return {"messages": messages, "status": "running", "pending_tool_calls": []}


def route_after_observe(state) -> str:
    if state.get("status") == "interrupted":
        return "wait_redirect"
    return "reason"
```

Wire: `observe → route_after_observe → wait_redirect|reason`. `wait_redirect → reason`.

`build_graph(..., control=None)` passes control into wraps.

Rewrite `run_manager.py` accordingly (full file):

```python
# exp1dir/backend/agent/run_manager.py
import threading
import uuid
from functools import partial
from langgraph.graph import END, START, StateGraph
from backend.agent.events import EventLog
from backend.agent.nodes import act, load_context, observe, reason, reflect, route_after_reason, update_memory, wait_redirect
from backend.agent.state import AgentState
from backend.tools.registry import build_tool_fns
from backend.tools.shell import kill_current_shell


def route_after_observe(state) -> str:
    if state.get("status") == "interrupted":
        return "wait_redirect"
    return "reason"


def build_controlled_graph(paths, llm, emit, tools, control):
    def wrap(fn):
        return partial(fn, paths=paths, llm=llm, tools=tools, emit=emit, control=control)

    g = StateGraph(AgentState)
    g.add_node("load_context", wrap(load_context))
    g.add_node("reason", wrap(reason))
    g.add_node("act", wrap(act))
    g.add_node("observe", wrap(observe))
    g.add_node("wait_redirect", wrap(wait_redirect))
    g.add_node("reflect", wrap(reflect))
    g.add_node("update_memory", wrap(update_memory))
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "reason")
    g.add_conditional_edges("reason", route_after_reason, {"act": "act", "reflect": "reflect"})
    g.add_edge("act", "observe")
    g.add_conditional_edges("observe", route_after_observe, {"wait_redirect": "wait_redirect", "reason": "reason"})
    g.add_edge("wait_redirect", "reason")
    g.add_edge("reflect", "update_memory")
    g.add_edge("update_memory", END)
    return g.compile()


class RunManager:
    def __init__(self, paths, llm):
        self.paths = paths
        self.llm = llm
        self.runs = {}
        self.listeners = []

    def subscribe(self, fn):
        self.listeners.append(fn)

    def start(self, task: str, model: str = "scripted") -> str:
        run_id = uuid.uuid4().hex
        control = {"cancel": False, "note": "", "redirect_event": threading.Event(), "redirect_text": ""}
        rec = {"id": run_id, "control": control, "result": None, "events": [], "thread": None, "status": "running"}
        self.runs[run_id] = rec

        def emit(event):
            event = dict(event)
            event["run_id"] = run_id
            EventLog(self.paths, run_id).append(event)
            rec["events"].append(event)
            for fn in list(self.listeners):
                fn(event)

        def worker():
            tools = build_tool_fns(self.paths)
            graph = build_controlled_graph(self.paths, self.llm, emit, tools, control)
            rec["result"] = graph.invoke(
                {
                    "task": task,
                    "run_id": run_id,
                    "messages": [],
                    "memory_snapshot": "",
                    "skill_index": [],
                    "loaded_skills": [],
                    "cycle": 0,
                    "max_cycles": 15,
                    "pending_tool_calls": [],
                    "last_observation": "",
                    "status": "running",
                    "final_answer": "",
                    "reflection": "",
                    "memory_writes": [],
                    "active_model": model,
                }
            )
            rec["status"] = rec["result"].get("status", "success")

        t = threading.Thread(target=worker, daemon=True)
        rec["thread"] = t
        t.start()
        return run_id

    def interrupt(self, run_id: str, note: str = "") -> None:
        rec = self.runs[run_id]
        rec["control"]["cancel"] = True
        rec["control"]["note"] = note
        kill_current_shell()

    def send_message(self, run_id: str, text: str) -> None:
        rec = self.runs[run_id]
        rec["control"]["redirect_text"] = text
        rec["control"]["cancel"] = False
        rec["control"]["redirect_event"].set()

    def join(self, run_id: str, timeout: float = 60):
        self.runs[run_id]["thread"].join(timeout=timeout)
        return self.runs[run_id]["result"]
```

Update every node signature to accept `control=None` (unused except `act` and `wait_redirect`). Add `wait_redirect` to `nodes.py`. Update `build_graph` in `graph.py` to add `control=None` on wraps so existing tests still pass (no wait node needed if never interrupted). Keep `build_graph` as the simple graph for unit tests; `RunManager` uses `build_controlled_graph`.

`act` must check cancel **during** the shell. Killing Popen is enough: `run_shell` returns, then act checks `control["cancel"]` and overwrites observation to `user interrupted: {note}`.

```python
def act(state, paths, llm, tools, emit, control=None):
    observations = []
    for call in state.get("pending_tool_calls") or []:
        name = call["name"] if isinstance(call, dict) else call.name
        args = call["args"] if isinstance(call, dict) else call.args
        cid = (call.get("id") if isinstance(call, dict) else call.id) or ""
        emit(make_event(state["run_id"], "act", cycle=state["cycle"], tool=name, input=json.dumps(args), model=state.get("active_model", "")))
        fn = tools.get(name)
        try:
            obs = fn(**args) if fn else f"ERROR: unknown tool {name}"
        except Exception as e:
            obs = f"ERROR: {e}"
        if control and control.get("cancel"):
            obs = f"user interrupted: {control.get('note') or ''}".strip()
            observations.append({"tool_call_id": cid, "name": name, "content": obs})
            return {"pending_observations": observations, "status": "interrupted", "last_observation": obs}
        observations.append({"tool_call_id": cid, "name": name, "content": str(obs)})
    return {"pending_observations": observations}


def wait_redirect(state, paths, llm, tools, emit, control=None):
    control = control or {}
    ev = control.get("redirect_event")
    if ev is not None:
        ev.wait(timeout=300)
    text = (control.get("redirect_text") or "").strip()
    messages = list(state["messages"]) + [{"role": "user", "content": text or "(continue)"}]
    return {"messages": messages, "status": "running", "pending_tool_calls": []}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_interrupt.py tests/test_graph_routing.py tests/test_reflect_reuse.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/agent/run_manager.py exp1dir/backend/agent/nodes.py exp1dir/backend/agent/graph.py exp1dir/backend/tools/shell.py exp1dir/tests/test_interrupt.py
git commit -m "feat(exp1): interrupt and redirect a run"
```

---

### Task 13: FastAPI gateway

**Files:**
- Create: `exp1dir/backend/api/__init__.py`
- Create: `exp1dir/backend/api/app.py`
- Create: `exp1dir/tests/test_gateway.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_gateway.py
from pathlib import Path
from fastapi.testclient import TestClient
from backend.agent.llm_port import LLMResponse, ScriptedLLM
from backend.api.app import create_app
from backend.paths import HermesPaths


def test_health_and_models(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha", "beta"])
    app = create_app(HermesPaths(root=tmp_path), llm=ScriptedLLM([]), settings={"ollama_base_url": "http://x", "ollama_api_key": "", "ollama_model": "", "gateway_host": "127.0.0.1", "gateway_port": 8765})
    c = TestClient(app)
    h = c.get("/health").json()
    assert h["active_model"] in ("alpha", "beta")
    assert c.get("/models").json()["models"] == ["alpha", "beta"]
    bad = c.post("/models/active", json={"model": "nope"})
    assert bad.status_code == 400
    ok = c.post("/models/active", json={"model": "beta"})
    assert ok.json()["model"] == "beta"


def test_run_events_and_two_clients(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.api.app.list_models", lambda *a, **k: ["alpha"])
    llm = ScriptedLLM(
        [
            LLMResponse(content="hello", tool_calls=[]),
            LLMResponse(content='{"memory": [], "skills": []}', tool_calls=[]),
        ]
    )
    app = create_app(HermesPaths(root=tmp_path), llm=llm, settings={"ollama_base_url": "http://x", "ollama_api_key": "", "ollama_model": "alpha", "gateway_host": "127.0.0.1", "gateway_port": 8765})
    c = TestClient(app)
    run_id = c.post("/runs", json={"task": "say hello"}).json()["run_id"]
    with c.websocket_connect(f"/ws/runs/{run_id}") as ws1, c.websocket_connect(f"/ws/runs/{run_id}") as ws2:
        steps1, steps2 = [], []
        for _ in range(20):
            try:
                steps1.append(ws1.receive_json()["step"])
            except Exception:
                break
        for _ in range(20):
            try:
                steps2.append(ws2.receive_json()["step"])
            except Exception:
                break
    assert "success" in steps1
    assert "success" in steps2
```

Websocket receive may need a timeout loop. Prefer: after POST /runs, `join` internally; TestClient websocket gets replay from jsonl. Implement `/ws/runs/{id}` as: replay log, then subscribe live until `memory_update` then close optional.

If the two-client live test is flaky, assert both replays contain `success` after `mgr.join`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gateway.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write `create_app`**

```python
# exp1dir/backend/api/app.py
import asyncio
import json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.agent.events import EventLog
from backend.agent.run_manager import RunManager
from backend.llm.ollama import ModelError, list_models, resolve_active, set_active
from backend.memory.store import MemoryStore, ensure_home
from backend.tools.skill_tool import skill_index


class TaskIn(BaseModel):
    task: str


class ModelIn(BaseModel):
    model: str


class MessageIn(BaseModel):
    text: str


class InterruptIn(BaseModel):
    note: str = ""


def create_app(paths, llm, settings: dict):
    ensure_home(paths)
    mgr = RunManager(paths, llm)
    hub: list[WebSocket] = []
    run_sockets: dict[str, list[WebSocket]] = {}

    def broadcast(event: dict):
        dead = []
        targets = list(hub) + list(run_sockets.get(event.get("run_id"), []))
        for ws in targets:
            try:
                asyncio.get_event_loop().create_task(ws.send_json(event))
            except Exception:
                dead.append(ws)
        # TestClient is sync: also stash events; sockets read via replay

    mgr.subscribe(lambda e: EventLog(paths, e["run_id"]).append(e) if False else None)
    # EventLog already appended in RunManager._emit / start emit

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.mgr = mgr
    app.state.paths = paths
    app.state.settings = settings

    def tags():
        return list_models(settings["ollama_base_url"], settings.get("ollama_api_key", ""))

    def active():
        try:
            return resolve_active(paths, tags(), settings.get("ollama_model", ""))
        except ModelError as e:
            return ""

    @app.get("/health")
    def health():
        try:
            models = tags()
            err = ""
        except Exception as e:
            models, err = [], str(e)
        return {"ok": not err, "ollama": settings["ollama_base_url"], "active_model": active() if models else "", "error": err}

    @app.get("/models")
    def models():
        try:
            return {"models": tags(), "active": active()}
        except Exception as e:
            raise HTTPException(502, f"cannot reach Ollama at {settings['ollama_base_url']}: {e}")

    @app.post("/models/active")
    def set_model(body: ModelIn):
        try:
            name = set_active(paths, body.model, tags())
        except ModelError as e:
            raise HTTPException(400, str(e))
        return {"model": name}

    @app.post("/runs")
    def start_run(body: TaskIn):
        if not active():
            raise HTTPException(502, f"cannot reach Ollama at {settings['ollama_base_url']}")
        run_id = mgr.start(body.task, model=active() or "unknown")
        return {"run_id": run_id}

    @app.post("/runs/{run_id}/interrupt")
    def interrupt(run_id: str, body: InterruptIn):
        mgr.interrupt(run_id, body.note)
        return {"ok": True}

    @app.post("/runs/{run_id}/message")
    def message(run_id: str, body: MessageIn):
        mgr.send_message(run_id, body.text)
        return {"ok": True}

    @app.get("/memory")
    def memory():
        store = MemoryStore(paths)
        return {"snapshot": store.snapshot()}

    @app.get("/skills")
    def skills():
        return {"skills": skill_index(paths)}

    @app.get("/runs")
    def runs():
        from backend.memory.sessions import SessionStore
        rows = SessionStore(paths).recent()
        return {"runs": [{"id": r[0], "task": r[1], "summary": r[2], "status": r[3]} for r in rows]}

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: str):
        await ws.accept()
        for event in EventLog(paths, run_id).replay():
            await ws.send_json(event)
        q: asyncio.Queue = asyncio.Queue()

        def on_event(event):
            if event.get("run_id") == run_id:
                q.put_nowait(event)

        mgr.subscribe(on_event)
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                await ws.send_json(event)
                if event.get("step") == "memory_update":
                    break
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass

    @app.websocket("/ws/events")
    async def ws_all(ws: WebSocket):
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        mgr.subscribe(lambda e: q.put_nowait(e))
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=60.0)
                await ws.send_json(event)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass

    return app
```

Health check in tests uses ScriptedLLM and mocked `list_models`. `POST /runs` currently refuses if `active()` is empty — with mock tags `alpha`, resolve_active works.

For `test_run_events_and_two_clients`, TestClient websocket + thread timing: sleep 0.5 after POST then connect so replay contains events. Update the test:

```python
    import time
    run_id = c.post("/runs", json={"task": "say hello"}).json()["run_id"]
    app.state.mgr.join(run_id, timeout=15)
    with c.websocket_connect(f"/ws/runs/{run_id}") as ws1:
        steps1 = []
        while True:
            try:
                steps1.append(ws1.receive_json()["step"])
            except Exception:
                break
    with c.websocket_connect(f"/ws/runs/{run_id}") as ws2:
        steps2 = []
        while True:
            try:
                steps2.append(ws2.receive_json()["step"])
            except Exception:
                break
    assert "success" in steps1 and "success" in steps2
```

`create_app` for tests should **not** require live Ollama. Gate `POST /runs` on models only when llm is the real Ollama adapter. Add `require_ollama: bool = True` and set False in tests, OR if `llm` is ScriptedLLM skip the health gate.

```python
        run_id = mgr.start(body.task, model=active() or "scripted")
```

Remove the `if not active(): raise` when `settings.get("skip_ollama")`. Tests pass `skip_ollama: True`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_gateway.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/backend/api exp1dir/tests/test_gateway.py
git commit -m "feat(exp1): FastAPI gateway and run websockets"
```

---

### Task 14: TUI commands + app

**Files:**
- Create: `exp1dir/tui/__init__.py`
- Create: `exp1dir/tui/commands.py`
- Create: `exp1dir/tui/client.py`
- Create: `exp1dir/tui/app.py`
- Create: `exp1dir/tui/main.py`
- Create: `exp1dir/tests/test_tui_commands.py`

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_tui_commands.py
from tui.commands import COMMANDS, parse_command


def test_command_table():
    names = {c["name"] for c in COMMANDS}
    assert {"model", "memory", "skills", "interrupt", "history", "quit"} <= names


def test_parse_model():
    assert parse_command("/model") == ("model", [])
    assert parse_command("/model llama3.1") == ("model", ["llama3.1"])
    assert parse_command("not a command") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tui_commands.py -v`

Expected: FAIL import error

- [ ] **Step 3: Implementation**

```python
# exp1dir/tui/commands.py
COMMANDS = [
    {"name": "model", "help": "List or switch Ollama models"},
    {"name": "memory", "help": "Show frozen memory snapshot"},
    {"name": "skills", "help": "List skills"},
    {"name": "interrupt", "help": "Stop current act and wait to redirect"},
    {"name": "history", "help": "Past runs"},
    {"name": "quit", "help": "Exit"},
]


def parse_command(text: str):
    if not text.startswith("/"):
        return None
    parts = text[1:].strip().split()
    if not parts:
        return None
    return parts[0], parts[1:]
```

```python
# exp1dir/tui/client.py
import httpx


class GatewayClient:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self._http = httpx.Client(timeout=30.0)

    def health(self):
        return self._http.get(f"{self.base}/health").json()

    def models(self):
        return self._http.get(f"{self.base}/models").json()

    def set_model(self, name: str):
        r = self._http.post(f"{self.base}/models/active", json={"model": name})
        r.raise_for_status()
        return r.json()

    def start(self, task: str):
        return self._http.post(f"{self.base}/runs", json={"task": task}).json()["run_id"]

    def interrupt(self, run_id: str, note: str = ""):
        self._http.post(f"{self.base}/runs/{run_id}/interrupt", json={"note": note})

    def message(self, run_id: str, text: str):
        self._http.post(f"{self.base}/runs/{run_id}/message", json={"text": text})

    def memory(self):
        return self._http.get(f"{self.base}/memory").json()

    def skills(self):
        return self._http.get(f"{self.base}/skills").json()

    def history(self):
        return self._http.get(f"{self.base}/runs").json()
```

`exp1dir/tui/app.py` — Textual app:

- `Header`, `RichLog` transcript, `TextArea` input
- Bindings: `ctrl+enter` submit, `ctrl+c` interrupt
- On submit: if text starts with `/`, handle command; elif `awaiting_redirect`, `client.message`; else `client.start` and spawn a worker that reads websocket via `httpx`/`websockets` — use `httpx` stream is awkward; use `websocket-client` or stdlib. Add dependency `websockets`.
- Print labeled blocks from `step`

Add `websockets` to `pyproject.toml` dependencies.

```python
# exp1dir/tui/app.py
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Log, TextArea
from tui.client import GatewayClient
from tui.commands import parse_command
import asyncio
import json
import websockets


class HermesApp(App):
    CSS = "TextArea { height: 8; } Log { height: 1fr; }"
    BINDINGS = [Binding("ctrl+enter", "submit", "Send"), Binding("ctrl+c", "interrupt", "Interrupt")]

    def __init__(self, client: GatewayClient):
        super().__init__()
        self.client = client
        self.run_id = None
        self.awaiting_redirect = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Log(id="log")
        yield TextArea(id="in")
        yield Footer()

    def on_mount(self):
        h = self.client.health()
        self.query_one("#log", Log).write_line(f"Ollama {h.get('ollama')} model={h.get('active_model')} err={h.get('error')}")

    def action_interrupt(self):
        if self.run_id:
            self.client.interrupt(self.run_id, "")
            self.awaiting_redirect = True
            self.query_one("#log", Log).write_line("[interrupt] next send redirects this run")

    def action_submit(self):
        box = self.query_one("#in", TextArea)
        text = box.text.strip()
        box.text = ""
        if not text:
            return
        parsed = parse_command(text)
        log = self.query_one("#log", Log)
        if parsed:
            name, args = parsed
            if name == "quit":
                self.exit()
                return
            if name == "model" and not args:
                data = self.client.models()
                log.write_line("models: " + ", ".join(f"{'*' + m if m == data.get('active') else m}" for m in data.get("models", [])))
                return
            if name == "model" and args:
                try:
                    got = self.client.set_model(args[0])
                    log.write_line(f"active model: {got['model']}")
                except Exception as e:
                    log.write_line(f"model error: {e}")
                return
            if name == "memory":
                log.write_line(self.client.memory()["snapshot"])
                log.write_line("(disk writes apply on the next task)")
                return
            if name == "skills":
                log.write_line(json.dumps(self.client.skills(), indent=2))
                return
            if name == "history":
                log.write_line(json.dumps(self.client.history(), indent=2))
                return
            if name == "interrupt":
                self.action_interrupt()
                return
            log.write_line(f"unknown command /{name}")
            return
        if self.awaiting_redirect and self.run_id:
            self.client.message(self.run_id, text)
            self.awaiting_redirect = False
            return
        self.run_id = self.client.start(text)
        self.run_worker(self._stream(self.run_id), exclusive=False)

    async def _stream(self, run_id: str):
        log = self.query_one("#log", Log)
        url = self.client.base.replace("http", "ws") + f"/ws/runs/{run_id}"
        async with websockets.connect(url) as ws:
            async for raw in ws:
                e = json.loads(raw)
                step = e.get("step", "")
                log.write_line(f"[{step}] {e.get('text') or e.get('observation') or e.get('input') or ''}")
```

```python
# exp1dir/tui/main.py
import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path
from backend.paths import HermesPaths
from backend.settings import load_settings
from tui.app import HermesApp
from tui.client import GatewayClient


def _port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _is_gateway(host: str, port: int) -> bool:
    try:
        import httpx
        r = httpx.get(f"http://{host}:{port}/health", timeout=0.5)
        return r.status_code == 200
    except Exception:
        return False


def serve():
    from backend.api.app import create_app
    from backend.agent.llm_port import OllamaLLM
    import uvicorn
    paths = HermesPaths.default()
    settings = load_settings(paths)
    llm = OllamaLLM(settings)
    app = create_app(paths, llm, settings)
    uvicorn.run(app, host=settings["gateway_host"], port=settings["gateway_port"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", nargs="?", default="tui")
    args = parser.parse_args()
    if args.cmd == "serve":
        serve()
        return
    paths = HermesPaths.default()
    settings = load_settings(paths)
    host, port = settings["gateway_host"], settings["gateway_port"]
    if not _port_open(host, port):
        subprocess.Popen([sys.executable, "-m", "tui.main", "serve"], cwd=str(paths.root))
        for _ in range(50):
            if _is_gateway(host, port):
                break
            time.sleep(0.1)
    elif not _is_gateway(host, port):
        print(f"port {port} is occupied by a non-gateway process")
        sys.exit(1)
    HermesApp(GatewayClient(f"http://{host}:{port}")).run()


if __name__ == "__main__":
    main()
```

`OllamaLLM` is created in this task so `serve` works. Add to `backend/agent/llm_port.py`:

```python
class OllamaLLM:
    def __init__(self, settings: dict, model: str | None = None):
        from langchain_ollama import ChatOllama
        self.settings = settings
        self._model = model
        self._client = None

    def _chat(self):
        from langchain_ollama import ChatOllama
        from backend.llm.ollama import list_models, resolve_active
        from backend.paths import HermesPaths
        paths = HermesPaths.default()
        tags = list_models(self.settings["ollama_base_url"], self.settings.get("ollama_api_key") or "")
        name = self._model or resolve_active(paths, tags, self.settings.get("ollama_model") or "")
        return ChatOllama(model=name, base_url=self.settings["ollama_base_url"], temperature=0)

    def invoke(self, messages: list, tools: list) -> LLMResponse:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
        chat = self._chat()
        lc = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                lc.append(SystemMessage(content=m["content"]))
            elif role == "user":
                lc.append(HumanMessage(content=m["content"]))
            elif role == "tool":
                lc.append(ToolMessage(content=m["content"], tool_call_id=m.get("tool_call_id") or "t"))
            else:
                lc.append(AIMessage(content=m.get("content") or ""))
        # tools are callables; skip bind_tools in v1 if conversion is heavy — bind empty and rely on prompt
        msg = chat.invoke(lc)
        content = getattr(msg, "content", "") or ""
        tcs = []
        for tc in getattr(msg, "tool_calls", None) or []:
            tcs.append(ToolCall(id=tc.get("id") or "t", name=tc.get("name"), args=tc.get("args") or {}))
        return LLMResponse(content=content, tool_calls=tcs)
```

Tool calling: convert registry to langchain tools in a follow-up inside this same step. Add `backend/tools/lc.py`:

```python
from langchain_core.tools import tool
from backend.tools.registry import build_tool_fns


def langchain_tools(paths):
    fns = build_tool_fns(paths)

    @tool
    def read_file(path: str) -> str:
        """Read a file under the workspace."""
        return fns["read_file"](path)

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a file under the workspace."""
        return fns["write_file"](path, content)

    @tool
    def list_dir(path: str = ".") -> str:
        """List a directory under the workspace."""
        return fns["list_dir"](path)

    @tool
    def shell(command: str) -> str:
        """Run a shell command in the workspace. Do not use curl/wget; use web_fetch for HTTP."""
        return fns["shell"](command)

    @tool
    def web_fetch(url: str) -> str:
        """HTTP GET a URL and return text."""
        return fns["web_fetch"](url)

    @tool
    def memory(action: str, target: str, text: str = "", old_text: str = "") -> str:
        """add/replace/remove long-term memory. target is MEMORY or USER."""
        return fns["memory"](action, target, text, old_text)

    @tool
    def skill_manage(action: str, name: str, description: str = "", body: str = "") -> str:
        """create/update/delete a skill."""
        return fns["skill_manage"](action, name, description, body)

    @tool
    def load_skill(name: str) -> str:
        """Load a skill body into context."""
        return fns["load_skill"](name)

    @tool
    def search_sessions(query: str) -> str:
        """Search past runs."""
        return fns["search_sessions"](query)

    return [read_file, write_file, list_dir, shell, web_fetch, memory, skill_manage, load_skill, search_sessions]
```

Then `OllamaLLM.invoke` uses `chat.bind_tools(langchain_tools(HermesPaths.default())).invoke(lc)` when tools is non-empty. ScriptedLLM ignores this.

Also add `websockets` to pyproject.toml dependencies.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tui_commands.py tests/test_graph_routing.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/tui exp1dir/backend/agent/llm_port.py exp1dir/backend/tools/lc.py exp1dir/pyproject.toml exp1dir/tests/test_tui_commands.py
git commit -m "feat(exp1): Hermes-like Textual TUI and Ollama adapter"
```

---

### Task 15: React UI

**Files:**
- Create Vite React app under `exp1dir/web/`
- Create: `exp1dir/web/src/loopMap.ts`
- Create: `exp1dir/web/src/App.tsx`
- Create: `exp1dir/tests/test_graph_map.py` (reads shared/loop-nodes.json — already tested; add that React copies the same keys)

- [ ] **Step 1: Write the failing test**

```python
# exp1dir/tests/test_graph_map.py
from pathlib import Path
from backend.agent.events import load_loop_nodes


def test_react_loop_map_matches_shared():
    data = load_loop_nodes()
    ts = Path(__file__).resolve().parent.parent / "web" / "src" / "loopMap.ts"
    text = ts.read_text(encoding="utf-8")
    for node in data["nodes"]:
        assert node in text
    for step in data["steps"]:
        assert step in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_graph_map.py -v`

Expected: FAIL missing `web/src/loopMap.ts`

- [ ] **Step 3: Scaffold Vite app and UI**

From `exp1dir/web`:

```bash
npm create vite@latest . -- --template react-ts
npm install
```

If the directory must be created first, `npm create vite@latest web -- --template react-ts` from `exp1dir`.

`exp1dir/web/src/loopMap.ts`:

```ts
import loop from "../../shared/loop-nodes.json";

export const NODES = loop.nodes as string[];
export const STEPS = loop.steps as Record<string, string>;

export function nodeForStep(step: string): string {
  return STEPS[step] ?? step;
}
```

Vite JSON import: add `resolve.json` default true. If TS complains, copy the JSON into the ts file as a const matching `shared/loop-nodes.json` exactly (same keys). Prefer:

```ts
export const NODES = ["task", "reason", "act", "observe", "success", "learn", "memory_update", "reuse"] as const;
export const STEPS: Record<string, string> = {
  reason: "reason",
  act: "act",
  observe: "observe",
  success: "success",
  learn: "learn",
  memory_update: "memory_update",
  error: "observe",
};
export function nodeForStep(step: string): string {
  return STEPS[step] ?? step;
}
```

`exp1dir/web/src/App.tsx` — single file UI:

- Left: SVG/flex graph of NODES in the spec order. Highlight `active` from last event's mapped node. `error`/`failed observe` → red on observe. After `memory_update`, also light `reuse`.
- Center: transcript lines `[step] text`
- Right: model `<select>`, memory `<pre>`, skills list
- Top: task `<textarea>` + Send + Stop
- `const API = import.meta.env.VITE_GATEWAY || "http://127.0.0.1:8765"`
- On mount: GET /health, /models, /memory, /skills; open `ws://127.0.0.1:8765/ws/events`
- Send: POST /runs then also connect `/ws/runs/{id}` (hub already gets events)
- Stop: POST interrupt
- Model change: POST /models/active

`exp1dir/web/src/index.css` — dark background `#0f1419`, accent `#7ee0a8`, mono for transcript, no purple gradient.

`exp1dir/web/vite.config.ts` set `server.port = 5173`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_graph_map.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add exp1dir/web exp1dir/tests/test_graph_map.py
git commit -m "feat(exp1): React live loop graph"
```

---

### Task 16: .env.example, README, wire serve LLM into create_app

**Files:**
- Create: `exp1dir/.env.example`
- Create: `exp1dir/README.md`
- Modify: `exp1dir/tui/main.py` if needed so `hermes` and `hermes serve` work after `pip install -e .`

- [ ] **Step 1: Write `.env.example` and README** (no failing test; verify by reading files and running help)

`.env.example`:

```
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_API_KEY=
OLLAMA_MODEL=
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=8765
```

`README.md` must include:

1. `cd exp1dir && python -m venv .venv && .venv\Scripts\activate && pip install -e ".[dev]"`
2. Copy `.env.example` to `.env` and set `OLLAMA_BASE_URL`
3. `hermes serve` then in another terminal `hermes` (or just `hermes`, which auto-starts the gateway)
4. `/model` to list/switch
5. Type a task with Ctrl+Enter
6. React: `cd web && npm install && npm run dev` — open the Vite URL; set `VITE_GATEWAY` if the port is not 8765
7. Manual check from the spec: list workspace, remember a fact, second task reuses it, watch the graph

- [ ] **Step 2: Run full pytest**

Run: `python -m pytest -v`

Expected: all PASS

- [ ] **Step 3: `hermes --help` / `python -m tui.main serve` import check**

Run: `python -c "from tui.main import main; from backend.api.app import create_app"`

Expected: no import error

- [ ] **Step 4: Commit**

```bash
git add exp1dir/.env.example exp1dir/README.md
git commit -m "docs(exp1): env example and run instructions"
```

---

## Spec coverage (self-review)

| Spec item | Task |
| --- | --- |
| HermesPaths / `.hermes` layout | 1 |
| Sandbox | 2 |
| File tools | 3 |
| MEMORY.md / USER.md / memory tool | 4 |
| Bundled skills, index vs body, skill_manage, no overwrite | 5 |
| search_sessions | 6 |
| shell + web_fetch + 50KB cap | 7 |
| OLLAMA_BASE_URL, /model, config.json order | 8 |
| Event jsonl + loop map | 9 |
| LangGraph reason⇄act⇄observe, cycle cap, LLM retry | 10 |
| reflect JSON, update_memory, reuse next task | 11 |
| interrupt + redirect same run | 12 |
| Gateway REST + WS + two clients replay | 13 |
| TUI slash commands, Ctrl+Enter, auto-start gateway, `hermes serve` | 14 |
| React graph, transcript, model dropdown, stop | 15 |
| .env.example + README | 16 |
| Frozen snapshot per run | 10 `load_context` |
| FUTURE/REUSE display-only node | 15 lights `reuse` after `memory_update` |
| Path escape returns ERROR string | 3 |
| Invalid reflect JSON skips write | 11 |
| Shell not a network jail | 7 (cwd+timeout only) |

No MCP, cron, subagents, vector DB.
