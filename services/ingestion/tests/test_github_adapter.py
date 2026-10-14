"""GitHub adapter tests. All HTTP goes through httpx.MockTransport; no network."""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from adapters.github_adapter import (
    MIN_BODY_CHARS,
    QUALITY_RULES,
    GithubAdapter,
    IssueCandidate,
    clean_markdown,
    rejection_reason,
)

FIXTURES = Path(__file__).parent / "fixtures"
ISSUES = json.loads((FIXTURES / "github_search_issues.json").read_text(encoding="utf-8"))
REPOS = json.loads((FIXTURES / "github_search_repositories.json").read_text(encoding="utf-8"))
SINCE = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
NOW = 1_800_000_000.0
STAMP = "updated:>=2026-10-07T12:00:00Z"
LONG_BODY = "x" * MIN_BODY_CHARS

Handler = Callable[[httpx.Request], httpx.Response]


def default_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/search/repositories":
        return httpx.Response(200, json=REPOS)
    if request.url.path == "/search/issues":
        return httpx.Response(200, json=ISSUES)
    if request.url.path.startswith("/repos/"):
        return httpx.Response(200, json={"topics": ["looked-up"]})
    return httpx.Response(404, json={"message": "Not Found"})


class Recorder:
    def __init__(self, handler: Handler = default_handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def paths(self, prefix: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.startswith(prefix)]


def make_adapter(
    recorder: Recorder, config: dict[str, Any] | None = None, **kwargs: Any
) -> tuple[GithubAdapter, list[float]]:
    slept: list[float] = []
    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(recorder))
    adapter = GithubAdapter(
        config, token="test-token", client=client, sleep=slept.append, clock=lambda: NOW, **kwargs
    )
    return adapter, slept


def issue(n: int, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "node_id": f"I_{n}",
        "title": f"Volunteers need a way to plan shifts {n}",
        "body": LONG_BODY,
        "user": {"login": "someone", "type": "User"},
        "comments": 1,
        "reactions": {"total_count": 1},
        "html_url": f"https://github.com/o/r{n}/issues/{n}",
        # One repo per issue so the per-repo cap only applies where a test wants it.
        "repository_url": f"https://api.github.com/repos/o/r{n}",
        "created_at": "2026-10-01T00:00:00Z",
    }
    item.update(overrides)
    return item


# ------------------------------------------------------------ end to end


def test_fetch_filters_ranks_and_tags() -> None:
    recorder = Recorder()
    adapter, _ = make_adapter(recorder)
    signals = adapter.fetch(SINCE)

    # Of the 9 fixture issues only two pass the rules; ranked by reactions + comments.
    assert [s.external_id for s in signals] == ["I_node_88", "I_node_412"]

    keys, csv = signals
    assert keys.category_tags == []  # repo has no topics
    assert csv.source == "github"
    assert csv.title == "Support exporting emissions reports as CSV"
    assert csv.url == "https://github.com/opencarbon/meter/issues/412"
    assert csv.published_at == datetime(2026, 9, 20, 8, 15, tzinfo=timezone.utc)
    # Topics come from the repo search; no per-repo lookups needed.
    assert csv.category_tags == ["climate", "carbon-accounting", "open-data"]
    assert recorder.paths("/repos/") == []

    assert csv.raw_text.startswith("Support exporting emissions reports as CSV\n\n### Problem")
    assert "Add a `to_csv()` export" in csv.raw_text
    for removed in ("<!--", "Thanks for opening", "![", "<img", "```", "AttributeError", "shields.io", "\r"):
        assert removed not in csv.raw_text
    assert "\n\n\n" not in csv.raw_text


def test_default_queries() -> None:
    recorder = Recorder()
    adapter, _ = make_adapter(recorder)
    adapter.fetch(SINCE)

    repo_searches = recorder.paths("/search/repositories")
    assert [r.url.params["q"] for r in repo_searches] == [
        f"topic:{t} archived:false stars:>=20"
        for t in (
            "accessibility", "education", "healthcare", "climate",
            "civic-tech", "open-data", "nonprofit", "developer-tools",
        )
    ]
    assert repo_searches[0].url.params["sort"] == "help-wanted-issues"
    assert repo_searches[0].url.params["per_page"] == "15"

    # Every topic search returns the same two repos; they're queried once.
    (search,) = recorder.paths("/search/issues")
    assert search.headers["Authorization"] == "Bearer test-token"
    assert search.url.params["q"] == (
        f'is:issue is:open {STAMP} label:"help wanted","idea","feature request" '
        "interactions:>=2 repo:opencarbon/meter repo:a11y-kit/reader"
    )
    assert search.url.params["sort"] == "interactions"


def test_issue_queries_batch_repos() -> None:
    adapter, _ = make_adapter(Recorder())
    repos = [f"org/repo{i}" for i in range(30)]
    queries = adapter.build_issue_queries(SINCE, repos)
    assert len(queries) == 2
    assert queries[0].count("repo:") == 25 and queries[1].count("repo:") == 5


def test_query_config() -> None:
    adapter, _ = make_adapter(
        Recorder(),
        {"topics": ["climate"], "labels": ["idea"], "min_interactions": 5, "min_reactions": 1,
         "min_repo_stars": 100},
    )
    assert adapter.build_repo_queries() == ["topic:climate archived:false stars:>=100"]
    assert adapter.build_issue_queries(SINCE) == [
        f'is:issue is:open {STAMP} label:"idea" interactions:>=5 reactions:>=1'
    ]


def test_raw_queries_skip_repo_search_and_look_up_topics() -> None:
    recorder = Recorder()
    adapter, _ = make_adapter(recorder, {"queries": ["org:mozilla"]})
    assert adapter.build_issue_queries(SINCE) == [f"org:mozilla is:issue is:open {STAMP}"]
    signals = adapter.fetch(SINCE)
    assert recorder.paths("/search/repositories") == []
    assert all(s.category_tags == ["looked-up"] for s in signals)
    # One lookup per distinct repo, not per issue.
    assert len(recorder.paths("/repos/")) == 2


def test_empty_topics_searches_all_of_github() -> None:
    recorder = Recorder()
    adapter, _ = make_adapter(recorder, {"topics": []})
    adapter.fetch(SINCE)
    assert recorder.paths("/search/repositories") == []
    (search,) = recorder.paths("/search/issues")
    assert "repo:" not in search.url.params["q"]


def test_no_matching_repos_returns_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/repositories":
            return httpx.Response(200, json={"total_count": 0, "items": []})
        return default_handler(request)

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder)
    assert adapter.fetch(SINCE) == []
    assert recorder.paths("/search/issues") == []


@pytest.mark.parametrize(
    "config",
    [
        {"labels": "enhancement"},
        {"labels": []},
        {"topics": "climate"},
        {"min_interactions": "5"},
        {"min_reactions": -1},
        {"min_repo_stars": True},
        {"repos_per_topic": 0},
        {"repos_per_topic": 101},
        {"max_per_repo": 0},
        {"queries": [1]},
    ],
)
def test_rejects_bad_config(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        GithubAdapter(config, token="t")


# ------------------------------------------------------------ quality rules


def candidate(**overrides: Any) -> IssueCandidate:
    fields: dict[str, Any] = {
        "title": "Volunteers need a way to plan shifts",
        "body": LONG_BODY,
        "author": "someone",
        "author_type": "User",
        "reactions": 0,
        "comments": 0,
    }
    fields.update(overrides)
    return IssueCandidate(**fields)


def test_good_candidate_passes() -> None:
    assert rejection_reason(candidate()) is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"title": "[BFW-7446][ENHANCEMENT] Allow automatic offset tool calibration"}, "ticket_code"),
        ({"title": "ABC-123 add a way to export reports"}, "ticket_code"),
        ({"author": "dependabot[bot]"}, "bot_author"),
        ({"author": "renovate"}, "bot_author"),
        ({"author": "release-bot"}, "bot_author"),
        ({"author_type": "Bot"}, "bot_author"),
        ({"title": "Bump lodash from 4.17.20 to 4.17.21"}, "chore_title"),
        ({"title": "Prepare the next release for the docs site"}, "chore_title"),
        ({"title": "Update deps for the web frontend"}, "chore_title"),
        ({"title": "Run the CI on Windows runners too"}, "chore_title"),
        ({"title": "Fix a typo in the README intro"}, "chore_title"),
        ({"title": "[Bug]: Chart export crashes on Safari"}, "bug_report"),
        ({"title": "Bug report: login fails after reset"}, "bug_report"),
        ({"title": "Kustomize plugin"}, "short_title"),
        ({"title": "Multi-core/Multithreaded support"}, "short_title"),
        ({"title": "[Feature Request] Dark mode"}, "short_title"),  # tags don't count as words
        ({"body": "x" * (MIN_BODY_CHARS - 1)}, "short_body"),
    ],
)
def test_rules_drop(overrides: dict[str, Any], reason: str) -> None:
    assert rejection_reason(candidate(**overrides)) == reason


@pytest.mark.parametrize(
    "title",
    [
        "[Feature Request]Need the client to support wayland natively",
        "Accessible bus timetables for low-vision riders",  # "bus" isn't "bug"
        "Better circuit diagrams for the physics course",  # "circuit" contains "ci"
    ],
)
def test_rules_keep(title: str) -> None:
    assert rejection_reason(candidate(title=title)) is None


def test_rule_names_are_unique() -> None:
    names = [name for name, _ in QUALITY_RULES]
    assert len(names) == len(set(names))


def test_fetch_keeps_highest_interactions_when_capped() -> None:
    items = [
        issue(1, comments=1),
        issue(2, comments=50),
        issue(3, title="Kustomize plugin", comments=99),  # dropped despite engagement
        issue(4, reactions={"total_count": 10}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"total_count": len(items), "items": items})
        return default_handler(request)

    adapter, _ = make_adapter(Recorder(handler), {"topics": []}, max_issues=2)
    assert [s.external_id for s in adapter.fetch(SINCE)] == ["I_2", "I_4"]


def test_caps_issues_per_repo() -> None:
    same_repo = {"repository_url": "https://api.github.com/repos/big/backlog"}
    items = [issue(i, comments=10 - i, **same_repo) for i in range(5)] + [issue(9)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"total_count": len(items), "items": items})
        return default_handler(request)

    adapter, _ = make_adapter(Recorder(handler), {"topics": [], "max_per_repo": 2})
    # The repo's two most-discussed issues, then the other repo's issue.
    assert [s.external_id for s in adapter.fetch(SINCE)] == ["I_0", "I_1", "I_9"]


# ------------------------------------------------------------ paging and limits


def test_paginates_and_stops_at_page_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/issues":
            page = int(request.url.params["page"])
            items = [issue(page * 1000 + i) for i in range(100)]
            return httpx.Response(200, json={"total_count": 5000, "items": items})
        return default_handler(request)

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder, {"topics": []}, max_issues=1000)
    assert len(adapter.fetch(SINCE)) == 300
    assert [r.url.params["page"] for r in recorder.paths("/search/issues")] == ["1", "2", "3"]


def test_stops_paging_once_enough_to_rank() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/issues":
            page = int(request.url.params["page"])
            items = [issue(page * 1000 + i) for i in range(100)]
            return httpx.Response(200, json={"total_count": 5000, "items": items})
        return default_handler(request)

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder, {"topics": []}, max_issues=50)
    assert len(adapter.fetch(SINCE)) == 50
    # 100 good issues on page 1 is already 2x the cap.
    assert len(recorder.paths("/search/issues")) == 1


def test_backs_off_on_rate_limit_using_reset_header() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/search/issues":
            calls += 1
            if calls == 1:
                headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(NOW) + 30)}
                return httpx.Response(403, headers=headers, json={"message": "API rate limit exceeded"})
        return default_handler(request)

    adapter, slept = make_adapter(Recorder(handler))
    assert len(adapter.fetch(SINCE)) == 2
    assert slept == [31.0]  # until reset, plus one second of slack


def test_honours_retry_after_on_429() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/search/repositories":
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={"retry-after": "7"})
        return default_handler(request)

    adapter, slept = make_adapter(Recorder(handler))
    adapter.fetch(SINCE)
    assert slept == [7.0]


def test_waits_before_next_request_when_quota_used_up() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/issues":
            page = int(request.url.params["page"])
            headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(NOW) + 20)}
            items = [issue(page * 1000 + i) for i in range(100)]
            return httpx.Response(200, headers=headers, json={"total_count": 300, "items": items})
        return default_handler(request)

    adapter, slept = make_adapter(Recorder(handler), {"topics": []}, max_issues=100)
    adapter.fetch(SINCE)
    assert slept == [21.0]  # before page 2 only


def test_forbidden_without_rate_limit_raises() -> None:
    adapter, slept = make_adapter(
        Recorder(lambda r: httpx.Response(403, json={"message": "Resource not accessible"}))
    )
    with pytest.raises(httpx.HTTPStatusError):
        adapter.fetch(SINCE)
    assert slept == []


def test_long_rate_limit_fails_instead_of_hanging() -> None:
    headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(NOW) + 3600)}
    adapter, slept = make_adapter(Recorder(lambda r: httpx.Response(403, headers=headers)))
    with pytest.raises(RuntimeError, match="rate limit"):
        adapter.fetch(SINCE)
    assert slept == []


def test_topic_failure_does_not_fail_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/issues":
            return httpx.Response(200, json=ISSUES)
        return httpx.Response(500)

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder, {"topics": []})
    signals = adapter.fetch(SINCE)
    assert len(signals) == 2
    assert all(s.category_tags == [] for s in signals)
    # After the first failure, topic lookups are switched off for the run.
    assert len(recorder.paths("/repos/")) == 1


def test_clean_markdown() -> None:
    text = (
        "Intro\n<!-- hidden\nmulti-line -->\n"
        "~~~\nfenced tilde\n~~~\n"
        "  ```js\nindented fence\n  ```\n"
        "keep `inline code`\n"
        "![alt](a.png) ![ref][img] <IMG SRC='x'>\n"
        "```\nunclosed fence runs to the end"
    )
    assert clean_markdown(text) == "Intro\n\nkeep `inline code`"
