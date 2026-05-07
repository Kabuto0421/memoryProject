"""FastAPI application for a simple conversational long-term memory MVP."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.memory.store import create_memory, init_db, list_memories


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize local SQLite storage on startup."""
    init_db()
    yield


app = FastAPI(title="Long Memory Prototype", lifespan=lifespan)


class MemoryCreateRequest(BaseModel):
    """Incoming request body for memory creation."""

    raw_text: str = Field(..., min_length=1, description="Conversation text to remember.")

@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Return a simple health payload."""
    return {"status": "ok"}


@app.get("/memories")
def get_memories(limit: int = 20) -> dict[str, object]:
    """List recent memories."""
    memories = list_memories(limit=limit)
    return {"count": len(memories), "memories": memories}


@app.post("/memories")
def post_memory(request: MemoryCreateRequest) -> dict[str, object]:
    """Create a new memory from raw conversational text."""
    memory = create_memory(request.raw_text)
    return {"memory": memory}
