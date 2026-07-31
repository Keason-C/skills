"""Explicit triage state machine.

The lifecycle of a ticket is a small, closed graph. Making it explicit means an
illegal transition is a raised exception rather than a silently wrong result.
"""

from __future__ import annotations

from enum import Enum


class TriageState(str, Enum):
    NEW = "NEW"
    ENRICHED = "ENRICHED"
    CLASSIFIED = "CLASSIFIED"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    ESCALATED = "ESCALATED"


TERMINAL_STATES: frozenset[TriageState] = frozenset(
    {TriageState.AUTO_RESOLVED, TriageState.ESCALATED}
)

LEGAL_TRANSITIONS: dict[TriageState, frozenset[TriageState]] = {
    TriageState.NEW: frozenset({TriageState.ENRICHED}),
    TriageState.ENRICHED: frozenset({TriageState.CLASSIFIED}),
    TriageState.CLASSIFIED: frozenset({TriageState.AUTO_RESOLVED, TriageState.ESCALATED}),
    TriageState.AUTO_RESOLVED: frozenset(),
    TriageState.ESCALATED: frozenset(),
}


class IllegalTransitionError(Exception):
    """Raised when a caller attempts a transition the lifecycle forbids."""


class TriageStateMachine:
    """Tracks where a ticket is in its lifecycle and refuses illegal moves."""

    def __init__(self, initial: TriageState = TriageState.NEW) -> None:
        self._state = initial
        self._history: list[TriageState] = [initial]

    @property
    def state(self) -> TriageState:
        return self._state

    @property
    def history(self) -> tuple[TriageState, ...]:
        return tuple(self._history)

    def transition_to(self, next_state: TriageState) -> None:
        if next_state not in LEGAL_TRANSITIONS[self._state]:
            raise IllegalTransitionError(
                f"{self._state.value} -> {next_state.value} is not a legal transition"
            )
        self._state = next_state
        self._history.append(next_state)
