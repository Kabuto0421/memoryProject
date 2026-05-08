"""SQLite-backed storage for conversational memories."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.analysis.text_analyzer import analyze_text
from app.core.settings import DB_PATH, ensure_data_dir

ASSISTANT_SHARED_CONTEXT_TERMS = (
    "方針",
    "で進める",
    "を使う",
    "にする",
    "がよい",
    "がいい",
)
USER_ACCEPTANCE_TERMS = {
    "それで",
    "それでお願い",
    "それでお願いします",
    "ok",
    "その方針で",
    "じゃあそれで",
}
PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO string."""
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection."""
    target = db_path or str(DB_PATH)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None) -> None:
    """Create the memories table if it does not exist."""
    ensure_data_dir()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                turn_id TEXT NOT NULL,
                reply_to_turn_id TEXT,
                speaker TEXT NOT NULL DEFAULT 'user',
                source TEXT NOT NULL DEFAULT 'chat',
                memory_scope TEXT NOT NULL DEFAULT 'user_memory',
                status TEXT NOT NULL DEFAULT 'asserted',
                raw_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                memory_types_json TEXT NOT NULL,
                topics_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                entities_json TEXT NOT NULL DEFAULT '[]',
                facets_json TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                emotion_json TEXT NOT NULL,
                recall_policy_json TEXT NOT NULL,
                safety_json TEXT NOT NULL,
                save_strength REAL NOT NULL DEFAULT 0,
                memory_priority TEXT NOT NULL DEFAULT 'low',
                reason_codes_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shared_contexts (
                id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                detail TEXT NOT NULL,
                status TEXT NOT NULL,
                source_turn_ids_json TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                importance REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        if "save_strength" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN save_strength REAL NOT NULL DEFAULT 0")
        if "memory_priority" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN memory_priority TEXT NOT NULL DEFAULT 'low'")
        if "reason_codes_json" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN reason_codes_json TEXT NOT NULL DEFAULT '[]'")
        if "entities_json" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN entities_json TEXT NOT NULL DEFAULT '[]'")
        if "turn_id" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN turn_id TEXT NOT NULL DEFAULT ''")
            conn.execute("UPDATE memories SET turn_id = id WHERE turn_id = ''")
        if "reply_to_turn_id" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN reply_to_turn_id TEXT")
        if "speaker" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN speaker TEXT NOT NULL DEFAULT 'user'")
        if "source" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'chat'")
        if "memory_scope" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN memory_scope TEXT NOT NULL DEFAULT 'user_memory'")
        if "status" not in existing_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'asserted'")


def create_memory(
    raw_text: str,
    db_path: str | None = None,
    *,
    turn_id: str | None = None,
    reply_to_turn_id: str | None = None,
    speaker: str = "user",
) -> dict[str, Any]:
    """Analyze and persist a conversational memory."""
    text = raw_text.strip()
    if not text:
        raise ValueError("raw_text must not be empty.")

    init_db(db_path)
    analysis = analyze_text(text)
    resolved_scope = _default_memory_scope(speaker)
    resolved_status = _default_status(speaker)
    reason_codes = list(analysis.reason_codes)
    if speaker == "assistant" and _has_shared_context_signal(text):
        resolved_scope = "shared_context_candidate"
        reason_codes = _append_reason_code(reason_codes, "has_shared_context_signal")

    memory = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "turn_id": turn_id or f"turn_{uuid.uuid4().hex[:12]}",
        "reply_to_turn_id": reply_to_turn_id,
        "speaker": speaker,
        "source": "chat",
        "memory_scope": resolved_scope,
        "status": resolved_status,
        "raw_text": text,
        "summary": analysis.summary,
        "memory_types": analysis.memory_types,
        "topics": analysis.topics,
        "keywords": analysis.keywords,
        "entities": analysis.entities,
        "facets": analysis.facets,
        "scores": analysis.scores,
        "emotion": analysis.emotion,
        "recall_policy": analysis.recall_policy,
        "safety": analysis.safety,
        "save_strength": analysis.save_strength,
        "memory_priority": analysis.memory_priority,
        "reason_codes": reason_codes,
        "created_at": utc_now_iso(),
        "updated_at": None,
    }
    with get_connection(db_path) as conn:
        if speaker == "user" and _is_user_acceptance_text(text):
            memory["reason_codes"] = _append_reason_code(memory["reason_codes"], "has_user_acceptance_signal")
            if reply_to_turn_id:
                referenced = _find_message_by_turn_id(conn, reply_to_turn_id)
                if _can_promote_to_accepted(referenced):
                    memory["memory_scope"] = "shared_context_candidate"
                    memory["status"] = "accepted"
                    promoted = _mark_message_accepted(conn, referenced["turn_id"])
                    _ensure_shared_context_from_messages(conn, proposal=promoted, acceptance=memory)
        conn.execute(
            """
            INSERT INTO memories (
                id, turn_id, reply_to_turn_id, speaker, source, memory_scope, status,
                raw_text, summary, memory_types_json, topics_json, keywords_json,
                entities_json, facets_json, scores_json, emotion_json, recall_policy_json, safety_json,
                save_strength, memory_priority, reason_codes_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory["id"],
                memory["turn_id"],
                memory["reply_to_turn_id"],
                memory["speaker"],
                memory["source"],
                memory["memory_scope"],
                memory["status"],
                memory["raw_text"],
                memory["summary"],
                _dump_json(memory["memory_types"]),
                _dump_json(memory["topics"]),
                _dump_json(memory["keywords"]),
                _dump_json(memory["entities"]),
                _dump_json(memory["facets"]),
                _dump_json(memory["scores"]),
                _dump_json(memory["emotion"]),
                _dump_json(memory["recall_policy"]),
                _dump_json(memory["safety"]),
                memory["save_strength"],
                memory["memory_priority"],
                _dump_json(memory["reason_codes"]),
                memory["created_at"],
                memory["updated_at"],
            ),
        )
    return memory


def list_memories(
    limit: int = 50,
    db_path: str | None = None,
    *,
    speaker: str | None = None,
    memory_scope: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent memories in reverse chronological order."""
    init_db(db_path)
    query = """
        SELECT *
        FROM memories
    """
    clauses: list[str] = []
    params: list[Any] = []
    if speaker:
        clauses.append("speaker = ?")
        params.append(speaker)
    if memory_scope:
        clauses.append("memory_scope = ?")
        params.append(memory_scope)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += """
        ORDER BY created_at DESC
        LIMIT ?
    """
    params.append(limit)
    with get_connection(db_path) as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [_row_to_memory(row) for row in rows]


def create_message(
    text: str,
    *,
    turn_id: str | None = None,
    reply_to_turn_id: str | None = None,
    speaker: str = "user",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Create a conversation turn using the extended message metadata."""
    return create_memory(
        text,
        db_path=db_path,
        turn_id=turn_id,
        reply_to_turn_id=reply_to_turn_id,
        speaker=speaker,
    )


def list_messages(
    limit: int = 50,
    *,
    speaker: str | None = None,
    memory_scope: str | None = None,
    status: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """List stored conversation turns with optional metadata filters."""
    return list_memories(
        limit=limit,
        db_path=db_path,
        speaker=speaker,
        memory_scope=memory_scope,
        status=status,
    )


def list_shared_contexts(limit: int = 50, db_path: str | None = None) -> list[dict[str, Any]]:
    """List stored shared contexts in reverse chronological order."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM shared_contexts
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_shared_context(row) for row in rows]


def list_relevant_context(
    query: str,
    *,
    limit: int = 8,
    speaker: str | None = None,
    memory_priority: str | None = None,
    memory_scope: str | None = None,
    db_path: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return a compact relevant context bundle for the given query."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty.")

    shared_contexts = _find_relevant_shared_contexts(normalized_query, limit=limit, db_path=db_path)
    memories = _find_relevant_memories(
        normalized_query,
        limit=limit,
        speaker=speaker,
        memory_priority=memory_priority,
        memory_scope=memory_scope,
        db_path=db_path,
    )
    return {
        "shared_contexts": shared_contexts[:limit],
        "memories": memories[:limit],
    }


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str) -> Any:
    return json.loads(value)


def _row_to_memory(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "turn_id": row["turn_id"],
        "reply_to_turn_id": row["reply_to_turn_id"],
        "speaker": row["speaker"],
        "source": row["source"],
        "memory_scope": row["memory_scope"],
        "status": row["status"],
        "raw_text": row["raw_text"],
        "summary": row["summary"],
        "memory_types": _load_json(row["memory_types_json"]),
        "topics": _load_json(row["topics_json"]),
        "keywords": _load_json(row["keywords_json"]),
        "entities": _load_json(row["entities_json"]),
        "facets": _load_json(row["facets_json"]),
        "scores": _load_json(row["scores_json"]),
        "emotion": _load_json(row["emotion_json"]),
        "recall_policy": _load_json(row["recall_policy_json"]),
        "safety": _load_json(row["safety_json"]),
        "save_strength": row["save_strength"],
        "memory_priority": row["memory_priority"],
        "reason_codes": _load_json(row["reason_codes_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_shared_context(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "summary": row["summary"],
        "detail": row["detail"],
        "status": row["status"],
        "source_turn_ids": _load_json(row["source_turn_ids_json"]),
        "tags": _load_json(row["tags_json"]),
        "importance": row["importance"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _find_relevant_shared_contexts(
    query: str,
    *,
    limit: int,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM shared_contexts
            ORDER BY created_at DESC
            """
        ).fetchall()
    contexts = [_row_to_shared_context(row) for row in rows]
    ranked = [
        (context, _score_shared_context_match(query, context))
        for context in contexts
    ]
    ranked = [item for item in ranked if item[1] > 0]
    ranked.sort(
        key=lambda item: (
            item[1],
            item[0]["importance"],
            item[0]["created_at"],
        ),
        reverse=True,
    )
    return [item[0] for item in ranked[:limit]]


def _find_relevant_memories(
    query: str,
    *,
    limit: int,
    speaker: str | None,
    memory_priority: str | None,
    memory_scope: str | None,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    memories = list_memories(
        limit=200,
        db_path=db_path,
        speaker=speaker,
        memory_scope=memory_scope,
    )
    ranked: list[tuple[dict[str, Any], int]] = []
    for memory in memories:
        if memory_priority and memory["memory_priority"] != memory_priority:
            continue
        score = _score_memory_match(query, memory)
        if score <= 0:
            continue
        if _should_suppress_sensitive_memory(query, memory, score):
            continue
        ranked.append((memory, score))

    ranked.sort(
        key=lambda item: (
            item[1],
            PRIORITY_ORDER.get(item[0]["memory_priority"], 0),
            item[0]["save_strength"],
            item[0]["created_at"],
        ),
        reverse=True,
    )
    return [item[0] for item in ranked[:limit]]


def _score_shared_context_match(query: str, context: dict[str, Any]) -> int:
    haystacks = [
        context["summary"],
        context["detail"],
        *context["tags"],
    ]
    return _match_score(query, haystacks)


def _score_memory_match(query: str, memory: dict[str, Any]) -> int:
    haystacks = [
        memory["raw_text"],
        memory["summary"],
        *memory["topics"],
        *memory["keywords"],
        *memory["entities"],
        *memory["reason_codes"],
    ]
    return _match_score(query, haystacks)


def _match_score(query: str, haystacks: list[str]) -> int:
    query_terms = _query_terms(query)
    score = 0
    for term in query_terms:
        for haystack in haystacks:
            if term and term in haystack.lower():
                score += 1
                break
    return score


def _query_terms(query: str) -> list[str]:
    normalized = query.lower().strip()
    terms = [part for part in normalized.replace("　", " ").split() if part]
    if not terms:
        return [normalized]
    if normalized not in terms:
        terms.append(normalized)
    return _unique_strings(terms)


def _should_suppress_sensitive_memory(query: str, memory: dict[str, Any], score: int) -> bool:
    if memory["safety"]["sensitivity"] != "sensitive":
        return False
    if score >= 2:
        return False
    query_terms = set(_query_terms(query))
    memory_terms = {
        *[item.lower() for item in memory["topics"]],
        *[item.lower() for item in memory["keywords"]],
        *[item.lower() for item in memory["entities"]],
    }
    return query_terms.isdisjoint(memory_terms)


def _default_memory_scope(speaker: str) -> str:
    if speaker == "assistant":
        return "assistant_trace"
    return "user_memory"


def _default_status(speaker: str) -> str:
    if speaker == "assistant":
        return "proposed"
    return "asserted"


def _has_shared_context_signal(text: str) -> bool:
    normalized = text.strip()
    return any(term in normalized for term in ASSISTANT_SHARED_CONTEXT_TERMS)


def _is_user_acceptance_text(text: str) -> bool:
    normalized = (
        text.strip()
        .lower()
        .replace("。", "")
        .replace("！", "")
        .replace("!", "")
        .replace(" ", "")
    )
    return normalized in USER_ACCEPTANCE_TERMS


def _append_reason_code(reason_codes: list[str], code: str) -> list[str]:
    if code in reason_codes:
        return reason_codes
    return [*reason_codes, code]


def _find_message_by_turn_id(conn: sqlite3.Connection, turn_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM memories
        WHERE turn_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (turn_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_memory(row)


def _can_promote_to_accepted(referenced: dict[str, Any] | None) -> bool:
    if referenced is None:
        return False
    return (
        referenced["speaker"] == "assistant"
        and referenced["memory_scope"] == "shared_context_candidate"
        and referenced["status"] == "proposed"
    )


def _mark_message_accepted(conn: sqlite3.Connection, turn_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM memories
        WHERE turn_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (turn_id,),
    ).fetchone()
    if row is None:
        return None
    message = _row_to_memory(row)
    reason_codes = _append_reason_code(message["reason_codes"], "accepted_by_user_ack")
    conn.execute(
        """
        UPDATE memories
        SET status = ?, updated_at = ?, reason_codes_json = ?
        WHERE turn_id = ?
        """,
        ("accepted", utc_now_iso(), _dump_json(reason_codes), turn_id),
    )
    message["status"] = "accepted"
    message["updated_at"] = utc_now_iso()
    message["reason_codes"] = reason_codes
    return message


def _ensure_shared_context_from_messages(
    conn: sqlite3.Connection,
    *,
    proposal: dict[str, Any] | None,
    acceptance: dict[str, Any],
) -> None:
    if proposal is None:
        return
    context_id = f"ctx_{proposal['turn_id']}"
    existing = conn.execute(
        """
        SELECT id
        FROM shared_contexts
        WHERE id = ?
        LIMIT 1
        """,
        (context_id,),
    ).fetchone()
    if existing is not None:
        return

    source_turn_ids = [proposal["turn_id"], acceptance["turn_id"]]
    tags = _unique_strings(
        proposal["memory_types"]
        + acceptance["memory_types"]
        + [proposal["memory_scope"], acceptance["memory_scope"]]
    )
    detail = (
        f"proposal: {proposal['raw_text']}\n"
        f"acceptance: {acceptance['raw_text']}"
    )
    importance = round(max(proposal["save_strength"], acceptance["save_strength"]), 2)
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO shared_contexts (
            id, summary, detail, status, source_turn_ids_json, tags_json,
            importance, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            context_id,
            proposal["summary"],
            detail,
            "accepted",
            _dump_json(source_turn_ids),
            _dump_json(tags),
            importance,
            now,
            None,
        ),
    )


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
