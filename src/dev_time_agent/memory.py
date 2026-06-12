import json
import os
import sqlite3
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol


class SessionMemoryStore(Protocol):
    def get(self, session_id: str) -> dict[str, Any]:
        ...

    def put(self, session_id: str, memory: dict[str, Any]) -> None:
        ...

    def clear(self) -> None:
        ...


class InMemorySessionMemoryStore:
    def __init__(self) -> None:
        self._memory: dict[str, dict[str, Any]] = {}

    def get(self, session_id: str) -> dict[str, Any]:
        return dict(self._memory.get(session_id, {}))

    def put(self, session_id: str, memory: dict[str, Any]) -> None:
        self._memory[session_id] = dict(memory)

    def clear(self) -> None:
        self._memory.clear()


class SQLiteSessionMemoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT memory_json FROM session_memory WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            return {}
        loaded = json.loads(row[0])
        if not isinstance(loaded, dict):
            return {}
        return loaded

    def put(self, session_id: str, memory: dict[str, Any]) -> None:
        memory_json = json.dumps(memory, ensure_ascii=False, sort_keys=True)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    INSERT INTO session_memory (session_id, memory_json, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id)
                    DO UPDATE SET
                        memory_json = excluded.memory_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (session_id, memory_json),
                )
                connection.commit()
            finally:
                connection.close()

    def clear(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("DELETE FROM session_memory")
                connection.commit()
            finally:
                connection.close()

    def _initialize(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_memory (
                        session_id TEXT PRIMARY KEY,
                        memory_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)


def build_session_memory_store_from_env(
    environment: Mapping[str, str] | None = None,
) -> SessionMemoryStore:
    loaded_environment = environment or os.environ
    sqlite_path = loaded_environment.get("DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH", "")
    if sqlite_path.strip():
        return SQLiteSessionMemoryStore(sqlite_path)
    return InMemorySessionMemoryStore()
