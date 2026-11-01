"""fetch_signals CLI options and cursor handling. The DB connection is faked; no network."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from adapters.base import BaseAdapter
from common.schema import ProblemSignal
from jobs import fetch_signals
from jobs.fetch_signals import SourceConfig, parse_args, run_source

CURSOR = datetime(2026, 9, 1, tzinfo=timezone.utc)


class FakeConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))


class FakeAdapter(BaseAdapter):
    source = "hn"

    def __init__(self) -> None:
        self.since: datetime | None = None

    def fetch(self, since: datetime) -> list[ProblemSignal]:
        self.since = since
        return []


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> FakeAdapter:
    fake = FakeAdapter()
    monkeypatch.setitem(fetch_signals.ADAPTERS, "hn", lambda config: fake)
    monkeypatch.setattr(fetch_signals, "upsert_signals", lambda signals, conn: len(signals))
    return fake


def test_defaults_are_a_normal_run() -> None:
    args = parse_args([])
    assert args.source is None and args.backfill_days is None


def test_parses_one_off_options() -> None:
    args = parse_args(["--source", "hn", "--backfill-days", "365"])
    assert args.source == "hn" and args.backfill_days == 365


@pytest.mark.parametrize("argv", [["--source", "reddit"], ["--backfill-days", "0"]])
def test_rejects_bad_options(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_normal_run_uses_and_advances_cursor(adapter: FakeAdapter) -> None:
    conn = FakeConn()
    result = run_source(conn, SourceConfig("hn", 7, {}, CURSOR))  # type: ignore[arg-type]
    assert result.error is None
    assert adapter.since == CURSOR
    ((sql, params),) = conn.executed
    assert "last_fetched_at" in sql and params[1] == 7


def test_backfill_overrides_since_and_keeps_cursor(adapter: FakeAdapter) -> None:
    conn = FakeConn()
    before = datetime.now(timezone.utc)
    result = run_source(  # type: ignore[arg-type]
        conn, SourceConfig("hn", 7, {}, CURSOR), timedelta(days=365)
    )
    assert result.error is None
    assert adapter.since is not None
    assert before - timedelta(days=365) <= adapter.since <= datetime.now(timezone.utc) - timedelta(days=365)
    assert conn.executed == []


def test_load_sources_filters_by_type() -> None:
    class Cursor:
        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def execute(self, sql: str) -> None:
            pass

        def fetchall(self) -> list[Mapping[str, Any]]:
            return [
                {"id": 1, "source_type": "github", "config": {}, "is_active": True, "last_fetched_at": None},
                {"id": 2, "source_type": "hn", "config": {}, "is_active": True, "last_fetched_at": None},
            ]

    class Conn:
        def cursor(self, row_factory: Any = None) -> Cursor:
            return Cursor()

    sources = fetch_signals.load_sources(Conn(), "hn")  # type: ignore[arg-type]
    assert [s.label for s in sources] == ["hn#2"]
