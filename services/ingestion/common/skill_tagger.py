"""Tag a signal with the skills it needs, for signal_skills.

Two sources of evidence, merged per skill (highest confidence wins):
  a) keyword rules from skills_data -> KEYWORD_CONFIDENCE
  b) cosine similarity between the signal embedding and each skill
     description's embedding -> the similarity itself, if >= threshold
At most MAX_SKILLS per signal, highest confidence first.
"""

import re
from collections.abc import Callable, Mapping

import numpy as np

from common.skills_data import SKILLS, SkillInfo

KEYWORD_CONFIDENCE = 0.9
DEFAULT_THRESHOLD = 0.35
MAX_SKILLS = 5


def compile_rules(skills: Mapping[str, SkillInfo] = SKILLS) -> dict[str, re.Pattern[str]]:
    """One case-insensitive alternation per skill."""
    return {
        name: re.compile("|".join(f"(?:{k})" for k in info.keywords), re.IGNORECASE)
        for name, info in skills.items()
    }


_RULES = compile_rules()


def keyword_skills(text: str, rules: Mapping[str, re.Pattern[str]] = _RULES) -> set[str]:
    """Skill names whose keyword rules match `text`."""
    return {name for name, pattern in rules.items() if pattern.search(text)}


def _unit_rows(vectors: list[list[float]]) -> np.ndarray:
    m = np.asarray(vectors, dtype=np.float32).reshape(len(vectors), -1)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


class SkillTagger:
    """Built once per job run: embeds the skill descriptions up front."""

    def __init__(
        self,
        skill_names: list[str],
        embed: Callable[[list[str]], list[list[float]]],
        threshold: float = DEFAULT_THRESHOLD,
        max_skills: int = MAX_SKILLS,
    ) -> None:
        unknown = [n for n in skill_names if n not in SKILLS]
        if unknown:
            raise ValueError(f"no entry in skills_data.SKILLS for: {', '.join(unknown)}")
        self.names = list(skill_names)
        self.threshold = threshold
        self.max_skills = max_skills
        self._rules = {n: _RULES[n] for n in self.names}
        descriptions = [SKILLS[n].description for n in self.names]
        self._desc = _unit_rows(embed(descriptions)) if self.names else np.zeros((0, 0))

    def tag(self, text: str, embedding: list[float]) -> list[tuple[str, float]]:
        """(skill name, confidence) pairs, highest confidence first."""
        scores: dict[str, float] = {n: KEYWORD_CONFIDENCE for n in keyword_skills(text, self._rules)}
        if self.names:
            sims = self._desc @ _unit_rows([embedding])[0]
            for name, sim in zip(self.names, sims.tolist()):
                if sim >= self.threshold and sim > scores.get(name, 0.0):
                    scores[name] = min(sim, 1.0)  # float rounding can nudge past 1
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[: self.max_skills]
