"""HTTP API routes. The DB connection and the embedding model are faked."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

import main

KEY = "test-service-key"
AUTH = {"X-Service-Key": KEY}
USER_ID = "00000000-0000-4000-8000-000000000001"
FAKE_VECTOR = [0.5] * 384


class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeConn:
    """Answers each SELECT by the table it reads; records every statement."""

    def __init__(
        self,
        user_exists: bool = True,
        skills: list[tuple[str, int]] | None = None,
        interests: list[str] | None = None,
        stack: list[str] | None = None,
    ) -> None:
        self.user_exists = user_exists
        self.skills = skills or []
        self.interests = interests or []
        self.stack = stack
        self.executed: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.executed.append((sql, params))
        if sql.startswith("SELECT 1 FROM users"):
            return FakeResult([(1,)] if self.user_exists else [])
        if "FROM user_skills" in sql:
            return FakeResult(list(self.skills))
        if "FROM user_interests" in sql:
            return FakeResult([(name,) for name in self.interests])
        if "FROM constraints" in sql:
            return FakeResult([(self.stack,)] if self.stack is not None else [])
        return FakeResult([])

    def updates(self) -> list[tuple[str, Any]]:
        return [(sql, params) for sql, params in self.executed if sql.startswith("UPDATE")]


@pytest.fixture
def embedded_texts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def fake_embed(text: str) -> list[float]:
        seen.append(text)
        return FAKE_VECTOR

    monkeypatch.setattr(main, "embed_text", fake_embed)
    monkeypatch.setenv("SERVICE_KEY", KEY)
    return seen


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def use_conn(conn: FakeConn) -> FakeConn:
    main.app.dependency_overrides[main.get_db] = lambda: conn
    return conn


def test_health_needs_no_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_KEY", raising=False)
    resp = client.get("/health")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-Service-Key": "wrong"}])
def test_rejects_missing_or_wrong_key(
    client: TestClient, embedded_texts: list[str], headers: dict[str, str]
) -> None:
    assert client.post("/embed", json={"text": "hi"}, headers=headers).status_code == 401
    conn = use_conn(FakeConn())
    resp = client.post(f"/users/{USER_ID}/refresh-embedding", headers=headers)
    assert resp.status_code == 401
    assert conn.executed == [] and embedded_texts == []


def test_unconfigured_key_fails_closed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SERVICE_KEY", raising=False)
    resp = client.post("/embed", json={"text": "hi"}, headers={"X-Service-Key": ""})
    assert resp.status_code == 503


def test_embed_returns_vector(client: TestClient, embedded_texts: list[str]) -> None:
    resp = client.post("/embed", json={"text": "graph databases"}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"embedding": FAKE_VECTOR}
    assert embedded_texts == ["graph databases"]


def test_embed_rejects_empty_text(client: TestClient, embedded_texts: list[str]) -> None:
    assert client.post("/embed", json={"text": ""}, headers=AUTH).status_code == 422
    assert embedded_texts == []


def test_refresh_builds_profile_and_stores_vector(
    client: TestClient, embedded_texts: list[str]
) -> None:
    conn = use_conn(
        FakeConn(
            skills=[("python", 5), ("react", 3)],
            interests=["climate", "health"],
            stack=["python", "postgresql"],
        )
    )
    resp = client.post(f"/users/{USER_ID}/refresh-embedding", headers=AUTH)

    assert resp.status_code == 200
    expected = (
        "Skills: python (proficiency 5/5), react (proficiency 3/5)\n"
        "Interests: climate, health\n"
        "Preferred stack: python, postgresql"
    )
    assert resp.json() == {"user_id": USER_ID, "profile_text": expected, "embedded": True}
    assert embedded_texts == [expected]
    [(sql, (vector, user_id))] = conn.updates()
    assert "profile_embedding" in sql and str(user_id) == USER_ID
    assert vector == main.to_vector_literal(FAKE_VECTOR)


def test_refresh_unknown_user_is_404(client: TestClient, embedded_texts: list[str]) -> None:
    conn = use_conn(FakeConn(user_exists=False))
    resp = client.post(f"/users/{USER_ID}/refresh-embedding", headers=AUTH)
    assert resp.status_code == 404
    assert conn.updates() == [] and embedded_texts == []


def test_refresh_empty_profile_clears_embedding(
    client: TestClient, embedded_texts: list[str]
) -> None:
    conn = use_conn(FakeConn(stack=None))
    resp = client.post(f"/users/{USER_ID}/refresh-embedding", headers=AUTH)
    assert resp.status_code == 200 and resp.json()["embedded"] is False
    assert embedded_texts == []
    [(_, (vector, _))] = conn.updates()
    assert vector is None


def test_refresh_rejects_non_uuid(client: TestClient, embedded_texts: list[str]) -> None:
    use_conn(FakeConn())
    assert client.post("/users/not-a-uuid/refresh-embedding", headers=AUTH).status_code == 422
