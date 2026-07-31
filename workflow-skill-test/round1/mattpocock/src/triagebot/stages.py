"""The Triage Stage machine.

Advancing is a function over a transition table, not a setter. There is no way to put a Ticket
into a stage it has not legally reached — an illegal advance is rejected, never corrected.
"""

from __future__ import annotations

from enum import Enum


class TriageStage(str, Enum):
    """Where a Ticket has got to."""

    NEW = "NEW"
    ENRICHED = "ENRICHED"
    CLASSIFIED = "CLASSIFIED"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    ESCALATED = "ESCALATED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL


_TERMINAL: frozenset[TriageStage] = frozenset(
    {TriageStage.AUTO_RESOLVED, TriageStage.ESCALATED}
)

_TRANSITIONS: dict[TriageStage, frozenset[TriageStage]] = {
    TriageStage.NEW: frozenset({TriageStage.ENRICHED}),
    TriageStage.ENRICHED: frozenset({TriageStage.CLASSIFIED}),
    TriageStage.CLASSIFIED: frozenset({TriageStage.AUTO_RESOLVED, TriageStage.ESCALATED}),
    TriageStage.AUTO_RESOLVED: frozenset(),
    TriageStage.ESCALATED: frozenset(),
}


class IllegalStageTransition(Exception):
    """Raised when a Ticket is asked to move somewhere the machine does not allow."""

    def __init__(self, current: TriageStage, target: TriageStage) -> None:
        allowed = sorted(stage.value for stage in _TRANSITIONS[current])
        super().__init__(
            f"cannot advance from {current.value} to {target.value}; "
            f"allowed from {current.value}: {allowed or 'nothing (terminal)'}"
        )
        self.current = current
        self.target = target


def advance(current: TriageStage, target: TriageStage) -> TriageStage:
    """Return `target` if the machine permits the move, otherwise raise."""
    if target not in _TRANSITIONS[current]:
        raise IllegalStageTransition(current, target)
    return target
