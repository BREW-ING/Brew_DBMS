"""Hacker News adapter: Ask HN posts that describe a problem or ask for a tool.

Uses the HN Algolia API (search_by_date, newest first), filtered server-side by
story type, creation time and minimum points. Every post then goes through
QUALITY_RULES (one of which needs a REQUEST_PHRASES match); survivors are
ranked by points and capped.

Points accumulate for a day or two after posting, so a post that was below
min_points on one run can cross it on the next. Each query therefore reaches
back `lookback_hours` before `since`; re-fetching a post already stored is a
no-op upsert.

Algolia returns at most 1000 hits per query, so long ranges (first runs,
backfills) are split into WINDOW-sized queries, each ranked and capped on its
own.
"""

import html
import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from adapters.base import BaseAdapter
from common.schema import ProblemSignal, Source

log = logging.getLogger(__name__)

API_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://news.ycombinator.com/item?id={}"

# Defaults for ingestion_sources.config; any key present there wins.
DEFAULT_STORY_TYPES = ("ask_hn",)
# 10 leaves only ~2 matching Ask HN posts a month.
DEFAULT_MIN_POINTS = 5
DEFAULT_LOOKBACK_HOURS = 48
DEFAULT_MAX_RESULTS = 200  # signals kept per window

STORY_TYPES = frozenset({"ask_hn", "show_hn", "story", "poll"})  # Algolia tags
HITS_PER_PAGE = 100
# Algolia never returns more than 1000 hits per query.
MAX_PAGES = 10
WINDOW = timedelta(days=30)
MAX_RETRIES = 3
RETRY_WAIT_S = 10.0  # when a 429/5xx has no usable Retry-After
MAX_RETRY_WAIT_S = 120.0

# --------------------------------------------------------------------- html

_PARAGRAPH = re.compile(r"<\s*(p|br)\s*/?\s*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t]+")
_EXTRA_BLANK_LINES = re.compile(r"\n\s*\n+")
_TITLE_PREFIX = re.compile(r"^\s*(ask|show|tell)\s+hn\s*:\s*", re.IGNORECASE)


def strip_html(text: str) -> str:
    """Algolia story_text HTML -> plain text, paragraphs kept as blank lines.

    Text inside tags is kept (a link's text is its URL on HN). Literal < and >
    in posts arrive as entities, so removing tags before unescaping is safe.
    """
    text = _PARAGRAPH.sub("\n\n", text)
    text = html.unescape(_TAG.sub("", text))
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _EXTRA_BLANK_LINES.sub("\n\n", text).strip()


# ------------------------------------------------------------ topic mapping
# category_tags must use the interests vocabulary (db/postgres/schema.sql).
# (topic, pattern) matched against title + text, case-insensitive.
TOPIC_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    (topic, re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE))
    for topic, pattern in [
        ("developer-tools", r"developers?|programmers?|codebases?|IDEs?|debugging|deploy(s|ing|ments?)?"
                            r"|CI|pull requests?|code review|git|APIs?|devops"),
        ("security", r"security|passwords?|phishing|scams?|malware|breach(es)?|2FA|privacy"),
        ("healthtech", r"health|medical|doctors?|patients|therapy|clinics?|hospitals?"),
        # Plural "courses" only: "of course" is everywhere.
        ("education", r"students?|teachers?|teaching|classrooms?|schools?|courses|tutoring"),
        ("accessibility", r"accessibility|a11y|screen readers?|blind|deaf|disabilit(y|ies)|ADHD|dyslexia"),
        ("climate", r"climate|carbon|emissions|solar|energy usage|heat ?pumps?"),
        ("fintech-alt", r"invoices?|invoicing|bookkeeping|taxes|budget(ing)?|small business(es)?"),
        ("civic-tech", r"government|city council|public records|voting|nonprofits?|non-profits?"),
        ("research-tools", r"papers|research(ers)?|citations?|literature|lab notebooks?"),
    ]
]


def map_topics(text: str) -> list[str]:
    return [topic for topic, pattern in TOPIC_KEYWORDS if pattern.search(text)]


# ----------------------------------------------------------- quality filter

# Phrases that mark a post as describing a problem or asking for a tool. Each
# is a case-insensitive regex, matched on word boundaries against the title and
# text; tune here. Posts matching none are dropped.
REQUEST_PHRASES: list[str] = [
    r"is there (a|an|any) (good |simple |open[- ]source )?"
    r"(tool|app|service|library|way|software|product|website|site|alternative|solution)s?",
    r"are there (any )?(good )?(tools|apps|services|libraries|alternatives|solutions)",
    r"does (anyone|anybody) know (of )?(a|an|any)",
    r"how (do|did|does|are|can|should) (you|people|others|i|we|your team|folks) "
    r"(deal with|dealing with|handle|handling|manage|managing|keep track of|track"
    r"|organi[sz]e|avoid|prevent|stop|automate|solve|fix)",
    r"i wish there (was|were)",
    r"wish (i|we) had",
    r"(looking|searching) for (a|an) (tool|app|service|solution|alternative)",
    r"is there (a|any) (better|easier|faster|simpler) way",
    r"(what|which) (tools?|apps?|software|services?) do (you|people) use",
    r"what do you use (for|to)",
    r"why (is|are) there no",
    r"why (isn['’]t|doesn['’]t) there",
    r"(can['’]?t|cannot|couldn['’]t) find (a|an|any) (good )?"
    r"(tool|app|service|library|software|solution|product)s?",
    r"alternatives? (to|for)",
    # Venting alone isn't a problem to build for; needs repetitive manual work.
    r"(tired of|fed up with|sick of) (manually|having to|constantly|always|copying|re-?typing)",
    r"(biggest|main) (pain points?|frustrations?)",
    r"pain points?",
    r"(manual|tedious|painful) (process|work|task)",
]
_REQUEST_PATTERNS = [re.compile(rf"\b(?:{p})\b", re.IGNORECASE) for p in REQUEST_PHRASES]

# The monthly "Who is hiring?" / "Freelancer?" threads are posted as Ask HN.
_HIRING_AUTHORS = frozenset({"whoishiring"})
_HIRING_TITLE = re.compile(
    r"\b(who is hiring|who wants to be hired|seeking freelancer|freelancer\?)", re.IGNORECASE
)


@dataclass(frozen=True)
class PostCandidate:
    """The parts of a search hit the quality rules look at."""

    title: str  # "Ask HN:" prefix already stripped
    text: str  # already plain text (strip_html)
    author: str

    @property
    def request_hits(self) -> int:
        text = f"{self.title}\n{self.text}"
        return sum(1 for p in _REQUEST_PATTERNS if p.search(text))


# (name, drop_if) pairs, checked in order; the first match drops the post.
# Names show up in the per-run drop counts, so keep them short and stable.
# min_points is enforced server-side; it's applied again in _fetch because a
# hit's points can be missing.
QUALITY_RULES: list[tuple[str, Callable[[PostCandidate], bool]]] = [
    ("hiring_thread", lambda c: c.author in _HIRING_AUTHORS or bool(_HIRING_TITLE.search(c.title))),
    ("empty_title", lambda c: not c.title),
    ("no_request_phrase", lambda c: c.request_hits == 0),
]


def rejection_reason(candidate: PostCandidate) -> str | None:
    """Name of the first rule that drops this post, or None to keep it."""
    for name, drop_if in QUALITY_RULES:
        if drop_if(candidate):
            return name
    return None


# ------------------------------------------------------------------ adapter


class HnAdapter(BaseAdapter):
    source: Source = "hn"

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """`config` is ingestion_sources.config for source_type='hn'.

        Recognised keys (all optional; missing ones fall back to defaults):
          story_types:    list[str]  Algolia tags, any of ask_hn, show_hn,
                                     story, poll (ORed)
          min_points:     int        minimum points
          lookback_hours: int        extra hours searched before `since`, so
                                     posts that gain points late are caught
          max_results:    int        most signals kept per 30-day window
        """
        config = dict(config or {})
        story_types = _str_list(config.get("story_types", DEFAULT_STORY_TYPES), "story_types")
        if not story_types:
            raise ValueError("config.story_types must not be empty")
        unknown = set(story_types) - STORY_TYPES
        if unknown:
            raise ValueError(f"config.story_types has unknown types: {sorted(unknown)}")
        self.story_types = list(dict.fromkeys(story_types))
        self.min_points = _int(config, "min_points", DEFAULT_MIN_POINTS, minimum=0)
        self.lookback_hours = _int(config, "lookback_hours", DEFAULT_LOOKBACK_HOURS, minimum=0)
        self.max_results = _int(config, "max_results", DEFAULT_MAX_RESULTS, minimum=1)

        self._client = client
        self._sleep = sleep
        self._clock = clock

    # ------------------------------------------------------------------ public

    def windows(self, since: datetime) -> list[tuple[datetime, datetime | None]]:
        """[start, end) creation-time ranges covering since - lookback to now.
        The last one is open-ended so posts created mid-run aren't cut off."""
        start = since - timedelta(hours=self.lookback_hours)
        now = self._clock()
        ranges: list[tuple[datetime, datetime | None]] = []
        while now - start > WINDOW:
            ranges.append((start, start + WINDOW))
            start += WINDOW
        ranges.append((start, None))
        return ranges

    def build_params(self, start: datetime, page: int, end: datetime | None = None) -> dict[str, Any]:
        tags = self.story_types[0] if len(self.story_types) == 1 else f"({','.join(self.story_types)})"
        filters = [f"created_at_i>={int(start.timestamp())}"]
        if end is not None:
            filters.append(f"created_at_i<{int(end.timestamp())}")
        filters.append(f"points>={self.min_points}")
        return {
            "tags": tags,
            "numericFilters": ",".join(filters),
            "hitsPerPage": HITS_PER_PAGE,
            "page": page,
        }

    def fetch(self, since: datetime) -> list[ProblemSignal]:
        if self._client is not None:
            return self._fetch(self._client, since)
        headers = {"User-Agent": "brew-ingestion"}
        with httpx.Client(timeout=30.0, headers=headers) as client:
            return self._fetch(client, since)

    # ---------------------------------------------------------------- internals

    def _fetch(self, client: httpx.Client, since: datetime) -> list[ProblemSignal]:
        ranked: dict[str, tuple[ProblemSignal, int]] = {}
        for start, end in self.windows(since):
            for signal, points in self._fetch_window(client, start, end):
                ranked.setdefault(signal.external_id, (signal, points))
        return [s for s, _ in sorted(ranked.values(), key=lambda t: t[1], reverse=True)]

    def _fetch_window(
        self, client: httpx.Client, start: datetime, end: datetime | None
    ) -> list[tuple[ProblemSignal, int]]:
        """Top max_results (signal, points) created in [start, end), best first."""
        # objectID -> (signal, points).
        kept: dict[str, tuple[ProblemSignal, int]] = {}
        dropped: Counter[str] = Counter()
        seen = 0
        page = 0
        while page < MAX_PAGES:
            body = self._get(client, self.build_params(start, page, end)).json()
            if page == 0 and int(body.get("nbHits") or 0) > MAX_PAGES * HITS_PER_PAGE:
                log.warning(
                    "HN: %s hits from %s exceed Algolia's 1000-hit cap; the oldest are skipped",
                    body["nbHits"],
                    start.date(),
                )
            hits: list[dict[str, Any]] = body.get("hits", [])
            for hit in hits:
                seen += 1
                result = self._evaluate(hit)
                if isinstance(result, str):
                    dropped[result] += 1
                else:
                    kept.setdefault(result[0].external_id, result)
            page += 1
            if not hits or page >= int(body.get("nbPages") or 0):
                break

        ranked = sorted(kept.values(), key=lambda t: t[1], reverse=True)[: self.max_results]
        log.info(
            "HN %s..%s: %d posts seen, %d passed quality rules, keeping %d; dropped %s",
            start.date(),
            end.date() if end is not None else "now",
            seen,
            len(kept),
            len(ranked),
            dict(dropped.most_common()) or "none",
        )
        return ranked

    def _evaluate(self, hit: dict[str, Any]) -> tuple[ProblemSignal, int] | str:
        """(signal, points) for a post worth keeping, else a drop reason."""
        points = int(hit.get("points") or 0)
        if points < self.min_points:
            return "low_points"
        candidate = PostCandidate(
            title=_TITLE_PREFIX.sub("", hit.get("title") or "").strip(),
            text=strip_html(hit.get("story_text") or ""),
            author=hit.get("author") or "",
        )
        reason = rejection_reason(candidate)
        if reason is not None:
            return reason
        raw_text = candidate.title if not candidate.text else f"{candidate.title}\n\n{candidate.text}"
        try:
            object_id = str(hit["objectID"])
            signal = ProblemSignal(
                source=self.source,
                external_id=object_id,
                title=candidate.title,
                raw_text=raw_text,
                url=ITEM_URL.format(object_id),
                category_tags=map_topics(f"{candidate.title}\n{candidate.text}"),
                published_at=hit.get("created_at"),
            )
        except (KeyError, ValidationError) as exc:
            log.warning("Skipping malformed HN hit %s: %s", hit.get("objectID"), exc)
            return "malformed"
        return signal, points

    def _get(self, client: httpx.Client, params: Mapping[str, Any]) -> httpx.Response:
        for attempt in range(MAX_RETRIES + 1):
            resp = client.get(API_URL, params=params)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                wait = self._retry_wait(resp)
                log.warning("HN Algolia returned HTTP %d; retrying in %.0fs", resp.status_code, wait)
                self._sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        raise AssertionError("unreachable")  # the last attempt always returns or raises

    def _retry_wait(self, resp: httpx.Response) -> float:
        retry_after = resp.headers.get("retry-after")
        try:
            wait = float(retry_after) if retry_after is not None else RETRY_WAIT_S
        except ValueError:  # HTTP-date form; not worth parsing
            wait = RETRY_WAIT_S
        if wait > MAX_RETRY_WAIT_S:
            raise RuntimeError(f"HN Algolia asked us to wait {wait:.0f}s; giving up this run")
        return max(wait, 1.0)


def _str_list(value: Any, name: str) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of strings")
    if not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of strings")
    return list(value)


def _int(config: Mapping[str, Any], key: str, default: int, *, minimum: int) -> int:
    value = config.get(key, default)
    # bool is an int subclass; "true" as a threshold is a config mistake.
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"config.{key} must be an integer >= {minimum}")
    return value
