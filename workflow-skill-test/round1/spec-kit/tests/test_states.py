"""State machine -- scenario V21 (task T025).

FR-023: an illegal transition must be rejected outright, never logged-and-ignored or
silently repaired.
"""

from __future__ import annotations

import pytest

from triagebot import IllegalTransitionError, StateMachine, TriageState
from triagebot.states import LEGAL_TRANSITIONS

LEGAL_PAIRS = [
    (TriageState.NEW, TriageState.ENRICHED),
    (TriageState.ENRICHED, TriageState.CLASSIFIED),
    (TriageState.CLASSIFIED, TriageState.AUTO_RESOLVED),
    (TriageState.CLASSIFIED, TriageState.ESCALATED),
]

ILLEGAL_PAIRS = [
    # Skipping enrichment: the classifier would run without tool context.
    (TriageState.NEW, TriageState.CLASSIFIED),
    (TriageState.NEW, TriageState.AUTO_RESOLVED),
    (TriageState.NEW, TriageState.ESCALATED),
    (TriageState.NEW, TriageState.NEW),
    # Going backwards.
    (TriageState.ENRICHED, TriageState.NEW),
    (TriageState.CLASSIFIED, TriageState.ENRICHED),
    # Re-deciding after a terminal verdict.
    (TriageState.ESCALATED, TriageState.AUTO_RESOLVED),
    (TriageState.AUTO_RESOLVED, TriageState.ESCALATED),
    # Re-entering a terminal state.
    (TriageState.AUTO_RESOLVED, TriageState.AUTO_RESOLVED),
    (TriageState.ESCALATED, TriageState.ESCALATED),
]


def test_starts_at_new() -> None:
    machine = StateMachine()
    assert machine.current is TriageState.NEW
    assert machine.path == (TriageState.NEW,)


@pytest.mark.parametrize(("start", "target"), LEGAL_PAIRS)
def test_legal_transitions_succeed(start: TriageState, target: TriageState) -> None:
    machine = StateMachine(initial=start)
    machine.advance(target)
    assert machine.current is target


@pytest.mark.parametrize(("start", "target"), ILLEGAL_PAIRS)
def test_illegal_transitions_raise(start: TriageState, target: TriageState) -> None:
    machine = StateMachine(initial=start)
    with pytest.raises(IllegalTransitionError):
        machine.advance(target)


def test_illegal_transition_leaves_state_untouched() -> None:
    """Rejection must not half-apply: a failed advance changes nothing."""
    machine = StateMachine()
    with pytest.raises(IllegalTransitionError):
        machine.advance(TriageState.CLASSIFIED)
    assert machine.current is TriageState.NEW
    assert machine.path == (TriageState.NEW,)


def test_path_records_every_state() -> None:
    machine = StateMachine()
    machine.advance(TriageState.ENRICHED)
    machine.advance(TriageState.CLASSIFIED)
    machine.advance(TriageState.ESCALATED)
    assert machine.path == (
        TriageState.NEW,
        TriageState.ENRICHED,
        TriageState.CLASSIFIED,
        TriageState.ESCALATED,
    )


def test_error_names_both_states() -> None:
    machine = StateMachine()
    with pytest.raises(IllegalTransitionError) as exc:
        machine.advance(TriageState.ESCALATED)
    assert exc.value.current is TriageState.NEW
    assert exc.value.requested is TriageState.ESCALATED


def test_transition_table_covers_every_state() -> None:
    """A state missing from the table would raise KeyError instead of a clear error."""
    assert set(LEGAL_TRANSITIONS) == set(TriageState)


def test_terminal_states_have_no_successors() -> None:
    assert LEGAL_TRANSITIONS[TriageState.AUTO_RESOLVED] == frozenset()
    assert LEGAL_TRANSITIONS[TriageState.ESCALATED] == frozenset()
