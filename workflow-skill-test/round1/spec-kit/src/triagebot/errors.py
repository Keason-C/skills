"""Exception hierarchy for TriageBot (task T005)."""

from __future__ import annotations


class TriageError(Exception):
    """Base class for every error raised by TriageBot itself.

    Input validation problems are *not* raised as ``TriageError`` -- they surface as
    ``pydantic.ValidationError`` at the model boundary (FR-001..FR-004).
    """


class IllegalTransitionError(TriageError):
    """Raised when a ticket is moved between states in an order the model forbids (FR-023).

    This always indicates a programming error, never bad ticket data.
    """

    def __init__(self, current: object, requested: object) -> None:
        self.current = current
        self.requested = requested
        super().__init__(f"illegal state transition: {current} -> {requested}")


class DriverError(TriageError):
    """Raised when an LLM driver cannot produce a usable proposal."""
