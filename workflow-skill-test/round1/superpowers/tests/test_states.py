import pytest

from triagebot.states import IllegalTransitionError, TriageState, TriageStateMachine


def test_happy_path_reaches_auto_resolved():
    m = TriageStateMachine()
    m.transition_to(TriageState.ENRICHED)
    m.transition_to(TriageState.CLASSIFIED)
    m.transition_to(TriageState.AUTO_RESOLVED)
    assert m.state is TriageState.AUTO_RESOLVED


def test_classified_may_go_to_escalated():
    m = TriageStateMachine()
    m.transition_to(TriageState.ENRICHED)
    m.transition_to(TriageState.CLASSIFIED)
    m.transition_to(TriageState.ESCALATED)
    assert m.state is TriageState.ESCALATED


def test_skipping_enriched_is_rejected():
    m = TriageStateMachine()
    with pytest.raises(IllegalTransitionError):
        m.transition_to(TriageState.CLASSIFIED)


def test_terminal_state_has_no_outgoing_transition():
    m = TriageStateMachine()
    m.transition_to(TriageState.ENRICHED)
    m.transition_to(TriageState.CLASSIFIED)
    m.transition_to(TriageState.ESCALATED)
    with pytest.raises(IllegalTransitionError):
        m.transition_to(TriageState.AUTO_RESOLVED)


def test_repeating_a_transition_is_rejected():
    m = TriageStateMachine()
    m.transition_to(TriageState.ENRICHED)
    with pytest.raises(IllegalTransitionError):
        m.transition_to(TriageState.ENRICHED)


def test_backwards_transition_is_rejected():
    m = TriageStateMachine()
    m.transition_to(TriageState.ENRICHED)
    with pytest.raises(IllegalTransitionError):
        m.transition_to(TriageState.NEW)


def test_history_records_every_visited_state():
    m = TriageStateMachine()
    m.transition_to(TriageState.ENRICHED)
    m.transition_to(TriageState.CLASSIFIED)
    assert m.history == (TriageState.NEW, TriageState.ENRICHED, TriageState.CLASSIFIED)


def test_illegal_transition_leaves_state_unchanged():
    m = TriageStateMachine()
    with pytest.raises(IllegalTransitionError):
        m.transition_to(TriageState.AUTO_RESOLVED)
    assert m.state is TriageState.NEW
