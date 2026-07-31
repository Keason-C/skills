"""The triage state machine (task T012, research R5).

The legal transitions are declared **once, as data**. Anything not in the table raises.
Terminal states map to the empty set, so re-entering one is illegal rather than a no-op.
"""

from __future__ import annotations

from collections.abc import Mapping

from .errors import IllegalTransitionError
from .models import TriageState

#: The complete transition table (FR-022). This is the only place it is expressed.
LEGAL_TRANSITIONS: Mapping[TriageState, frozenset[TriageState]] = {
    TriageState.NEW: frozenset({TriageState.ENRICHED}),
    TriageState.ENRICHED: frozenset({TriageState.CLASSIFIED}),
    TriageState.CLASSIFIED: frozenset({TriageState.AUTO_RESOLVED, TriageState.ESCALATED}),
    TriageState.AUTO_RESOLVED: frozenset(),
    TriageState.ESCALATED: frozenset(),
}


class StateMachine:
    """Tracks the current state and the path taken to reach it (FR-023, FR-024)."""

    __slots__ = ("_current", "_path")

    def __init__(self, initial: TriageState = TriageState.NEW) -> None:
        self._current = initial
        self._path: list[TriageState] = [initial]

    @property
    def current(self) -> TriageState:
        return self._current

    @property
    def path(self) -> tuple[TriageState, ...]:
        """Append-only record of every state the ticket has occupied."""
        return tuple(self._path)

    def can_advance(self, to: TriageState) -> bool:
        return to in LEGAL_TRANSITIONS[self._current]

    def advance(self, to: TriageState) -> None:
        """Move to ``to``, or raise ``IllegalTransitionError`` if the table forbids it."""
        if not self.can_advance(to):
            raise IllegalTransitionError(self._current, to)
        self._current = to
        self._path.append(to)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"StateMachine(current={self._current.value}, path={[s.value for s in self._path]})"
