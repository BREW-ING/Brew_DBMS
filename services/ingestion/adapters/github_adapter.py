"""GitHub adapter: open issues in mission-driven repos that describe a buildable problem.

Two steps by default:
  1. Repository search finds active repos tagged with any configured topic
     (accessibility, climate, ...). Repo search returns each repo's topics,
     which become the signals' category_tags.
  2. Issue search looks for open, labelled, discussed issues in those repos.
Every issue then goes through QUALITY_RULES; survivors are ranked by
reactions + comments and capped, overall and per repo.
"""

import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from adapters.base import BaseAdapter
from common.schema import ProblemSignal, Source

log = logging.getLogger(__name__)

API_URL = "https://api.github.com"

# Defaults for ingestion_sources.config; any key present there wins.
DEFAULT_TOPICS = (
    "accessibility",
    "education",
    "healthcare",
    "climate",
    "civic-tech",
    "open-data",
    "nonprofit",
    "developer-tools",
)
DEFAULT_LABELS = ("help wanted", "idea", "feature request")
DEFAULT_MIN_INTERACTIONS = 2  # reactions + comments
DEFAULT_MIN_REPO_STARS = 20
DEFAULT_REPOS_PER_TOPIC = 15
# A few repos with huge backlogs otherwise crowd out everything else.
DEFAULT_MAX_PER_REPO = 3

MAX_ISSUES_PER_RUN = 200
PER_PAGE = 100  # GitHub's maximum
SEARCH_RESULT_LIMIT = 1000  # search never returns more than this per query
# Filtering drops many results, so read past the cap, but bound the requests.
MAX_PAGES_PER_QUERY = 3
# repo: qualifiers per issue query. Verified live with 30 (≈1000-char query).
REPOS_PER_QUERY = 25
MAX_RETRIES = 3
# Longest we'll sleep for a rate limit. Search limits reset every minute; a
# longer wait means the hourly core limit is exhausted and the run should fail.
MAX_RATE_LIMIT_WAIT_S = 120.0

# ------------------------------------------------------------------ markdown

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# Fenced blocks (``` or ~~~, 3+ chars); an unclosed fence runs to the end.
_FENCED_CODE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?(?:^[ \t]*\1[ \t]*$|\Z)", re.DOTALL | re.MULTILINE)
_MD_IMAGE = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])")
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_EMPTY_LINK = re.compile(r"\[\s*\]\([^)]*\)")  # left behind by [![badge](...)](...)
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


def clean_markdown(text: str) -> str:
    """Drop HTML comments, fenced code blocks and images from issue markdown."""
    text = text.replace("\r\n", "\n")
    for pattern in (_HTML_COMMENT, _FENCED_CODE, _MD_IMAGE, _HTML_IMAGE, _EMPTY_LINK):
        text = pattern.sub("", text)
    text = _TRAILING_SPACE.sub("", text)
    return _EXTRA_BLANK_LINES.sub("\n\n", text).strip()


# ----------------------------------------------------------- quality filter

MIN_BODY_CHARS = 200  # cleaned body, title excluded
MIN_TITLE_WORDS = 4  # bracketed tags like [Feature] don't count

_TICKET_CODE = re.compile(r"\[[A-Z][A-Z0-9]*-\d+\]|^\s*[A-Z][A-Z0-9]+-\d+\b")
_BRACKET_TAG = re.compile(r"\[[^\]]*\]")
_CHORE_WORD = re.compile(
    r"\b(bump(s|ed)?|release[sd]?|deps|dependenc(y|ies)|ci|typos?|chore)\b", re.IGNORECASE
)
_BUG_REPORT = re.compile(r"^\s*(\[[^\]]*\bbug\b[^\]]*\]|bug(\s+report)?\s*:)", re.IGNORECASE)
_BOT_LOGIN = re.compile(r"(\[bot\]|[-_]bot)$", re.IGNORECASE)
_KNOWN_BOTS = frozenset({"dependabot", "renovate", "github-actions", "stale", "allcontributors"})


@dataclass(frozen=True)
class IssueCandidate:
    """The parts of a search result the quality rules look at."""

    title: str
    body: str  # already cleaned with clean_markdown
    author: str
    author_type: str  # "User", "Bot", "Organization", ...
    reactions: int
    comments: int

    @property
    def interactions(self) -> int:
        return self.reactions + self.comments


def _title_words(title: str) -> int:
    return len(_BRACKET_TAG.sub(" ", title).split())


def _is_bot(c: IssueCandidate) -> bool:
    login = c.author.lower()
    return c.author_type == "Bot" or bool(_BOT_LOGIN.search(login)) or login in _KNOWN_BOTS


# (name, drop_if) pairs, checked in order; the first match drops the issue.
# Names show up in the per-run drop counts, so keep them short and stable.
QUALITY_RULES: list[tuple[str, Callable[[IssueCandidate], bool]]] = [
    ("ticket_code", lambda c: bool(_TICKET_CODE.search(c.title))),
    ("bot_author", _is_bot),
    ("chore_title", lambda c: bool(_CHORE_WORD.search(c.title))),
    ("bug_report", lambda c: bool(_BUG_REPORT.search(c.title))),
    ("short_title", lambda c: _title_words(c.title) < MIN_TITLE_WORDS),
    ("short_body", lambda c: len(c.body) < MIN_BODY_CHARS),
]


def rejection_reason(candidate: IssueCandidate) -> str | None:
    """Name of the first rule that drops this issue, or None to keep it."""
    for name, drop_if in QUALITY_RULES:
        if drop_if(candidate):
            return name
    return None


# ------------------------------------------------------------------ adapter


class GithubAdapter(BaseAdapter):
    source: Source = "github"

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        token: str | None = None,
        *,
        client: httpx.Client | None = None,
        max_issues: int = MAX_ISSUES_PER_RUN,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """`config` is ingestion_sources.config for source_type='github'.

        Recognised keys (all optional; missing ones fall back to defaults):
          topics:           list[str]  repo topics to search within; [] searches
                                       all of GitHub by label instead
          labels:           list[str]  issues with any of these labels
          min_interactions: int        minimum reactions + comments
          min_reactions:    int        minimum reactions (off unless set)
          min_repo_stars:   int        skip tiny/abandoned repos
          repos_per_topic:  int        repos taken per topic (1-100)
          max_per_repo:     int        most issues kept from one repo per run
          queries:          list[str]  raw issue queries, used instead of all
                                       of the above when given
        `is:issue is:open updated:>=<since>` is always added to issue queries.
        """
        config = dict(config or {})
        self.topics = _str_list(config.get("topics", DEFAULT_TOPICS), "topics")
        self.labels = _str_list(config.get("labels", DEFAULT_LABELS), "labels")
        self.min_interactions = _int(config, "min_interactions", DEFAULT_MIN_INTERACTIONS)
        self.min_reactions = _int(config, "min_reactions", None)
        self.min_repo_stars = _int(config, "min_repo_stars", DEFAULT_MIN_REPO_STARS)
        repos_per_topic = _int(config, "repos_per_topic", DEFAULT_REPOS_PER_TOPIC)
        assert repos_per_topic is not None
        if not 1 <= repos_per_topic <= PER_PAGE:
            raise ValueError(f"config.repos_per_topic must be between 1 and {PER_PAGE}")
        self.repos_per_topic = repos_per_topic
        max_per_repo = _int(config, "max_per_repo", DEFAULT_MAX_PER_REPO)
        if not max_per_repo:
            raise ValueError("config.max_per_repo must be at least 1")
        self.max_per_repo = max_per_repo
        self.raw_queries = _str_list(config.get("queries", []), "queries")
        if not self.raw_queries and not self.labels:
            raise ValueError("config needs at least one label or query")

        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.max_issues = max_issues
        self._client = client
        self._sleep = sleep
        self._clock = clock
        # Per rate-limit bucket ("search", "core"): epoch second before which
        # we must not send another request.
        self._blocked_until: dict[str, float] = {}

    # ------------------------------------------------------------------ public

    def build_repo_queries(self) -> list[str]:
        return [
            f"topic:{topic} archived:false stars:>={self.min_repo_stars}" for topic in self.topics
        ]

    def build_issue_queries(self, since: datetime, repos: list[str] | None = None) -> list[str]:
        """Issue search queries. `repos` (full names) scopes them to those repos,
        batched REPOS_PER_QUERY at a time; None means no repo restriction."""
        stamp = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        required = f"is:issue is:open updated:>={stamp}"
        if self.raw_queries:
            return [f"{q} {required}" for q in self.raw_queries]
        # Comma-separated values in one label: qualifier are ORed.
        labels = ",".join(f'"{label}"' for label in self.labels)
        base = f"{required} label:{labels} interactions:>={self.min_interactions}"
        if self.min_reactions is not None:
            base += f" reactions:>={self.min_reactions}"
        if repos is None:
            return [base]
        batches = [repos[i : i + REPOS_PER_QUERY] for i in range(0, len(repos), REPOS_PER_QUERY)]
        return [base + "".join(f" repo:{r}" for r in batch) for batch in batches]

    def fetch(self, since: datetime) -> list[ProblemSignal]:
        if not self.token:
            log.warning("GITHUB_TOKEN is not set; using unauthenticated limits (10 searches/min)")
        if self._client is not None:
            return self._fetch(self._client, since)
        with httpx.Client(base_url=API_URL, timeout=30.0) as client:
            return self._fetch(client, since)

    # ---------------------------------------------------------------- internals

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "brew-ingestion",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _fetch(self, client: httpx.Client, since: datetime) -> list[ProblemSignal]:
        topics = _TopicCache(self, client)
        if self.raw_queries or not self.topics:
            queries = self.build_issue_queries(since)
        else:
            repos = self._discover_repos(client, topics)
            if not repos:
                log.warning("No repositories matched topics %s", self.topics)
                return []
            queries = self.build_issue_queries(since, repos)

        # node_id -> (signal, interactions, repo); dedupes across queries.
        kept: dict[str, tuple[ProblemSignal, int, str]] = {}
        dropped: Counter[str] = Counter()
        seen = 0
        # Round-robin over queries one page at a time, so one query can't use
        # the whole page budget. Read until there's enough to rank from.
        active = queries
        page = 1
        while active and page <= MAX_PAGES_PER_QUERY and len(kept) < self.max_issues * 2:
            still_active: list[str] = []
            for query in active:
                items, has_more = self._search(client, "/search/issues", query, page, "interactions")
                for item in items:
                    seen += 1
                    result = self._evaluate(item, topics)
                    if isinstance(result, str):
                        dropped[result] += 1
                    else:
                        kept.setdefault(result[0].external_id, result)
                if has_more:
                    still_active.append(query)
            active = still_active
            page += 1

        signals: list[ProblemSignal] = []
        per_repo: Counter[str] = Counter()
        for signal, _, repo in sorted(kept.values(), key=lambda t: t[1], reverse=True):
            if len(signals) >= self.max_issues:
                break
            if per_repo[repo] >= self.max_per_repo:
                dropped["repo_cap"] += 1
                continue
            per_repo[repo] += 1
            signals.append(signal)
        log.info(
            "GitHub: %d issues seen, %d passed quality rules, keeping %d; dropped %s",
            seen,
            len(kept),
            len(signals),
            dict(dropped.most_common()) or "none",
        )
        return signals

    def _discover_repos(self, client: httpx.Client, topics: "_TopicCache") -> list[str]:
        repos: list[str] = []
        for query in self.build_repo_queries():
            # Repos with the most open "help wanted" issues first: they're the
            # ones asking outsiders for contributions.
            items, _ = self._search(
                client, "/search/repositories", query, 1, "help-wanted-issues", self.repos_per_topic
            )
            for item in items:
                name = item["full_name"]
                if name not in topics:
                    repos.append(name)
                topics.prefill(item["url"], item.get("topics", []))
        log.info("GitHub: %d repositories across %d topics", len(repos), len(self.topics))
        return repos

    def _search(
        self,
        client: httpx.Client,
        path: str,
        query: str,
        page: int,
        sort: str,
        per_page: int = PER_PAGE,
    ) -> tuple[list[dict[str, Any]], bool]:
        resp = self._get(
            client,
            path,
            params={"q": query, "sort": sort, "order": "desc", "per_page": per_page, "page": page},
        )
        body = resp.json()
        items: list[dict[str, Any]] = body.get("items", [])
        if body.get("incomplete_results"):
            log.warning("GitHub search timed out and returned partial results for page %d", page)
        reachable = min(int(body.get("total_count", 0)), SEARCH_RESULT_LIMIT)
        has_more = len(items) == per_page and page * per_page < reachable
        return items, has_more

    def _evaluate(
        self, item: dict[str, Any], topics: "_TopicCache"
    ) -> tuple[ProblemSignal, int, str] | str:
        """(signal, interactions, repo) for an issue worth keeping, else a drop reason."""
        # is:issue already excludes PRs; this guards against hand-written queries.
        if "pull_request" in item:
            return "pull_request"
        title = (item.get("title") or "").strip()
        body = clean_markdown(item.get("body") or "")
        user = item.get("user") or {}
        candidate = IssueCandidate(
            title=title,
            body=body,
            author=user.get("login") or "",
            author_type=user.get("type") or "",
            reactions=int((item.get("reactions") or {}).get("total_count") or 0),
            comments=int(item.get("comments") or 0),
        )
        reason = rejection_reason(candidate)
        if reason is not None:
            return reason
        try:
            signal = ProblemSignal(
                source=self.source,
                external_id=item["node_id"],
                title=title,
                raw_text=f"{title}\n\n{body}",
                url=item.get("html_url"),
                category_tags=topics.get(item.get("repository_url")),
                published_at=item.get("created_at"),
            )
        except (KeyError, ValidationError) as exc:
            log.warning("Skipping malformed issue %s: %s", item.get("html_url"), exc)
            return "malformed"
        return signal, candidate.interactions, item.get("repository_url") or ""

    def _get(
        self, client: httpx.Client, url: str, params: Mapping[str, Any] | None = None
    ) -> httpx.Response:
        bucket = "search" if url.startswith("/search") else "core"
        for attempt in range(MAX_RETRIES + 1):
            self._wait_for_bucket(bucket)
            # Headers per request, so an injected client gets auth too.
            resp = client.get(url, params=params, headers=self._headers())
            self._record_limits(resp, bucket)
            if resp.status_code in (403, 429) and attempt < MAX_RETRIES:
                wait = self._rate_limit_wait(resp)
                if wait is not None:
                    log.warning(
                        "GitHub rate limit hit (HTTP %d); retrying in %.0fs", resp.status_code, wait
                    )
                    # This sleep already covers the hold _record_limits just set.
                    self._blocked_until.pop(bucket, None)
                    self._sleep(wait)
                    continue
            resp.raise_for_status()
            return resp
        raise AssertionError("unreachable")  # the last attempt always returns or raises

    def _record_limits(self, resp: httpx.Response, bucket: str) -> None:
        # When this response used the last request in the window, hold back the
        # next request for this bucket until the window resets.
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if remaining == "0" and reset is not None:
            self._blocked_until[bucket] = float(reset) + 1

    def _wait_for_bucket(self, bucket: str) -> None:
        until = self._blocked_until.pop(bucket, None)
        if until is None:
            return
        wait = until - self._clock()
        if wait > MAX_RATE_LIMIT_WAIT_S:
            raise RuntimeError(f"GitHub {bucket} rate limit exhausted for another {wait:.0f}s")
        if wait > 0:
            log.info("GitHub %s rate limit reached; waiting %.0fs", bucket, wait)
            self._sleep(wait)

    def _rate_limit_wait(self, resp: httpx.Response) -> float | None:
        """Seconds to wait before retrying, or None if this 403/429 isn't a rate limit."""
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            wait = float(retry_after)
        elif resp.headers.get("x-ratelimit-remaining") == "0" and "x-ratelimit-reset" in resp.headers:
            wait = float(resp.headers["x-ratelimit-reset"]) - self._clock() + 1
        elif resp.status_code == 429:
            wait = 60.0
        else:
            return None  # e.g. a 403 for a bad token or a blocked resource
        if wait > MAX_RATE_LIMIT_WAIT_S:
            raise RuntimeError(f"GitHub rate limit resets in {wait:.0f}s; giving up this run")
        return max(wait, 1.0)


class _TopicCache:
    """Repo topics by repository API URL, fetched at most once per repo per run.

    Repos found by topic search are prefilled for free. For others (raw or
    label-only queries) topics are a nice-to-have: a missing repo yields no
    tags, and any other failure (usually the core rate limit) turns topic
    lookups off for the rest of the run instead of failing the adapter.
    """

    def __init__(self, adapter: GithubAdapter, client: httpx.Client) -> None:
        self._adapter = adapter
        self._client = client
        self._cache: dict[str, list[str]] = {}
        self._enabled = True

    def __contains__(self, full_name: str) -> bool:
        return f"{API_URL}/repos/{full_name}" in self._cache

    def prefill(self, repo_url: str, topics: list[str]) -> None:
        self._cache[repo_url] = _str_list(topics, "topics")

    def get(self, repo_url: str | None) -> list[str]:
        if not repo_url:
            return []
        if repo_url in self._cache:
            return self._cache[repo_url]
        if not self._enabled:
            return []
        try:
            resp = self._adapter._get(self._client, repo_url)
            self._cache[repo_url] = _str_list(resp.json().get("topics", []), "topics")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (404, 451):  # deleted / blocked repo
                self._disable(exc)
            self._cache[repo_url] = []
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            self._disable(exc)
            return []
        return self._cache[repo_url]

    def _disable(self, exc: Exception) -> None:
        log.warning("Repo topic lookup failed (%s); skipping topics for the rest of this run", exc)
        self._enabled = False


def _str_list(value: Any, name: str) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list of strings")
    if not all(isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of strings")
    return list(value)


def _int(config: Mapping[str, Any], key: str, default: int | None) -> int | None:
    value = config.get(key, default)
    if value is None:
        return None
    # bool is an int subclass; "true" as a threshold is a config mistake.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"config.{key} must be a non-negative integer")
    return value
