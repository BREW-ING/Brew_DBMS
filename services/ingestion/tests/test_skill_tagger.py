"""Keyword skill rules and how the tagger merges them with semantic matches. No model download."""

import re

import pytest

from common.skill_tagger import KEYWORD_CONFIDENCE, SkillTagger, keyword_skills
from common.skills_data import SKILLS

# skills seeded by db/postgres/schema.sql; each needs tagging data.
SEEDED_SKILLS = [
    "javascript", "typescript", "python", "react", "nextjs",
    "machine-learning", "computer-vision", "nlp", "postgresql",
    "neo4j", "vector-search", "ui-design", "mobile", "devops",
    "rust", "go", "data-engineering", "geospatial", "iot", "llm",
]  # fmt: skip


def test_every_seeded_skill_has_data() -> None:
    assert sorted(SKILLS) == sorted(SEEDED_SKILLS)
    for name, info in SKILLS.items():
        assert info.description and info.keywords, name
        for pattern in info.keywords:
            re.compile(pattern)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Migrate the dashboard to Next.js app router", {"nextjs"}),
        ("useEffect fires twice in a React component", {"react"}),
        ("Add pgvector similarity search to Postgres", {"postgresql", "vector-search"}),
        ("Write a Cypher query for Neo4j", {"neo4j"}),
        ("Flutter app crashes on iOS 18", {"mobile"}),
        ("Fine-tuning a PyTorch model for OCR", {"machine-learning", "computer-vision"}),
        ("RAG pipeline over LLM outputs with LangChain", {"llm"}),
        ("Kafka to BigQuery ETL keeps dropping rows", {"data-engineering"}),
        ("Goroutine leak in a Golang service", {"go"}),
        ("Arduino reading MQTT sensor data", {"iot"}),
        ("Render GeoJSON layers with Leaflet", {"geospatial"}),
        ("Dockerfile for the GitHub Actions runner", {"devops"}),
        ("TYPESCRIPT strict mode errors", {"typescript"}),  # case-insensitive
    ],
)
def test_keyword_matches(text: str, expected: set[str]) -> None:
    assert keyword_skills(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "How do users react when an app asks for location?",  # 'react' the verb
        "I want to go to a meetup about climate",  # 'go' the verb
        "Fetch the latest postings",  # 'postgres' must not match inside words
        "Nextjsfoo is not a framework",  # word boundary on next.js
        "Their ragtag team shipped it",  # 'rag' inside a word
    ],
)
def test_no_false_positives(text: str) -> None:
    assert keyword_skills(text) == set()


def fake_embed(texts: list[str]) -> list[list[float]]:
    """One-hot per description, so a signal's embedding picks skills directly."""
    return [[1.0 if i == j else 0.0 for j in range(len(texts))] for i in range(len(texts))]


def test_keyword_beats_weaker_semantic_match() -> None:
    tagger = SkillTagger(["python", "rust"], fake_embed)
    # python matches by keyword (0.9) and weakly by similarity; rust by similarity only.
    tags = dict(tagger.tag("A python script", [0.4, 0.8]))
    assert tags["python"] == KEYWORD_CONFIDENCE
    assert tags["rust"] == pytest.approx(0.8 / (0.4**2 + 0.8**2) ** 0.5)


def test_semantic_below_threshold_is_dropped() -> None:
    tagger = SkillTagger(["python", "rust"], fake_embed, threshold=0.35)
    assert tagger.tag("nothing relevant", [1.0, 0.1]) == [("python", pytest.approx(0.995, abs=1e-3))]


def test_caps_at_max_skills_highest_first() -> None:
    names = ["python", "rust", "go", "react", "nlp", "iot", "llm"]
    tagger = SkillTagger(names, fake_embed)
    tags = tagger.tag("python rust golang", [0.1] * len(names))  # semantic sims all ~0.38
    assert len(tags) == 5
    assert [n for n, _ in tags[:3]] == ["go", "python", "rust"]
    assert [c for _, c in tags] == sorted((c for _, c in tags), reverse=True)


def test_unknown_skill_rejected() -> None:
    with pytest.raises(ValueError, match="cobol"):
        SkillTagger(["cobol"], fake_embed)
