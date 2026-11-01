"""Small HTTP API over the embedding model, for the web app.

Run from services/ingestion:  uvicorn main:app --reload

Every route except /health requires the header X-Service-Key to equal the
SERVICE_KEY env var. If SERVICE_KEY is unset, those routes return 503 rather
than running unauthenticated.
"""

import hmac
import os
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from common.db import get_connection
from common.embeddings import embed_text
from jobs.embed_signals import to_vector_literal

load_dotenv()


def require_service_key(
    x_service_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = os.environ.get("SERVICE_KEY")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SERVICE_KEY is not configured")
    if x_service_key is None or not hmac.compare_digest(
        x_service_key.encode(), expected.encode()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-Service-Key")


def get_db() -> Iterator[psycopg.Connection]:
    """One connection per request; commits on success, rolls back on error."""
    with get_connection() as conn:
        yield conn


app = FastAPI(title="Brew ingestion service")
protected = [Depends(require_service_key)]


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1)


class EmbedResponse(BaseModel):
    embedding: list[float]


class RefreshResponse(BaseModel):
    user_id: UUID
    profile_text: str
    # False when the user has no skills, interests or stack: the stored
    # embedding is cleared instead of embedding an empty string.
    embedded: bool


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/embed", dependencies=protected)
def embed(body: EmbedRequest) -> EmbedResponse:
    return EmbedResponse(embedding=embed_text(body.text))


def build_profile_text(
    skills: list[tuple[str, int]], interests: list[str], preferred_stack: list[str]
) -> str:
    parts = []
    if skills:
        parts.append(
            "Skills: " + ", ".join(f"{name} (proficiency {level}/5)" for name, level in skills)
        )
    if interests:
        parts.append("Interests: " + ", ".join(interests))
    if preferred_stack:
        parts.append("Preferred stack: " + ", ".join(preferred_stack))
    return "\n".join(parts)


@app.post("/users/{user_id}/refresh-embedding", dependencies=protected)
def refresh_user_embedding(
    user_id: UUID, conn: Annotated[psycopg.Connection, Depends(get_db)]
) -> RefreshResponse:
    if conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    skills = conn.execute(
        "SELECT s.name, us.proficiency FROM user_skills us"
        " JOIN skills s ON s.id = us.skill_id"
        " WHERE us.user_id = %s ORDER BY us.proficiency DESC, s.name",
        (user_id,),
    ).fetchall()
    interests = conn.execute(
        "SELECT i.name FROM user_interests ui"
        " JOIN interests i ON i.id = ui.interest_id"
        " WHERE ui.user_id = %s ORDER BY i.name",
        (user_id,),
    ).fetchall()
    stack_row = conn.execute(
        "SELECT preferred_stack FROM constraints WHERE user_id = %s", (user_id,)
    ).fetchone()

    text = build_profile_text(
        [(name, level) for name, level in skills],
        [name for (name,) in interests],
        (stack_row[0] or []) if stack_row else [],
    )
    vector = to_vector_literal(embed_text(text)) if text else None
    conn.execute(
        "UPDATE users SET profile_embedding = %s::vector WHERE id = %s", (vector, user_id)
    )
    return RefreshResponse(user_id=user_id, profile_text=text, embedded=vector is not None)
