"""Tests for the conversational memory MVP."""

from fastapi.testclient import TestClient

from app.analysis.text_analyzer import analyze_text
from app.api.main import app, healthcheck
from app.memory.store import (
    create_memory,
    create_message,
    init_db,
    list_memories,
    list_messages,
    list_relevant_context,
    list_shared_contexts,
)


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
    assert memories[0]["speaker"] == "user"
    assert memories[0]["memory_scope"] == "user_memory"
    assert memories[0]["status"] == "asserted"
    assert memories[0]["turn_id"].startswith("turn_")


def test_short_ack_is_low_priority_but_still_saved(tmp_path) -> None:
    """Short acknowledgements should remain stored but at low priority."""
    db_path = str(tmp_path / "ack_memories.db")
    init_db(db_path)

    created = create_memory("ありがとう", db_path=db_path)

    assert created["memory_priority"] == "low"
    assert "is_short_ack" in created["reason_codes"]


def test_create_message_supports_assistant_metadata_and_filters(tmp_path) -> None:
    """Conversation turns should keep speaker metadata and list filters."""
    db_path = str(tmp_path / "messages.db")
    init_db(db_path)

    created = create_message(
        "この方針で進めるのがよい。",
        db_path=db_path,
        turn_id="turn_assistant_1",
        speaker="assistant",
    )
    filtered = list_messages(db_path=db_path, speaker="assistant", status="proposed")

    assert created["speaker"] == "assistant"
    assert created["memory_scope"] == "shared_context_candidate"
    assert created["status"] == "proposed"
    assert created["turn_id"] == "turn_assistant_1"
    assert "has_shared_context_signal" in created["reason_codes"]
    assert filtered[0]["id"] == created["id"]


def test_plain_assistant_explanation_stays_assistant_trace(tmp_path) -> None:
    """Assistant messages without proposal phrasing should remain plain traces."""
    db_path = str(tmp_path / "assistant_trace.db")
    init_db(db_path)

    created = create_message(
        "これは現在の保存構造の説明です。",
        db_path=db_path,
        turn_id="turn_assistant_trace_1",
        speaker="assistant",
    )

    assert created["memory_scope"] == "assistant_trace"
    assert created["status"] == "proposed"
    assert "has_shared_context_signal" not in created["reason_codes"]


def test_user_acceptance_promotes_referenced_proposal(tmp_path) -> None:
    """A user acknowledgement should promote a referenced assistant proposal."""
    db_path = str(tmp_path / "accepted_flow.db")
    init_db(db_path)

    proposal = create_message(
        "今後はこの方針で進めるのがよい。",
        db_path=db_path,
        turn_id="turn_proposal_1",
        speaker="assistant",
    )
    acceptance = create_message(
        "その方針で。",
        db_path=db_path,
        turn_id="turn_accept_1",
        reply_to_turn_id="turn_proposal_1",
        speaker="user",
    )
    refreshed_messages = list_messages(db_path=db_path, status="accepted")

    assert proposal["memory_scope"] == "shared_context_candidate"
    assert acceptance["memory_scope"] == "shared_context_candidate"
    assert acceptance["status"] == "accepted"
    assert "has_user_acceptance_signal" in acceptance["reason_codes"]
    assert any(message["turn_id"] == "turn_proposal_1" for message in refreshed_messages)
    promoted = next(message for message in refreshed_messages if message["turn_id"] == "turn_proposal_1")
    assert promoted["status"] == "accepted"
    assert "accepted_by_user_ack" in promoted["reason_codes"]


def test_shared_context_is_created_from_accepted_flow(tmp_path) -> None:
    """Accepted proposal flows should materialize into shared contexts."""
    db_path = str(tmp_path / "shared_contexts.db")
    init_db(db_path)

    create_message(
        "今後はこの方針で進めるのがよい。",
        db_path=db_path,
        turn_id="turn_ctx_proposal_1",
        speaker="assistant",
    )
    create_message(
        "それでお願い。",
        db_path=db_path,
        turn_id="turn_ctx_accept_1",
        reply_to_turn_id="turn_ctx_proposal_1",
        speaker="user",
    )
    contexts = list_shared_contexts(db_path=db_path)

    assert len(contexts) == 1
    assert contexts[0]["id"] == "ctx_turn_ctx_proposal_1"
    assert contexts[0]["status"] == "accepted"
    assert contexts[0]["summary"].startswith("今後はこの方針")
    assert contexts[0]["source_turn_ids"] == ["turn_ctx_proposal_1", "turn_ctx_accept_1"]
    assert "shared_context_candidate" in contexts[0]["tags"]


def test_relevant_context_prioritizes_shared_contexts(tmp_path) -> None:
    """Relevant context lookup should surface accepted shared context first."""
    db_path = str(tmp_path / "relevant_context.db")
    init_db(db_path)

    create_message(
        "保存方針としては全件保存で進めるのがよい。",
        db_path=db_path,
        turn_id="turn_rel_proposal_1",
        speaker="assistant",
    )
    create_message(
        "その方針で。",
        db_path=db_path,
        turn_id="turn_rel_accept_1",
        reply_to_turn_id="turn_rel_proposal_1",
        speaker="user",
    )
    create_message(
        "保存方針の説明をREADMEにも入れておきたい。",
        db_path=db_path,
        turn_id="turn_rel_user_1",
        speaker="user",
    )

    result = list_relevant_context("保存方針", db_path=db_path)

    assert result["shared_contexts"]
    assert result["shared_contexts"][0]["id"] == "ctx_turn_rel_proposal_1"
    assert result["memories"]
    assert any(memory["turn_id"] == "turn_rel_user_1" for memory in result["memories"])


def test_relevant_context_suppresses_sensitive_casual_matches(tmp_path) -> None:
    """Sensitive memories should not surface on weak casual matches."""
    db_path = str(tmp_path / "relevant_sensitive.db")
    init_db(db_path)

    create_memory("家族の病気のことで本当に不安だ。", db_path=db_path)
    create_memory("保存方針を整理したい。", db_path=db_path)

    result = list_relevant_context("保存", db_path=db_path)

    assert all(memory["safety"]["sensitivity"] == "normal" for memory in result["memories"])


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


def test_soft_negation_helper_phrase_is_not_treated_as_full_negation() -> None:
    """Purpose phrases like '忘れないように' should not inflate negation signals."""
    analysis = analyze_text("忘れないように明日、家族に連絡する。")

    assert "has_future_reference" in analysis.reason_codes
    assert "has_negation" not in analysis.reason_codes


def test_plain_choice_text_does_not_force_decision_support() -> None:
    """Simple selection phrasing should not always become decision support."""
    analysis = analyze_text("紙の本を選ぶ時間が結構好き。")

    assert "preference" in analysis.memory_types
    assert "decision_support" not in analysis.memory_types


def test_surface_reflection_phrase_is_detected() -> None:
    """Common reflective phrasing should be captured even without stronger keywords."""
    analysis = analyze_text("このやり方の方が自分に合っている気がする。")

    assert "reflection" in analysis.memory_types


def test_strong_relationship_memory_can_reach_critical() -> None:
    """A future-facing relationship worry should reach the critical bucket."""
    analysis = analyze_text("恋人との将来のことで不安が強くて、次回会う前に自分の気持ちをちゃんと決めたい。")

    assert analysis.save_strength >= 0.50
    assert analysis.memory_priority == "critical"
    assert "has_relationship" in analysis.reason_codes
    assert "has_worry" in analysis.reason_codes


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


def test_api_create_and_list_message(monkeypatch, tmp_path) -> None:
    """The message API should persist speaker-aware conversation turns."""
    db_path = str(tmp_path / "api_messages.db")
    monkeypatch.setattr("app.memory.store.DB_PATH", tmp_path / "api_messages.db")
    monkeypatch.setattr("app.core.settings.DB_PATH", tmp_path / "api_messages.db")
    init_db(db_path)

    client = TestClient(app)
    create_response = client.post(
        "/messages",
        json={
            "text": "今後は全件保存で進める提案です。",
            "speaker": "assistant",
            "turn_id": "turn_api_1",
        },
    )
    list_response = client.get("/messages", params={"speaker": "assistant"})

    assert create_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["count"] >= 1
    assert create_response.json()["message"]["speaker"] == "assistant"
    assert create_response.json()["message"]["memory_scope"] == "shared_context_candidate"
    assert create_response.json()["message"]["status"] == "proposed"
    assert "has_shared_context_signal" in create_response.json()["message"]["reason_codes"]


def test_api_message_filters(monkeypatch, tmp_path) -> None:
    """Message list filters should narrow the result set by speaker and status."""
    db_path = str(tmp_path / "api_message_filters.db")
    monkeypatch.setattr("app.memory.store.DB_PATH", tmp_path / "api_message_filters.db")
    monkeypatch.setattr("app.core.settings.DB_PATH", tmp_path / "api_message_filters.db")
    init_db(db_path)

    client = TestClient(app)
    client.post(
        "/messages",
        json={"text": "この方針で進めるのがよい。", "speaker": "assistant", "turn_id": "turn_filter_1"},
    )
    client.post(
        "/messages",
        json={"text": "その方針で。", "speaker": "user", "turn_id": "turn_filter_2", "status": "accepted"},
    )

    assistant_only = client.get("/messages", params={"speaker": "assistant"})
    accepted_only = client.get("/messages", params={"status": "accepted"})

    assert assistant_only.status_code == 200
    assert accepted_only.status_code == 200
    assert all(message["speaker"] == "assistant" for message in assistant_only.json()["messages"])
    assert all(message["status"] == "accepted" for message in accepted_only.json()["messages"])


def test_api_user_acceptance_promotes_assistant_candidate(monkeypatch, tmp_path) -> None:
    """The API should promote a referenced assistant proposal to accepted."""
    db_path = str(tmp_path / "api_acceptance.db")
    monkeypatch.setattr("app.memory.store.DB_PATH", tmp_path / "api_acceptance.db")
    monkeypatch.setattr("app.core.settings.DB_PATH", tmp_path / "api_acceptance.db")
    init_db(db_path)

    client = TestClient(app)
    proposal = client.post(
        "/messages",
        json={
            "text": "今後はこの方針で進めるのがよい。",
            "speaker": "assistant",
            "turn_id": "turn_api_proposal",
        },
    )
    acceptance = client.post(
        "/messages",
        json={
            "text": "それでお願い。",
            "speaker": "user",
            "turn_id": "turn_api_acceptance",
            "reply_to_turn_id": "turn_api_proposal",
        },
    )
    accepted_messages = client.get("/messages", params={"status": "accepted"})

    assert proposal.status_code == 200
    assert acceptance.status_code == 200
    assert acceptance.json()["message"]["status"] == "accepted"
    assert acceptance.json()["message"]["memory_scope"] == "shared_context_candidate"
    assert any(message["turn_id"] == "turn_api_proposal" for message in accepted_messages.json()["messages"])


def test_api_lists_shared_contexts(monkeypatch, tmp_path) -> None:
    """The shared context API should return contexts generated from accepted flows."""
    db_path = str(tmp_path / "api_shared_contexts.db")
    monkeypatch.setattr("app.memory.store.DB_PATH", tmp_path / "api_shared_contexts.db")
    monkeypatch.setattr("app.core.settings.DB_PATH", tmp_path / "api_shared_contexts.db")
    init_db(db_path)

    client = TestClient(app)
    client.post(
        "/messages",
        json={
            "text": "今後はこの方針で進めるのがよい。",
            "speaker": "assistant",
            "turn_id": "turn_api_ctx_proposal",
        },
    )
    client.post(
        "/messages",
        json={
            "text": "じゃあそれで。",
            "speaker": "user",
            "turn_id": "turn_api_ctx_accept",
            "reply_to_turn_id": "turn_api_ctx_proposal",
        },
    )
    shared_response = client.get("/context/shared")

    assert shared_response.status_code == 200
    assert shared_response.json()["count"] == 1
    assert shared_response.json()["shared_contexts"][0]["id"] == "ctx_turn_api_ctx_proposal"


def test_api_returns_relevant_context(monkeypatch, tmp_path) -> None:
    """The relevant context API should return shared contexts and matching memories."""
    db_path = str(tmp_path / "api_relevant_context.db")
    monkeypatch.setattr("app.memory.store.DB_PATH", tmp_path / "api_relevant_context.db")
    monkeypatch.setattr("app.core.settings.DB_PATH", tmp_path / "api_relevant_context.db")
    init_db(db_path)

    client = TestClient(app)
    client.post(
        "/messages",
        json={
            "text": "保存方針としては全件保存で進めるのがよい。",
            "speaker": "assistant",
            "turn_id": "turn_api_rel_proposal",
        },
    )
    client.post(
        "/messages",
        json={
            "text": "それでお願い。",
            "speaker": "user",
            "turn_id": "turn_api_rel_accept",
            "reply_to_turn_id": "turn_api_rel_proposal",
        },
    )
    client.post(
        "/messages",
        json={
            "text": "保存方針の説明を README にも入れておきたい。",
            "speaker": "user",
            "turn_id": "turn_api_rel_user",
        },
    )

    response = client.get("/context/relevant", params={"query": "保存方針"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["shared_context_count"] >= 1
    assert payload["memory_count"] >= 1
    assert payload["shared_contexts"][0]["id"] == "ctx_turn_api_rel_proposal"
    assert any(memory["turn_id"] == "turn_api_rel_user" for memory in payload["memories"])
