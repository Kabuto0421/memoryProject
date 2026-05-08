"""FastAPI application for a simple conversational long-term memory MVP."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.memory.store import create_memory, create_message, init_db, list_memories, list_messages


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize local SQLite storage on startup."""
    init_db()
    yield


app = FastAPI(title="Long Memory Prototype", lifespan=lifespan)


class MemoryCreateRequest(BaseModel):
    """Incoming request body for memory creation."""

    raw_text: str = Field(..., min_length=1, description="Conversation text to remember.")


class MessageCreateRequest(BaseModel):
    """Incoming request body for conversation turn ingestion."""

    text: str = Field(..., min_length=1, description="Conversation turn text.")
    turn_id: str | None = Field(default=None, description="Client-provided turn id.")
    reply_to_turn_id: str | None = Field(default=None, description="Parent turn id when this message is a reply.")
    speaker: Literal["user", "assistant"] = Field(default="user", description="Message speaker.")
    source: str = Field(default="chat", description="Origin of the message.")
    memory_scope: Literal["user_memory", "assistant_trace", "shared_context_candidate"] | None = Field(
        default=None,
        description="Optional explicit scope override.",
    )
    status: Literal["asserted", "proposed", "accepted", "rejected", "unresolved"] | None = Field(
        default=None,
        description="Optional explicit status override.",
    )


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Return a simple health payload."""
    return {"status": "ok"}


@app.get("/memories")
def get_memories(limit: int = 20) -> dict[str, object]:
    """List recent memories."""
    memories = list_memories(limit=limit)
    return {"count": len(memories), "memories": memories}


@app.get("/messages")
def get_messages(
    limit: int = 20,
    speaker: Literal["user", "assistant"] | None = None,
    memory_scope: Literal["user_memory", "assistant_trace", "shared_context_candidate"] | None = None,
    status: Literal["asserted", "proposed", "accepted", "rejected", "unresolved"] | None = None,
) -> dict[str, object]:
    """List recent conversation turns with optional metadata filters."""
    messages = list_messages(limit=limit, speaker=speaker, memory_scope=memory_scope, status=status)
    return {"count": len(messages), "messages": messages}


@app.post("/memories")
def post_memory(request: MemoryCreateRequest) -> dict[str, object]:
    """Create a new memory from raw conversational text."""
    memory = create_memory(request.raw_text)
    return {
        "memory": memory,
        "save_strength": memory["save_strength"],
        "memory_priority": memory["memory_priority"],
        "reason_codes": memory["reason_codes"],
    }


@app.post("/messages")
def post_message(request: MessageCreateRequest) -> dict[str, object]:
    """Create a new conversation turn with speaker-aware metadata."""
    message = create_message(
        request.text,
        turn_id=request.turn_id,
        reply_to_turn_id=request.reply_to_turn_id,
        speaker=request.speaker,
        source=request.source,
        memory_scope=request.memory_scope,
        status=request.status,
    )
    return {
        "message": message,
        "memory_scope": message["memory_scope"],
        "status": message["status"],
        "save_strength": message["save_strength"],
        "memory_priority": message["memory_priority"],
        "reason_codes": message["reason_codes"],
    }
