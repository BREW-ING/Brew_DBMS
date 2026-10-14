"""Shared shape every adapter normalizes its results into.

Mirrors the writable columns of `problem_signals` (db/postgres/schema.sql).
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

RAW_TEXT_MAX_CHARS = 8000

Source = Literal["github", "arxiv", "hn"]


class ProblemSignal(BaseModel):
    # Strips leading/trailing whitespace from every str field, list items included.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", frozen=True)

    source: Source
    external_id: str
    title: str
    raw_text: str = ""
    url: str | None = None
    category_tags: list[str] = []
    published_at: datetime | None = None

    @field_validator("source", mode="before")
    @classmethod
    def _strip_source(cls, v: object) -> object:
        # Literal checks run before str_strip_whitespace would apply.
        return v.strip() if isinstance(v, str) else v

    @field_validator("external_id", "title")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be empty or whitespace-only")
        return v

    @field_validator("raw_text")
    @classmethod
    def _truncate_raw_text(cls, v: str) -> str:
        # rstrip again so a cut that lands in whitespace doesn't leave a tail.
        return v[:RAW_TEXT_MAX_CHARS].rstrip()

    @field_validator("url")
    @classmethod
    def _empty_url_to_none(cls, v: str | None) -> str | None:
        return v or None

    @field_validator("category_tags")
    @classmethod
    def _clean_tags(cls, v: list[str]) -> list[str]:
        # Lowercase, drop empties, de-duplicate while keeping first-seen order,
        # so 'Climate' and 'climate ' count as one topic in the trending view.
        seen: dict[str, None] = {}
        for tag in v:
            tag = tag.strip().lower()
            if tag:
                seen.setdefault(tag, None)
        return list(seen)

    @field_validator("published_at")
    @classmethod
    def _assume_utc(cls, v: datetime | None) -> datetime | None:
        # A naive datetime written to TIMESTAMPTZ is read in the session's
        # time zone; pin it to UTC so the result doesn't depend on the server.
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
