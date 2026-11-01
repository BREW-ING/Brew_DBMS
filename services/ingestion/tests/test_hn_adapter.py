"""Hacker News adapter tests. All HTTP goes through httpx.MockTransport; no network."""

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from adapters.hn_adapter import (
    HITS_PER_PAGE,
    MAX_PAGES,
    QUALITY_RULES,
    REQUEST_PHRASES,
    WINDOW,
    HnAdapter,
    PostCandidate,
    map_topics,
    rejection_reason,
    strip_html,
)

FIXTURES = Path(__file__).parent / "fixtures"
RESPONSE = json.loads((FIXTURES / "hn_search_by_date.json").read_text(encoding="utf-8"))
SINCE = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, handler: Handler = lambda r: httpx.Response(200, json=RESPONSE)) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make_adapter(
    recorder: Recorder, config: dict[str, Any] | None = None, now: datetime = NOW
) -> tuple[HnAdapter, list[float]]:
    slept: list[float] = []
    client = httpx.Client(transport=httpx.MockTransport(recorder))
    return HnAdapter(config, client=client, sleep=slept.append, clock=lambda: now), slept


def hit(n: int, **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "objectID": str(n),
        "title": f"Ask HN: Is there a tool for planning volunteer shifts {n}?",
        "story_text": "",
        "author": "someone",
        "points": 20,
        "created_at": "2026-10-10T00:00:00Z",
    }
    item.update(overrides)
    return item


def page_response(hits: list[dict[str, Any]], page: int, nb_pages: int) -> httpx.Response:
    return httpx.Response(200, json={"hits": hits, "page": page, "nbPages": nb_pages})


# ------------------------------------------------------------ end to end


def test_fetch_filters_ranks_and_cleans() -> None:
    adapter, _ = make_adapter(Recorder())
    signals = adapter.fetch(SINCE)

    # 3 of the 7 hits pass; ranked by points.
    assert [s.external_id for s in signals] == ["50070002", "50080001", "50060003"]

    flaky, grants, invoicing = signals
    assert flaky.source == "hn"
    assert flaky.title == "How do you deal with flaky tests in a large monorepo?"
    assert flaky.url == "https://news.ycombinator.com/item?id=50070002"
    assert flaky.published_at == datetime(2026, 10, 11, 9, 30, tzinfo=timezone.utc)
    assert flaky.category_tags == ["developer-tools"]

    assert grants.raw_text == (
        "Is there a tool for tracking which grants a lab applied to?\n\n"
        "Our lab applies to ~30 grants a year and we track them in a shared spreadsheet that"
        " nobody keeps up to date.\n\n"
        "Deadlines get missed, and we can't tell which reviewers' comments we already addressed."
        " I've looked at https://example.org/grants but it's built for big universities.\n\n"
        "What do other researchers use? Anything > a spreadsheet would help."
    )
    assert grants.category_tags == ["research-tools"]

    # Title-only post: story_text is null.
    assert invoicing.raw_text == invoicing.title
    assert invoicing.category_tags == ["fintech-alt"]


def test_default_query() -> None:
    recorder = Recorder()
    adapter, _ = make_adapter(recorder)
    adapter.fetch(SINCE)

    (request,) = recorder.requests
    assert request.url.host == "hn.algolia.com"
    assert request.url.path == "/api/v1/search_by_date"
    start = int((SINCE - timedelta(hours=48)).timestamp())
    assert request.url.params["tags"] == "ask_hn"
    assert request.url.params["numericFilters"] == f"created_at_i>={start},points>=5"
    assert request.url.params["hitsPerPage"] == str(HITS_PER_PAGE)
    assert request.url.params["page"] == "0"


def test_query_config() -> None:
    adapter, _ = make_adapter(
        Recorder(), {"story_types": ["ask_hn", "show_hn"], "min_points": 25, "lookback_hours": 0}
    )
    params = adapter.build_params(SINCE, 2)
    assert params["tags"] == "(ask_hn,show_hn)"
    assert params["numericFilters"] == f"created_at_i>={int(SINCE.timestamp())},points>=25"
    assert params["page"] == 2
    end = SINCE + WINDOW
    assert adapter.build_params(SINCE, 0, end)["numericFilters"] == (
        f"created_at_i>={int(SINCE.timestamp())},created_at_i<{int(end.timestamp())},points>=25"
    )


def test_short_range_is_one_open_window() -> None:
    adapter, _ = make_adapter(Recorder())
    assert adapter.windows(SINCE) == [(SINCE - timedelta(hours=48), None)]


def test_long_range_is_split_into_windows() -> None:
    since = NOW - timedelta(days=90)
    recorder = Recorder(lambda r: page_response([], 0, nb_pages=0))
    adapter, _ = make_adapter(recorder, {"lookback_hours": 0})
    assert adapter.windows(since) == [
        (since, since + WINDOW),
        (since + WINDOW, since + 2 * WINDOW),
        (since + 2 * WINDOW, None),
    ]
    adapter.fetch(since)
    filters = [r.url.params["numericFilters"] for r in recorder.requests]
    assert len(filters) == 3
    assert "created_at_i<" in filters[0] and "created_at_i<" in filters[1]
    assert "created_at_i<" not in filters[2]


def test_max_results_applies_per_window() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # A distinct id per window, from its start timestamp.
        start = int(request.url.params["numericFilters"].split(",")[0].split(">=")[1])
        return page_response([hit(start, points=20), hit(start + 1, points=30)], 0, nb_pages=1)

    since = NOW - timedelta(days=45)
    adapter, _ = make_adapter(Recorder(handler), {"max_results": 1, "lookback_hours": 0})
    # The 30-point post of each of the 2 windows.
    starts = [int(start.timestamp()) for start, _ in adapter.windows(since)]
    assert [s.external_id for s in adapter.fetch(since)] == [str(t + 1) for t in starts]


def test_warns_when_algolia_caps_hits(caplog: pytest.LogCaptureFixture) -> None:
    recorder = Recorder(lambda r: httpx.Response(200, json={"hits": [], "nbHits": 2500, "nbPages": 10}))
    adapter, _ = make_adapter(recorder)
    adapter.fetch(SINCE)
    assert "1000-hit cap" in caplog.text


def test_max_results_keeps_highest_points() -> None:
    adapter, _ = make_adapter(Recorder(), {"max_results": 1})
    assert [s.external_id for s in adapter.fetch(SINCE)] == ["50070002"]


def test_paginates_until_last_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return page_response([hit(page * 10 + i) for i in range(3)], page, nb_pages=3)

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder)
    signals = adapter.fetch(SINCE)
    assert [r.url.params["page"] for r in recorder.requests] == ["0", "1", "2"]
    assert len(signals) == 9


def test_stops_on_empty_page_and_at_page_budget() -> None:
    recorder = Recorder(lambda r: page_response([], 0, nb_pages=5))
    adapter, _ = make_adapter(recorder)
    assert adapter.fetch(SINCE) == []
    assert len(recorder.requests) == 1

    recorder = Recorder(lambda r: page_response([hit(1)], 0, nb_pages=50))
    adapter, _ = make_adapter(recorder)
    adapter.fetch(SINCE)
    assert len(recorder.requests) == MAX_PAGES


def test_missing_points_are_dropped() -> None:
    recorder = Recorder(lambda r: page_response([hit(1, points=None), hit(2, points=4)], 0, 1))
    adapter, _ = make_adapter(recorder)
    assert adapter.fetch(SINCE) == []


def test_retries_on_429_honouring_retry_after() -> None:
    responses = [httpx.Response(429, headers={"Retry-After": "7"})]
    recorder = Recorder(lambda r: responses.pop(0) if responses else httpx.Response(200, json=RESPONSE))
    adapter, slept = make_adapter(recorder)
    assert len(adapter.fetch(SINCE)) == 3
    assert slept == [7.0]


def test_persistent_server_error_raises() -> None:
    adapter, slept = make_adapter(Recorder(lambda r: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        adapter.fetch(SINCE)
    assert len(slept) == 3


def test_long_retry_after_fails_instead_of_hanging() -> None:
    adapter, _ = make_adapter(Recorder(lambda r: httpx.Response(429, headers={"Retry-After": "3600"})))
    with pytest.raises(RuntimeError, match="3600"):
        adapter.fetch(SINCE)


@pytest.mark.parametrize(
    "config",
    [
        {"story_types": "ask_hn"},
        {"story_types": []},
        {"story_types": ["ask_hn", "front_page"]},
        {"min_points": -1},
        {"min_points": True},
        {"lookback_hours": "48"},
        {"max_results": 0},
    ],
)
def test_rejects_bad_config(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        HnAdapter(config)


# ------------------------------------------------------------ helpers


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("one<p>two", "one\n\ntwo"),
        ("a<br>b<br/>c", "a\n\nb\n\nc"),
        ("<i>it&#x27;s</i> &lt;b&gt; &amp; &quot;q&quot;", "it's <b> & \"q\""),
        ('see <a href="https:&#x2F;&#x2F;x.io" rel="nofollow">https:&#x2F;&#x2F;x.io</a>', "see https://x.io"),
        ("<pre><code>  x = 1\n</code></pre>", "x = 1"),
        ("a<p><p>  <p>b", "a\n\nb"),
        ("", ""),
    ],
)
def test_strip_html(raw: str, expected: str) -> None:
    assert strip_html(raw) == expected


def test_map_topics() -> None:
    assert map_topics("Students skip code review") == ["developer-tools", "education"]
    assert map_topics("Of course, it depends") == []


# ------------------------------------------------------------ quality rules


def candidate(**overrides: Any) -> PostCandidate:
    fields: dict[str, Any] = {
        "title": "Is there a tool for planning volunteer shifts?",
        "text": "",
        "author": "someone",
    }
    fields.update(overrides)
    return PostCandidate(**fields)


def test_good_candidate_passes() -> None:
    assert rejection_reason(candidate()) is None


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"author": "whoishiring"}, "hiring_thread"),
        ({"title": "Who wants to be hired? (October 2026)"}, "hiring_thread"),
        ({"title": "Freelancer? Seeking Freelancer? (October 2026)"}, "hiring_thread"),
        ({"title": ""}, "empty_title"),
        ({"title": "What are you working on?"}, "no_request_phrase"),
        ({"title": "Favourite programming books?", "text": "Of course, any genre."}, "no_request_phrase"),
        # Venting and prose uses of the looser phrases.
        ({"title": "I am so tired of startups doing worse than me"}, "no_request_phrase"),
        ({"title": "IEEE news", "text": "I can't find any coverage of this."}, "no_request_phrase"),
        ({"title": "Agent swarms", "text": "I'm struggling to get 3 agents to cooperate."},
         "no_request_phrase"),
    ],
)
def test_rules_drop(overrides: dict[str, Any], reason: str) -> None:
    assert rejection_reason(candidate(**overrides)) == reason


@pytest.mark.parametrize(
    "title, text",
    [
        ("Is there a tool for converting scanned forms?", ""),
        ("Are there any good alternatives to Jira for tiny teams?", ""),
        ("How do you deal with on-call burnout?", ""),
        ("How do you keep track of receipts?", ""),
        ("I wish there was a way to mute group chats by topic", ""),
        ("Accessible maps", "Does anyone know of an app that reads bus stops aloud?"),
        ("Contract review", "I can't find any tool that flags auto-renewal clauses."),
        ("Contract review", "I can’t find any tool that flags auto-renewal clauses."),
        ("Why is there no standard format for recipes?", ""),
        ("Home energy", "I'm tired of manually checking which appliance uses the most power."),
        ("Spreadsheets", "Is there a better way to merge these every week?"),
        ("What tools do you use for meeting notes?", ""),
    ],
)
def test_request_phrases_match(title: str, text: str) -> None:
    assert candidate(title=title, text=text).request_hits >= 1


def test_rule_names_are_unique_and_phrases_compile() -> None:
    names = [name for name, _ in QUALITY_RULES]
    assert len(names) == len(set(names))
    for phrase in REQUEST_PHRASES:
        re.compile(phrase)
