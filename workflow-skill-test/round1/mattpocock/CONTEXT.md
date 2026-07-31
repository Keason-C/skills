# TriageBot

The context that decides what happens to an inbound customer-support ticket. An LLM reads the
ticket and *suggests*; deterministic rules *decide*. Nothing the LLM emits reaches the outside
world without passing the rules.

## Language

### The work item

**Ticket**:
One inbound customer-support request, as received. Immutable once accepted.
_Avoid_: case, issue, request, complaint.

**Triage**:
The act of turning one Ticket into one Verdict.
_Avoid_: classification (that is only the first half), routing, handling.

**Verdict**:
The final, rules-approved decision about a Ticket — category, priority, sentiment, action,
escalation flag, rationale. The only thing callers are allowed to act on. Carried by the
`TriageResult` type.
_Avoid_: result, output, response, decision object.

**Suggestion**:
What a Driver returns — an *unapproved* opinion about a Ticket. Never authoritative; every
field of it may be overruled by a Guard.
_Avoid_: prediction, classification, LLM output, answer.

### What a Verdict says

**Category**:
What kind of problem the Ticket is about: `BILLING`, `REFUND`, `TECHNICAL`, `ACCOUNT`, `OTHER`.
`OTHER` is the honest "we don't know" value, not a dumping ground — it is never auto-resolved.
_Avoid_: type, topic, intent, class.

**Priority**:
How urgently a human should get to the Ticket. `P0_URGENT` = service unavailable or a security
event; `P1_HIGH` = a core user action is blocked; `P2_NORMAL` = an ordinary problem; `P3_LOW` = a
question or a suggestion. Always computed by Guards, never taken from a Suggestion.
_Avoid_: severity, urgency, importance.

**Sentiment**:
How the customer sounds: `ANGRY`, `FRUSTRATED`, `NEUTRAL`, `SATISFIED`.
_Avoid_: mood, tone, emotion, POSITIVE (the fourth value is `SATISFIED`).

**Action**:
The single next step a Verdict recommends, drawn from a closed set. Never free text — free text
cannot be checked against a Policy Entry.
_Avoid_: recommendation, next step, resolution, disposition.

### The decision machinery

**Driver**:
The swappable thing that turns a Ticket (plus optionally Tool Context) into a Suggestion.
`MockDriver` is deterministic and used by every test; `AnthropicDriver` calls Claude.
_Avoid_: model, client, LLM, provider, backend.

**Guard**:
A pure deterministic rule that inspects a Suggestion and may overrule it. Guards run in a fixed
order, cannot call out to anything, and always win against the Suggestion.
_Avoid_: validator, policy check, rule engine, filter.

**Tool Context**:
The facts gathered from local tools before classification — order status, refund policy entries.
Read-only, fetched once per Ticket.
_Avoid_: enrichment data, RAG context, retrieval.

**Policy Entry**:
One row of the refund policy: what a given Category permits, and the single Action that follows
from it. The only source of truth for what a REFUND Ticket may be told.
_Avoid_: rule, policy record, refund rule.

**Escalation**:
Handing a Ticket to a human. Terminal. Once a Ticket is escalated, no later rule may un-escalate
it.
_Avoid_: handoff, hand-off to agent, raise, elevate.

**Auto-resolution**:
Closing a Ticket with a machine-chosen Action and no human in the loop. The only alternative
terminal outcome to Escalation.
_Avoid_: auto-close, self-serve, resolution.

**Injection Attempt**:
Text inside a Ticket's body that tries to address the triage system rather than describe a
customer problem. Detected deterministically, recorded on the Verdict, and never permitted to
change any other field.
_Avoid_: prompt hack, jailbreak, adversarial input, attack.

### Ticket lifecycle

**Triage Stage**:
Where a Ticket has got to: `NEW` → `ENRICHED` → `CLASSIFIED` → `AUTO_RESOLVED` | `ESCALATED`.
Advancing out of order is rejected, not corrected.
_Avoid_: state, status, phase, step (in code, `TriageStage`; a Ticket's own `status` word is
reserved for order status).
