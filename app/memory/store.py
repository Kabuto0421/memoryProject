"""SQLite-backed storage for conversational memories."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from app.analysis.text_analyzer import analyze_text
from app.core.settings import DB_PATH, ensure_data_dir


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
    source: str = "chat",
    memory_scope: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Analyze and persist a conversational memory."""
    text = raw_text.strip()
    if not text:
        raise ValueError("raw_text must not be empty.")

    init_db(db_path)
    analysis = analyze_text(text)
    resolved_scope = memory_scope or _default_memory_scope(speaker)
    resolved_status = status or _default_status(speaker)
    memory = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "turn_id": turn_id or f"turn_{uuid.uuid4().hex[:12]}",
        "reply_to_turn_id": reply_to_turn_id,
        "speaker": speaker,
        "source": source,
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
        "reason_codes": analysis.reason_codes,
        "created_at": utc_now_iso(),
        "updated_at": None,
    }
    with get_connection(db_path) as conn:
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
    source: str = "chat",
    memory_scope: str | None = None,
    status: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Create a conversation turn using the extended message metadata."""
    return create_memory(
        text,
        db_path=db_path,
        turn_id=turn_id,
        reply_to_turn_id=reply_to_turn_id,
        speaker=speaker,
        source=source,
        memory_scope=memory_scope,
        status=status,
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


def _default_memory_scope(speaker: str) -> str:
    if speaker == "assistant":
        return "assistant_trace"
    return "user_memory"


def _default_status(speaker: str) -> str:
    if speaker == "assistant":
        return "proposed"
    return "asserted"
