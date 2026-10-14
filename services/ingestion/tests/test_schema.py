from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from common.schema import RAW_TEXT_MAX_CHARS, ProblemSignal


def make(**overrides: Any) -> ProblemSignal:
    fields: dict[str, Any] = {
        "source": "github",
        "external_id": "octo/repo#1",
        "title": "Something is broken",
        "raw_text": "Steps to reproduce...",
    }
    fields.update(overrides)
    return ProblemSignal(**fields)


@pytest.mark.parametrize("source", ["github", "arxiv", "hn"])
def test_allowed_sources(source: str) -> None:
    assert make(source=source).source == source


@pytest.mark.parametrize("source", ["reddit", "GitHub", "HN", "", "hackernews"])
def test_rejects_unknown_source(source: str) -> None:
    with pytest.raises(ValidationError):
        make(source=source)


def test_source_is_stripped() -> None:
    assert make(source="  arxiv\n").source == "arxiv"


def test_strips_whitespace_from_text_fields() -> None:
    s = make(
        external_id="  42 ",
        title="\t Title \n",
        raw_text="  body  ",
        url="  https://example.com/x  ",
    )
    assert s.external_id == "42"
    assert s.title == "Title"
    assert s.raw_text == "body"
    assert s.url == "https://example.com/x"


@pytest.mark.parametrize("field", ["title", "external_id"])
@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_required_text_must_not_be_blank(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        make(**{field: value})


def test_raw_text_truncated_to_limit() -> None:
    s = make(raw_text="a" * (RAW_TEXT_MAX_CHARS + 1000))
    assert len(s.raw_text) == RAW_TEXT_MAX_CHARS == 8000


def test_raw_text_at_limit_is_unchanged() -> None:
    text = "b" * RAW_TEXT_MAX_CHARS
    assert make(raw_text=text).raw_text == text


def test_raw_text_stripped_before_truncation() -> None:
    # Leading whitespace must not eat into the 8000-char budget.
    s = make(raw_text=" " * 50 + "c" * RAW_TEXT_MAX_CHARS)
    assert s.raw_text == "c" * RAW_TEXT_MAX_CHARS


def test_raw_text_truncation_does_not_leave_trailing_whitespace() -> None:
    s = make(raw_text="d" * (RAW_TEXT_MAX_CHARS - 2) + "    tail")
    assert s.raw_text == "d" * (RAW_TEXT_MAX_CHARS - 2)


def test_empty_url_becomes_none() -> None:
    assert make(url="   ").url is None
    assert make().url is None


def test_category_tags_cleaned() -> None:
    s = make(category_tags=[" Climate", "climate", "", "  ", "HealthTech", "ai "])
    assert s.category_tags == ["climate", "healthtech", "ai"]


def test_naive_published_at_assumed_utc() -> None:
    s = make(published_at=datetime(2026, 1, 2, 3, 4, 5))
    assert s.published_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_aware_published_at_kept() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=ist)
    assert make(published_at=dt).published_at == dt


def test_published_at_parsed_from_iso_string() -> None:
    s = make(published_at="2026-03-01T12:00:00Z")
    assert s.published_at == datetime(2026, 3, 1, 12, tzinfo=timezone.utc)


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        make(embedding=[0.0] * 384)
