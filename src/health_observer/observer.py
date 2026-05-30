"""Observer interface for embeddable HealthSync collection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .schema import Observation


@dataclass(frozen=True)
class CollectionResult:
    """Result of one observer collection pass.

    Existing providers append observations directly to the HealthSync logs. The
    counters make collection outcomes explicit without changing that
    append-to-log behavior.
    """

    observer_name: str
    collected: int = 0
    skipped: int = 0
    failed: int = 0
    message: str | None = None
    observations: tuple[Observation, ...] = ()


class Observer(Protocol):
    """A source that can collect health observations once."""

    name: str

    def collect(self) -> CollectionResult:
        """Collect new observations and return the collection result."""
