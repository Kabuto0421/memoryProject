"""Tests for the conversational memory MVP."""

from fastapi.testclient import TestClient

from app.analysis.text_analyzer import analyze_text
from app.api.main import app, healthcheck
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
    assert "save_strength" in memories[0]
    assert memories[0]["memory_priority"] in {"low", "medium", "high", "critical"}
    assert isinstance(memories[0]["reason_codes"], list)


def test_short_ack_is_low_priority_but_still_saved(tmp_path) -> None:
    """Short acknowledgements should remain stored but at low priority."""
    db_path = str(tmp_path / "ack_memories.db")
    init_db(db_path)

    created = create_memory("ありがとう", db_path=db_path)

    assert created["memory_priority"] == "low"
    assert "is_short_ack" in created["reason_codes"]


def test_ginza_extracts_lemma_based_reflection_and_keywords() -> None:
    """Inflected verbs should still contribute to memory typing and keywords."""
    analysis = analyze_text("AIに相談できると助かると感じた。")

    assert "reflection" in analysis.memory_types
    assert "感ずる" in analysis.keywords


def test_negated_worry_signal_is_softened() -> None:
    """Negated worry expressions should not be treated as strong worry memories."""
    analysis = analyze_text("不安はないので大丈夫。")

    assert analysis.emotion["primary"] == "neutral"
    assert "worry" not in analysis.memory_types
    assert "has_negation" in analysis.reason_codes
    assert "has_emotion_signal" not in analysis.reason_codes


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
    assert "save_strength" in create_response.json()
    assert "reason_codes" in create_response.json()
    assert "entities" in create_response.json()["memory"]
