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
                raw_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                memory_types_json TEXT NOT NULL,
                topics_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                facets_json TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                emotion_json TEXT NOT NULL,
                recall_policy_json TEXT NOT NULL,
                safety_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )


def create_memory(raw_text: str, db_path: str | None = None) -> dict[str, Any]:
    """Analyze and persist a conversational memory."""
    text = raw_text.strip()
    if not text:
        raise ValueError("raw_text must not be empty.")

    init_db(db_path)
    analysis = analyze_text(text)
    memory = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "raw_text": text,
        "summary": analysis.summary,
        "memory_types": analysis.memory_types,
        "topics": analysis.topics,
        "keywords": analysis.keywords,
        "facets": analysis.facets,
        "scores": analysis.scores,
        "emotion": analysis.emotion,
        "recall_policy": analysis.recall_policy,
        "safety": analysis.safety,
        "created_at": utc_now_iso(),
        "updated_at": None,
    }
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memories (
                id, raw_text, summary, memory_types_json, topics_json, keywords_json,
                facets_json, scores_json, emotion_json, recall_policy_json, safety_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory["id"],
                memory["raw_text"],
                memory["summary"],
                _dump_json(memory["memory_types"]),
                _dump_json(memory["topics"]),
                _dump_json(memory["keywords"]),
                _dump_json(memory["facets"]),
                _dump_json(memory["scores"]),
                _dump_json(memory["emotion"]),
                _dump_json(memory["recall_policy"]),
                _dump_json(memory["safety"]),
                memory["created_at"],
                memory["updated_at"],
            ),
        )
    return memory


def list_memories(limit: int = 50, db_path: str | None = None) -> list[dict[str, Any]]:
    """Return recent memories in reverse chronological order."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM memories
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_memory(row) for row in rows]


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str) -> Any:
    return json.loads(value)


def _row_to_memory(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "raw_text": row["raw_text"],
        "summary": row["summary"],
        "memory_types": _load_json(row["memory_types_json"]),
        "topics": _load_json(row["topics_json"]),
        "keywords": _load_json(row["keywords_json"]),
        "facets": _load_json(row["facets_json"]),
        "scores": _load_json(row["scores_json"]),
        "emotion": _load_json(row["emotion_json"]),
        "recall_policy": _load_json(row["recall_policy_json"]),
        "safety": _load_json(row["safety_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
