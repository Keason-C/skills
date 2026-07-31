"""The one function callers learn: a Ticket goes in, a Verdict comes out.

Everything else in the package is behind this seam — the stage machine, the tool lookups, the
injection scan, the Driver calls and the Guard chain. Dependencies are accepted, never
constructed here (the default Tools adapter is the shipped fixture one, resolved at call time).
"""

from __future__ import annotations

from triagebot.drivers.base import LLMDriver
from triagebot.guards import CONFIDENCE_THRESHOLD, adjudicate
from triagebot.injection import scan_for_injection
from triagebot.models import Ticket, TriageResult
from triagebot.stages import TriageStage, advance
from triagebot.tools import FixtureTools, Tools, gather_context


def triage_ticket(
    ticket: Ticket,
    driver: LLMDriver,
    tools: Tools | None = None,
) -> TriageResult:
    """Triage one Ticket, returning the rules-approved Verdict."""
    tools = tools if tools is not None else FixtureTools()

    stage = advance(TriageStage.NEW, TriageStage.ENRICHED)
    context = gather_context(ticket, tools)

    # The Driver only ever sees redacted text, so instruction-like content cannot influence it.
    injection = scan_for_injection(ticket.subject, ticket.body)
    redacted = ticket.model_copy(
        update={"subject": injection.redacted_subject, "body": injection.redacted_body}
    )

    # ADR-0002: the first pass is deliberately context-free, so the retry has something to add.
    suggestion = driver.suggest(redacted, None)
    if suggestion.confidence < CONFIDENCE_THRESHOLD:
        suggestion = driver.suggest(redacted, context)
    advance(stage, TriageStage.CLASSIFIED)

    return adjudicate(ticket, suggestion, context, injection)
