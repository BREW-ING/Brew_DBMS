"""Contract every source adapter implements."""

from abc import ABC, abstractmethod
from datetime import datetime

from common.schema import ProblemSignal, Source


class BaseAdapter(ABC):
    # Which problem_signals.source this adapter produces.
    source: Source

    @abstractmethod
    def fetch(self, since: datetime) -> list[ProblemSignal]:
        """Return signals published or updated at or after `since`.

        Must not write to the database; the job upserts the results. Raise on
        failure; the job isolates each adapter so one failing source doesn't
        stop the others.
        """
        raise NotImplementedError
