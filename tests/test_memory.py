from dev_time_agent.memory import (
    InMemorySessionMemoryStore,
    SQLiteSessionMemoryStore,
    build_session_memory_store_from_env,
)


def test_build_session_memory_store_uses_in_memory_by_default() -> None:
    store = build_session_memory_store_from_env({})

    assert isinstance(store, InMemorySessionMemoryStore)


def test_build_session_memory_store_uses_sqlite_path_from_environment(tmp_path) -> None:
    memory_path = tmp_path / "session-memory.sqlite3"

    store = build_session_memory_store_from_env(
        {"DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH": str(memory_path)}
    )

    assert isinstance(store, SQLiteSessionMemoryStore)
    store.put("session_1", {"last_risk_reason": "go test failed"})
    reloaded_store = build_session_memory_store_from_env(
        {"DEV_TIME_AGENT_SESSION_MEMORY_DB_PATH": str(memory_path)}
    )
    assert reloaded_store.get("session_1") == {
        "last_risk_reason": "go test failed"
    }
