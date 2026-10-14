"""arXiv adapter tests. All HTTP goes through httpx.MockTransport; no network."""

import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from adapters.arxiv_adapter import (
    MIN_ABSTRACT_CHARS,
    MIN_REQUEST_INTERVAL_S,
    PAGE_SIZE,
    PROBLEM_PHRASES,
    QUALITY_RULES,
    DOMAIN_KEYWORDS,
    ArxivAdapter,
    PaperCandidate,
    arxiv_id,
    filter_funnel,
    map_topics,
    rejection_reason,
)

FIXTURES = Path(__file__).parent / "fixtures"
FEED = (FIXTURES / "arxiv_query.atom").read_text(encoding="utf-8")
SINCE = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
PROBLEM_ABSTRACT = "Existing tools fail to help volunteers plan shifts. " * 10

Handler = Callable[[httpx.Request], httpx.Response]


def feed_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=FEED)


class Recorder:
    def __init__(self, handler: Handler = feed_response) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


class FakeClock:
    """Time only moves when the adapter sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make_adapter(
    recorder: Recorder, config: dict[str, Any] | None = None
) -> tuple[ArxivAdapter, FakeClock]:
    clock = FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(recorder))
    return ArxivAdapter(config, client=client, sleep=clock.sleep, clock=clock), clock


def entry_xml(n: int, updated: str, summary: str = PROBLEM_ABSTRACT) -> str:
    return f"""
  <entry>
    <id>http://arxiv.org/abs/2610.{n:05d}v1</id>
    <title>Paper {n}</title>
    <updated>{updated}</updated>
    <summary>{summary}</summary>
    <category term="cs.HC" scheme="http://arxiv.org/schemas/atom"/>
    <published>{updated}</published>
    <arxiv:primary_category term="cs.HC"/>
  </entry>"""


def feed_xml(entries: list[str], total: int) -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>{total}</opensearch:totalResults>
  {''.join(entries)}
</feed>"""


# ------------------------------------------------------------ end to end


def test_fetch_filters_ranks_and_tags() -> None:
    adapter, _ = make_adapter(Recorder())
    signals = adapter.fetch(SINCE)

    # 3 of the 11 in-window entries pass; ranked by problem-phrase hits. Every
    # category returns the same feed, so cross-listed papers are deduped.
    assert [s.external_id for s in signals] == ["2610.01111", "cs/0601001", "2610.02222"]

    dashboards, forms, bots = signals
    assert dashboards.source == "arxiv"
    assert dashboards.title == "Screen Reader Navigation of Data Dashboards: A Study with Blind Analysts"
    assert dashboards.url == "https://arxiv.org/abs/2610.01111"
    assert dashboards.published_at == datetime(2026, 10, 14, 9, 12, tzinfo=timezone.utc)
    assert dashboards.category_tags == ["accessibility"]
    assert dashboards.raw_text.startswith(dashboards.title + "\n\nInteractive dashboards have")
    assert "\n  " not in dashboards.raw_text  # feed line wrapping collapsed

    # Version suffix stripped; published_at is the v1 date, not the revision.
    assert bots.url == "https://arxiv.org/abs/2610.02222"
    assert bots.published_at == datetime(2026, 9, 30, 11, 0, tzinfo=timezone.utc)
    assert bots.category_tags == ["developer-tools"]
    assert forms.category_tags == ["civic-tech"]


def test_default_queries_and_throttling() -> None:
    recorder = Recorder()
    adapter, clock = make_adapter(recorder)
    adapter.fetch(SINCE)

    # The fixture's last entry predates SINCE, so each category needs one page.
    assert [r.url.params["search_query"] for r in recorder.requests] == [
        "cat:cs.HC", "cat:cs.CY", "cat:cs.SE", "cat:cs.SI", "cat:cs.CL",
    ]
    params = recorder.requests[0].url.params
    assert recorder.requests[0].url.host == "export.arxiv.org"
    assert params["sortBy"] == "lastUpdatedDate"
    assert params["sortOrder"] == "descending"
    assert params["start"] == "0"
    assert params["max_results"] == str(PAGE_SIZE)
    # No wait before the first request, at least 3 s before each after it.
    assert clock.slept == [MIN_REQUEST_INTERVAL_S] * 4


def test_logs_counts_before_and_after_each_rule(caplog: pytest.LogCaptureFixture) -> None:
    adapter, _ = make_adapter(Recorder())
    with caplog.at_level(logging.INFO, logger="adapters.arxiv_adapter"):
        adapter.fetch(SINCE)
    lines = [r.getMessage() for r in caplog.records]
    # 5 categories x 11 in-window entries; 4 repeats of each are duplicates.
    assert "arXiv: 55 entries in window across 5 categories, 44 cross-listed duplicates,"         " 11 papers to filter" in lines
    funnel = [re.sub(r"\s+", " ", line) for line in lines if line.startswith("arXiv filter")]
    assert funnel == [
        "arXiv filter excluded_primary 11 -> 10",
        "arXiv filter withdrawn 10 -> 9",
        "arXiv filter not_a_paper 9 -> 8",
        "arXiv filter model_name_title 8 -> 7",
        "arXiv filter theory_title 7 -> 6",
        "arXiv filter short_abstract 6 -> 5",
        "arXiv filter no_domain_keyword 5 -> 4",
        "arXiv filter no_problem_statement 4 -> 3",
    ]
    assert "arXiv: 3 passed all rules, keeping 3 (max_results=200)" in lines


def test_filter_funnel_follows_rule_order() -> None:
    funnel = filter_funnel(10, {"theory_title": 4, "no_problem_statement": 1})
    assert [name for name, _, _ in funnel] == [name for name, _ in QUALITY_RULES]
    assert funnel[0] == ("excluded_primary", 10, 10)
    assert ("theory_title", 10, 6) in funnel
    assert funnel[-1] == ("no_problem_statement", 6, 5)


def test_categories_from_config() -> None:
    recorder = Recorder()
    adapter, _ = make_adapter(recorder, {"categories": ["cs.CR", "cs.CR"], "max_results": 1})
    signals = adapter.fetch(SINCE)
    assert [r.url.params["search_query"] for r in recorder.requests] == ["cat:cs.CR"]
    assert [s.external_id for s in signals] == ["2610.01111"]


def test_paginates_until_entries_predate_since() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        if start == 0:
            entries = [entry_xml(i, "2026-10-10T00:00:00Z") for i in range(PAGE_SIZE)]
        else:
            entries = [entry_xml(500, "2026-10-09T00:00:00Z"), entry_xml(501, "2026-10-01T00:00:00Z")]
        return httpx.Response(200, text=feed_xml(entries, total=10_000))

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder, {"categories": ["cs.HC"]})
    signals = adapter.fetch(SINCE)
    assert [r.url.params["start"] for r in recorder.requests] == ["0", str(PAGE_SIZE)]
    assert len(signals) == PAGE_SIZE + 1
    assert "2610.00501" not in {s.external_id for s in signals}


def test_stops_at_page_budget() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        entries = [entry_xml(start + i, "2026-10-10T00:00:00Z") for i in range(PAGE_SIZE)]
        return httpx.Response(200, text=feed_xml(entries, total=10_000))

    recorder = Recorder(handler)
    adapter, _ = make_adapter(recorder, {"categories": ["cs.HC"], "max_results": 1000})
    adapter.fetch(SINCE)
    assert len(recorder.requests) == 3


def test_api_error_feed_raises() -> None:
    error_feed = feed_xml(
        ["""<entry><id>https://arxiv.org/api/errors#bad_query</id><title>Error</title>
        <summary>malformed query</summary></entry>"""],
        total=1,
    )
    adapter, _ = make_adapter(Recorder(lambda r: httpx.Response(400, text=error_feed)))
    with pytest.raises(RuntimeError, match="malformed query"):
        adapter.fetch(SINCE)


def test_retries_on_503_honouring_retry_after() -> None:
    responses = [httpx.Response(503, headers={"Retry-After": "20"}), httpx.Response(200, text=FEED)]
    recorder = Recorder(lambda r: responses.pop(0) if responses else httpx.Response(200, text=FEED))
    adapter, clock = make_adapter(recorder, {"categories": ["cs.HC"]})
    assert len(adapter.fetch(SINCE)) == 3
    assert clock.slept == [20.0]  # the retry wait already exceeds the 3 s gap


def test_persistent_server_error_raises() -> None:
    adapter, _ = make_adapter(Recorder(lambda r: httpx.Response(500)), {"categories": ["cs.HC"]})
    with pytest.raises(httpx.HTTPStatusError):
        adapter.fetch(SINCE)


@pytest.mark.parametrize(
    "config",
    [
        {"categories": "cs.HC"},
        {"categories": []},
        {"categories": ["cat:cs.HC OR all:x"]},
        {"max_results": 0},
        {"max_results": True},
    ],
)
def test_rejects_bad_config(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ArxivAdapter(config)


# ------------------------------------------------------------ helpers


@pytest.mark.parametrize(
    "entry_id, expected",
    [
        ("http://arxiv.org/abs/2610.01234v2", "2610.01234"),
        ("http://arxiv.org/abs/2610.01234", "2610.01234"),
        ("http://arxiv.org/abs/hep-th/9901001v1", "hep-th/9901001"),
    ],
)
def test_arxiv_id_strips_version(entry_id: str, expected: str) -> None:
    assert arxiv_id(entry_id) == expected


def test_map_topics_combines_categories_and_keywords() -> None:
    assert map_topics(["cs.SE", "cs.CY"], "Tutoring students about floods") == [
        "developer-tools", "civic-tech", "education", "climate",
    ]
    # Domain keywords without a topic count for the rule but add no tag.
    assert map_topics(["cs.HC"], "Farmers in rural areas") == []
    assert map_topics(["cs.CV"], "Object detection on a new benchmark") == []


# ------------------------------------------------------------ quality rules


def candidate(**overrides: Any) -> PaperCandidate:
    fields: dict[str, Any] = {
        "title": "A study of shift planning",
        "abstract": PROBLEM_ABSTRACT,
        "primary_category": "cs.HC",
    }
    fields.update(overrides)
    return PaperCandidate(**fields)


def test_good_candidate_passes() -> None:
    assert rejection_reason(candidate()) is None


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"primary_category": "cs.LG"}, "excluded_primary"),
        ({"primary_category": "cs.CV"}, "excluded_primary"),
        ({"primary_category": "math.OC"}, "excluded_primary"),
        ({"abstract": "This paper has been withdrawn. " + PROBLEM_ABSTRACT}, "withdrawn"),
        ({"title": "Corrigendum to: shift planning"}, "not_a_paper"),
        ({"abstract": "Existing tools fail. " * ((MIN_ABSTRACT_CHARS - 1) // 21)}, "short_abstract"),
        ({"abstract": "We present a fast new method and report strong results. " * 10},
         "no_domain_keyword"),
        ({"abstract": "We built a scheduling app for volunteers and report usage. " * 10},
         "no_problem_statement"),
        # Problem phrases only count in the abstract.
        ({"title": "Planning remains challenging",
          "abstract": "We built a scheduling app for volunteers and report usage. " * 10},
         "no_problem_statement"),
    ],
)
def test_rules_drop(overrides: dict[str, Any], reason: str) -> None:
    assert rejection_reason(candidate(**overrides)) == reason


@pytest.mark.parametrize(
    "title, reason",
    [
        ("HybridDualPathNet: Cross-Fusion Attention of EfficientNetV2 and Swin", "model_name_title"),
        ("FlowBook: Enforcing Reproducibility in Notebooks", "model_name_title"),
        ("DTScribe: Generating Reports with Local Models", "model_name_title"),
        ("Llama3: Lessons for Clinics", "model_name_title"),
        ("REINS: Agent-guided Thread Scheduling", "model_name_title"),
        ("Improving Triage with a Lightweight SwinFormer", "model_name_title"),
        ("On Collision-Free Teaching in Planar Graphs", "theory_title"),
        ("Tight Lower Bounds for Fair Allocation", "theory_title"),
        ("Convergence of Peer Grading Schemes", "theory_title"),
        # Real tools and acronyms are fine.
        ("How Students Use ChatGPT for Homework", None),
        ("Why Maintainers Close Issues on GitHub", None),
        ("COVID-19: Lessons for Rural Clinics", None),
        ("LLMs in Classrooms: A Teacher Survey", None),
        ("mHealth Apps for Older Adults", None),
        ("Online Harassment of Journalists", None),
    ],
)
def test_title_rules(title: str, reason: str | None) -> None:
    assert rejection_reason(candidate(title=title)) == reason


@pytest.mark.parametrize(
    "text",
    [
        "We compare two model families on reasoning tasks.",
        "Flooding the context with retrieved passages hurts accuracy.",
        "A patient attacker can wait for the monitor to drift.",
    ],
)
def test_figurative_uses_are_not_domains(text: str) -> None:
    assert candidate(abstract=text, title="x").domain_hits == 0


def test_distillation_teacher_student_is_not_a_domain() -> None:
    abstract = "We distil a teacher model into a student model; the student network is small."
    assert candidate(abstract=abstract, title="x").domain_hits == 0
    assert candidate(abstract="Teachers grade essays by hand.", title="x").domain_hits == 1


@pytest.mark.parametrize(
    "sentence",
    [
        "Robust gaze tracking remains challenging on phones.",
        "There is a lack of labelled data for these dialects.",
        "Existing tools fail when documents mix scripts.",
        "Whether this transfers is an open question.",
        "Manual triage is time-consuming and error-prone.",
        "Little is known about how nurses use these alerts.",
        "Cost is a major barrier to adoption.",
    ],
)
def test_problem_phrases_match(sentence: str) -> None:
    filler = " We study this in detail across several settings." * 8
    assert candidate(abstract=sentence + filler).problem_hits >= 1


@pytest.mark.parametrize("word", ["black", "blacks", "slack", "openness"])
def test_problem_phrases_respect_word_boundaries(word: str) -> None:
    assert candidate(abstract=f"The {word} box.", title="x").problem_hits == 0


def test_rule_names_are_unique_and_patterns_compile() -> None:
    names = [name for name, _ in QUALITY_RULES]
    assert len(names) == len(set(names))
    for phrase in PROBLEM_PHRASES:
        re.compile(phrase)
    for _, pattern in DOMAIN_KEYWORDS:
        re.compile(pattern)
