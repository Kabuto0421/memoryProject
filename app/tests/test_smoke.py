"""Tests for the conversational memory MVP."""

from fastapi.testclient import TestClient

from app.api.main import app, healthcheck
from app.core.settings import DB_PATH
from app.memory.store import create_memory, init_db, list_memories


def test_healthcheck_returns_ok() -> None:
    """The health endpoint function should answer with a simple ok payload."""
    assert healthcheck() == {"status": "ok"}


def test_create_and_list_memory_with_temp_db(tmp_path) -> None:
    """The store should persist a memory and expose analyzed fields."""
    db_path = str(tmp_path / "memories.db")
    init_db(db_path)

    created = create_memory("本屋でAIに本を選んでほしいと感じた。", db_path=db_path)
    memories = list_memories(db_path=db_path)

    assert created["id"].startswith("mem_")
    assert memories[0]["raw_text"] == "本屋でAIに本を選んでほしいと感じた。"
    assert "desire" in memories[0]["memory_types"] or "decision_support" in memories[0]["memory_types"]
    assert "emotion" in memories[0]


def test_api_create_and_list_memory(monkeypatch, tmp_path) -> None:
    """The API should create and list memories using the configured store."""
    db_path = str(tmp_path / "api_memories.db")
    monkeypatch.setattr("app.memory.store.DB_PATH", tmp_path / "api_memories.db")
    monkeypatch.setattr("app.core.settings.DB_PATH", tmp_path / "api_memories.db")
    init_db(db_path)

    client = TestClient(app)
    create_response = client.post("/memories", json={"raw_text": "最近ちょっと不安だけど、AIに相談できると助かる。"})
    list_response = client.get("/memories")

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["count"] >= 1
