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
