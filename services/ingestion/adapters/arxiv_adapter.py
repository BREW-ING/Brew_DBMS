"""arXiv adapter: recent abstracts that state an open problem or limitation.

One query per configured category, newest update first, read a page at a time
round-robin until entries fall before `since`. Every paper goes through
QUALITY_RULES: applied primary category, no model-name or theory title, and
an abstract naming both a real-world domain (DOMAIN_KEYWORDS) and a problem
(PROBLEM_PHRASES). Survivors are ranked by how many distinct problem phrases
they hit, then by recency.

The arXiv API asks for no more than one request every 3 seconds; every
request here goes through `_get`, which enforces that.
"""

import calendar
import fnmatch
import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from pydantic import ValidationError

from adapters.base import BaseAdapter
from common.schema import ProblemSignal, Source

log = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"

# Defaults for ingestion_sources.config; any key present there wins.
# Applied categories. cs.CL is mostly method work; the domain-keyword rule
# below is what makes it worth including.
DEFAULT_CATEGORIES = ("cs.HC", "cs.CY", "cs.SE", "cs.SI", "cs.CL")
DEFAULT_MAX_RESULTS = 200  # signals kept per run

# Papers whose *primary* category is one of these are method/theory work even
# when cross-listed into an applied category. fnmatch patterns.
EXCLUDED_PRIMARY_CATEGORIES = ("cs.LG", "cs.CV", "stat.ML", "math.*")

PAGE_SIZE = 100
# cs.CL publishes hundreds of papers a day; bound the requests.
MAX_PAGES_PER_CATEGORY = 3
MIN_REQUEST_INTERVAL_S = 3.0  # arXiv API terms of use
MAX_RETRIES = 3
RETRY_WAIT_S = 10.0  # when a 429/503 has no usable Retry-After
MAX_RETRY_WAIT_S = 120.0

_CATEGORY = re.compile(r"^[a-z-]+(\.[A-Za-z-]+)?$")
_VERSION = re.compile(r"v\d+$")
_WHITESPACE = re.compile(r"\s+")

# ------------------------------------------------------------ topic mapping
# category_tags must use the interests vocabulary (db/postgres/schema.sql):
# climate, healthtech, accessibility, fintech-alt, education, security,
# conservation, civic-tech, developer-tools, research-tools.

# arXiv category (primary or cross-list) -> broad topics. cs.HC, cs.SI and
# cs.CL say nothing about the application area, so they rely on keywords.
CATEGORY_TOPICS: dict[str, tuple[str, ...]] = {
    "cs.CY": ("civic-tech",),
    "cs.SE": ("developer-tools",),
    "cs.PL": ("developer-tools",),
    "cs.CR": ("security",),
    "cs.DL": ("research-tools",),
    "physics.ao-ph": ("climate",),
    "q-bio.PE": ("conservation",),
    "q-fin.GN": ("fintech-alt",),
}

# Real-world people, settings and harms, as (topic, pattern). A paper needs at
# least one match in its title or abstract (rule no_domain_keyword); matches
# with a topic also become category_tags. topic=None: counts as a domain but
# has no interest to map to. Case-insensitive, matched on word boundaries.
DOMAIN_KEYWORDS: list[tuple[str | None, str]] = [
    # Singular "patient" only as a noun phrase; alone it's often the adjective.
    ("healthtech", r"patients|patient (care|records?|outcomes?|safety|data)|clinicians?|clinics?|nurses?|physicians?|caregivers?|hospitals?"
                   r"|health ?care|mental health"),
    ("accessibility", r"(people|users|individuals|students) with (disabilities|visual impairments?"
                      r"|hearing loss|dyslexia|autism)|disabilit(y|ies)|disabled|blind|low[- ]vision"
                      r"|visually impaired|deaf|hard of hearing|sign language|screen readers?"
                      r"|wheelchair users?|accessibility"),
    # Guards keep knowledge-distillation "teacher/student models" out.
    ("education", r"(?<!-)students?(?![- ](models?|networks?))|teachers?(?![- ](models?|networks?|students?))"
                  r"|educators?|classrooms?|schools?|tutors?|tutoring"),
    # Not bare "flooding": "flooding the context" is common in LLM papers.
    ("climate", r"climate|carbon emissions?|floods|flash floods?|flood (risk|damage|warnings?|events?)"
                r"|wildfires?|droughts?|heat ?waves?"
                r"|renewable energy"),
    ("conservation", r"wildlife|biodiversity|deforestation|endangered species|poaching"),
    ("civic-tech", r"citizens?|government(s|al)?|public services?|municipal(ity|ities)?|voters?|civic"
                   r"|policymakers?|misinformation|disinformation|fact[- ]check(ing|ers?)?"),
    ("fintech-alt", r"small businesses|small business owners?|financial inclusion|unbanked"
                    r"|microfinance|remittances?"),
    ("security", r"phishing|scams?|scammers?|cyber ?attacks?|malware|data breach(es)?"),
    ("developer-tools", r"developers?|programmers?|software engineers?|maintainers?|code reviewers?"),
    ("research-tools", r"peer review(ers?)?|librarians?"),
    (None, r"farmers?|smallholders?|agricultur(e|al)|disasters?|emergency (responders?|response)"
           r"|refugees?|migrants?|older adults|elderly|low-income|rural (communities|areas|residents)"
           r"|(gig|frontline|health|farm|domestic|factory) workers|journalists?|social workers?"
           r"|volunteers?|nonprofits?|non-profits?"),  # not "families": "model families"
]
_DOMAIN_PATTERNS = [
    (topic, re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE)) for topic, pattern in DOMAIN_KEYWORDS
]


def map_topics(categories: list[str], text: str) -> list[str]:
    topics: list[str] = []
    for category in categories:
        topics.extend(CATEGORY_TOPICS.get(category, ()))
    topics.extend(topic for topic, pattern in _DOMAIN_PATTERNS if topic and pattern.search(text))
    return list(dict.fromkeys(topics))


# ----------------------------------------------------------- quality filter

# Phrases that signal an abstract states an open problem or limitation. Each is
# a case-insensitive regex, matched on word boundaries; tune here. Abstracts
# matching none are dropped, and the number of distinct matches ranks the rest.
PROBLEM_PHRASES: list[str] = [
    r"remains? (challenging|difficult|unclear|unsolved|elusive)",
    r"open (problem|question|challenge)s?",
    r"lack(s|ing)?",
    r"existing (tools|methods|approaches|systems|models|solutions|techniques) "
    r"(fail|struggle|fall short|are (limited|insufficient|inadequate))",
    r"(fail|fails|struggle|struggles) to",
    r"(major|key|main|significant) (limitation|challenge|bottleneck|barrier)s?",
    r"(little|less) is known",
    r"(unexplored|underexplored|understudied|overlooked)",
    r"(poorly|not well) understood",
    r"(research|knowledge) gaps?",
    r"no (existing|prior) (work|tool|method|dataset|benchmark)s?",
    r"(time-consuming|labou?r-intensive|error-prone|prohibitively (expensive|costly))",
    r"barriers? to",
    r"(scarcity|scarce|shortage) of",
]
_PROBLEM_PATTERNS = [re.compile(rf"\b(?:{p})\b", re.IGNORECASE) for p in PROBLEM_PHRASES]

MIN_ABSTRACT_CHARS = 300

_WITHDRAWN = re.compile(
    r"\b(this (paper|article|submission) (has been|is) withdrawn|withdrawn by the author)",
    re.IGNORECASE,
)
_NOT_A_PAPER = re.compile(r"\b(erratum|corrigendum|proceedings of|workshop proceedings)\b", re.IGNORECASE)
# Case-sensitive on purpose. Either a leading "Name:" whose name is CamelCase
# ("FlowBook:", "DTScribe:"), has a letter-digit run ("Llama3:") or is an
# all-caps acronym of 3+ letters ("REINS:", "UMCR:"; "COVID-19:" is fine), or
# an architecture-style name anywhere ("XNet", "EfficientNetV2", "SwinFormer").
# Plain CamelCase elsewhere in the title is allowed, so studies of real tools
# ("How Students Use ChatGPT", "... on GitHub") survive.
_MODEL_NAME_TITLE = re.compile(
    r"^\s*[A-Za-z0-9-]*(?:[a-z]{2}[A-Z]|[A-Z]{2,}[a-z]{2,}|[A-Za-z]\d)[A-Za-z0-9-]*\s*:"
    r"|^\s*[A-Z]{3,}\s*:"
    r"|\b[A-Za-z0-9]+(?:Net|Former|GAN|BERT)(?:V?\d+)?\b"
)
_THEORY_TITLE = re.compile(
    r"^\s*On\s"
    r"|\b(bounds?|convergence|theorems?|lemmas?|conjectures?|asymptotics?|provabl[ey]"
    r"|NP-hard(ness)?|polynomial[- ]time|minimax)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PaperCandidate:
    """The parts of a feed entry the quality rules look at."""

    title: str
    abstract: str  # whitespace already collapsed
    primary_category: str = ""

    @property
    def problem_hits(self) -> int:
        # Abstract only: a title like "Remains Challenging" alone isn't enough.
        return sum(1 for p in _PROBLEM_PATTERNS if p.search(self.abstract))

    @property
    def domain_hits(self) -> int:
        text = f"{self.title} {self.abstract}"
        return sum(1 for _, p in _DOMAIN_PATTERNS if p.search(text))


def _excluded_primary(c: PaperCandidate) -> bool:
    return any(fnmatch.fnmatchcase(c.primary_category, p) for p in EXCLUDED_PRIMARY_CATEGORIES)


# (name, drop_if) pairs, checked in order; the first match drops the paper.
# Names show up in the per-run filter counts, so keep them short and stable.
QUALITY_RULES: list[tuple[str, Callable[[PaperCandidate], bool]]] = [
    ("excluded_primary", _excluded_primary),
    ("withdrawn", lambda c: bool(_WITHDRAWN.search(c.abstract))),
    ("not_a_paper", lambda c: bool(_NOT_A_PAPER.search(c.title))),
    ("model_name_title", lambda c: bool(_MODEL_NAME_TITLE.search(c.title))),
    ("theory_title", lambda c: bool(_THEORY_TITLE.search(c.title))),
    ("short_abstract", lambda c: len(c.abstract) < MIN_ABSTRACT_CHARS),
    ("no_domain_keyword", lambda c: c.domain_hits == 0),
    ("no_problem_statement", lambda c: c.problem_hits == 0),
]


def rejection_reason(candidate: PaperCandidate) -> str | None:
    """Name of the first rule that drops this paper, or None to keep it."""
    for name, drop_if in QUALITY_RULES:
        if drop_if(candidate):
            return name
    return None


def filter_funnel(evaluated: int, dropped: Mapping[str, int]) -> list[tuple[str, int, int]]:
    """(rule, papers before, papers after) for each rule in order. Rules run
    first-match, so a rule only sees what earlier rules let through."""
    funnel: list[tuple[str, int, int]] = []
    remaining = evaluated
    for name, _ in QUALITY_RULES:
        after = remaining - dropped.get(name, 0)
        funnel.append((name, remaining, after))
        remaining = after
    return funnel


# ------------------------------------------------------------------ helpers


def arxiv_id(entry_id: str) -> str:
    """'http://arxiv.org/abs/2610.01234v2' -> '2610.01234';
    old-style 'http://arxiv.org/abs/hep-th/9901001v1' -> 'hep-th/9901001'."""
    tail = entry_id.split("/abs/", 1)[-1]
    return _VERSION.sub("", tail)


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _entry_updated(entry: Any) -> datetime | None:
    parsed = entry.get("updated_parsed") or entry.get("published_parsed")
    if parsed is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


# ------------------------------------------------------------------ adapter


class ArxivAdapter(BaseAdapter):
    source: Source = "arxiv"

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`config` is ingestion_sources.config for source_type='arxiv'.

        Recognised keys (all optional; missing ones fall back to defaults):
          categories:  list[str]  arXiv categories to watch, e.g. "cs.HC"
          max_results: int        most signals kept per run
        """
        config = dict(config or {})
        categories = _str_list(config.get("categories", DEFAULT_CATEGORIES), "categories")
        if not categories:
            raise ValueError("config.categories must not be empty")
        for category in categories:
            if not _CATEGORY.match(category):
                raise ValueError(f"config.categories has an invalid arXiv category: {category!r}")
        self.categories = list(dict.fromkeys(categories))
        max_results = config.get("max_results", DEFAULT_MAX_RESULTS)
        if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results < 1:
            raise ValueError("config.max_results must be a positive integer")
        self.max_results = max_results

        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    # ------------------------------------------------------------------ public

    def build_params(self, category: str, start: int) -> dict[str, Any]:
        return {
            "search_query": f"cat:{category}",
            "sortBy": "lastUpdatedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": PAGE_SIZE,
        }

    def fetch(self, since: datetime) -> list[ProblemSignal]:
        if self._client is not None:
            return self._fetch(self._client, since)
        headers = {"User-Agent": "brew-ingestion"}
        with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:
            return self._fetch(client, since)

    # ---------------------------------------------------------------- internals

    def _fetch(self, client: httpx.Client, since: datetime) -> list[ProblemSignal]:
        # arXiv id -> (signal, problem_hits, updated).
        kept: dict[str, tuple[ProblemSignal, int, datetime]] = {}
        dropped: Counter[str] = Counter()
        evaluated: set[str] = set()
        fetched = duplicates = 0
        # Round-robin over categories one page at a time, so cs.CL's volume
        # can't use the whole page budget before cs.HC gets a look.
        active = list(self.categories)
        page = 0
        while active and page < MAX_PAGES_PER_CATEGORY and len(kept) < self.max_results * 2:
            still_active: list[str] = []
            for category in active:
                entries, has_more = self._page(client, category, page * PAGE_SIZE)
                for entry in entries:
                    updated = _entry_updated(entry)
                    if updated is not None and updated < since:
                        has_more = False  # sorted newest first: the rest are older
                        break
                    fetched += 1
                    # Cross-listed papers show up under several categories.
                    key = entry.get("id") or ""
                    if key in evaluated:
                        duplicates += 1
                        continue
                    evaluated.add(key)
                    result = self._evaluate(entry, updated)
                    if isinstance(result, str):
                        dropped[result] += 1
                    else:
                        kept.setdefault(result[0].external_id, result)
                if has_more:
                    still_active.append(category)
            active = still_active
            page += 1

        ranked = sorted(kept.values(), key=lambda t: (t[1], t[2]), reverse=True)
        signals = [signal for signal, _, _ in ranked[: self.max_results]]
        self._log_funnel(fetched, duplicates, len(evaluated), dropped, len(kept), len(signals))
        return signals

    def _log_funnel(
        self,
        fetched: int,
        duplicates: int,
        evaluated: int,
        dropped: Mapping[str, int],
        passed: int,
        kept: int,
    ) -> None:
        log.info(
            "arXiv: %d entries in window across %d categories, %d cross-listed duplicates,"
            " %d papers to filter",
            fetched,
            len(self.categories),
            duplicates,
            evaluated,
        )
        for name, before, after in filter_funnel(evaluated, dropped):
            log.info("arXiv filter %-20s %5d -> %5d", name, before, after)
        if dropped.get("malformed"):
            log.info("arXiv: %d malformed entries skipped", dropped["malformed"])
        log.info("arXiv: %d passed all rules, keeping %d (max_results=%d)", passed, kept, self.max_results)

    def _page(self, client: httpx.Client, category: str, start: int) -> tuple[list[Any], bool]:
        resp = self._get(client, self.build_params(category, start))
        feed = feedparser.parse(resp.text)
        entries = list(feed.entries)
        # Errors come back as HTTP 200 (sometimes 400) with a single "Error" entry.
        for entry in entries:
            if "/api/errors" in entry.get("id", ""):
                raise RuntimeError(f"arXiv API error: {entry.get('summary', 'unknown')}")
        if feed.bozo and not entries:
            raise RuntimeError(f"arXiv returned an unparseable feed: {feed.get('bozo_exception')}")
        total = int(feed.feed.get("opensearch_totalresults") or 0)
        has_more = len(entries) == PAGE_SIZE and start + PAGE_SIZE < total
        return entries, has_more

    def _evaluate(
        self, entry: Any, updated: datetime | None
    ) -> tuple[ProblemSignal, int, datetime] | str:
        """(signal, problem_hits, updated) for a paper worth keeping, else a drop reason."""
        categories = [t["term"] for t in entry.get("tags", []) if t.get("term")]
        primary = (entry.get("arxiv_primary_category") or {}).get("term")
        if primary:
            categories.insert(0, primary)
        candidate = PaperCandidate(
            title=_collapse(entry.get("title") or ""),
            abstract=_collapse(entry.get("summary") or ""),
            primary_category=primary or (categories[0] if categories else ""),
        )
        reason = rejection_reason(candidate)
        if reason is not None:
            return reason
        try:
            paper_id = arxiv_id(entry["id"])
            signal = ProblemSignal(
                source=self.source,
                external_id=paper_id,
                title=candidate.title,
                raw_text=f"{candidate.title}\n\n{candidate.abstract}",
                url=f"https://arxiv.org/abs/{paper_id}",
                category_tags=map_topics(categories, f"{candidate.title} {candidate.abstract}"),
                published_at=entry.get("published"),
            )
        except (KeyError, ValidationError) as exc:
            log.warning("Skipping malformed arXiv entry %s: %s", entry.get("id"), exc)
            return "malformed"
        return signal, candidate.problem_hits, updated or datetime.min.replace(tzinfo=timezone.utc)

    def _get(self, client: httpx.Client, params: Mapping[str, Any]) -> httpx.Response:
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            resp = client.get(API_URL, params=params)
            self._last_request = self._clock()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                wait = self._retry_wait(resp)
                log.warning("arXiv returned HTTP %d; retrying in %.0fs", resp.status_code, wait)
                self._sleep(wait)
                continue
            # A 400 carries an error feed with a readable reason; let _page report it.
            if resp.status_code != 400:
                resp.raise_for_status()
            return resp
        raise AssertionError("unreachable")  # the last attempt always returns or raises

    def _throttle(self) -> None:
        # Measured from the previous response, so slow responses don't eat the gap.
        if self._last_request is None:
            return
        wait = self._last_request + MIN_REQUEST_INTERVAL_S - self._clock()
        if wait > 0:
            self._sleep(wait)

    def _retry_wait(self, resp: httpx.Response) -> float:
        retry_after = resp.headers.get("retry-after")
        try:
            wait = float(retry_after) if retry_after is not None else RETRY_WAIT_S
        except ValueError:  # HTTP-date form; not worth parsing
            wait = RETRY_WAIT_S
        if wait > MAX_RETRY_WAIT_S:
            raise RuntimeError(f"arXiv asked us to wait {wait:.0f}s; giving up this run")
        return max(wait, MIN_REQUEST_INTERVAL_S)


def _str_list(value: Any, name: str) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of strings")
    if not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of strings")
    return list(value)
