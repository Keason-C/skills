# Contracts: TriageBot

Three external surfaces. Everything else is internal and may change without notice.

---

## 1. Python library API

```python
from triagebot import TriageSettings, Ticket, TriageResult, triage
from triagebot.drivers import MockDriver

result: TriageResult = triage(
    ticket: Ticket,
    driver: LLMDriver = MockDriver(),
    settings: TriageSettings = TriageSettings(),
)
```

**Guarantees**

- Raises `pydantic.ValidationError` for any invalid `Ticket` — before any driver call.
- Raises `IllegalTransitionError` only for programming errors, never for bad ticket data.
- Never performs network I/O when given a `MockDriver`.
- Pure with respect to the driver: same ticket + same driver responses → identical result.
- Calls `driver.classify` at most twice.

**`LLMDriver` protocol**

```python
class LLMDriver(Protocol):
    def classify(
        self, ticket: Ticket, context: ToolContext | None
    ) -> ClassificationProposal: ...
```

`context` is `None` on the first call and populated on the retry (FR-013). A driver MUST NOT be
relied on for any guarantee — the pipeline validates and overrides everything it returns.

---

## 2. Result JSON — the Python↔TypeScript contract

Generated, never hand-written:

```bash
python -m triagebot.schema_export --out schema/
# writes schema/triage_result.schema.json and schema/ticket.schema.json
```

The generated `schema/triage_result.schema.json` is the single source of truth. The TypeScript zod
schema is generated **from it** (`ts/scripts/generate-zod.mjs` → `ts/src/schema.generated.ts`) and a
test fails the build if the committed file is stale.

Example instance (shape only; values illustrative):

```json
{
  "ticket_id": "T-1001",
  "category": "TECHNICAL",
  "priority": "P2",
  "sentiment": "FRUSTRATED",
  "confidence": 0.82,
  "recommended_action": "INVESTIGATE_TECHNICAL",
  "escalated_to_human": false,
  "rationale": "…",
  "injection_detected": false,
  "language": "EN",
  "state": "AUTO_RESOLVED",
  "state_path": ["NEW", "ENRICHED", "CLASSIFIED", "AUTO_RESOLVED"],
  "guard_findings": [],
  "retried": false,
  "llm_calls": 1
}
```

**Compatibility rule**: adding a required field or removing an enum member is a breaking change to
this contract and requires regenerating both artifacts in the same change.

---

## 3. Command-line surfaces

### Python — produce a result

```bash
python -m triagebot.cli --ticket <ticket.json> [--out <result.json>] [--pretty]
```

| Exit code | Meaning |
|-----------|---------|
| `0` | Ticket triaged; result written |
| `2` | Ticket failed validation; field-level errors on stderr; nothing written |
| `1` | Unexpected internal error |

Writes the result JSON to `--out`, or stdout when omitted. Never contacts the network: the CLI uses
`MockDriver` unless `--driver anthropic` is passed explicitly.

### TypeScript — validate and format a result

```bash
npm run cli -- <result.json>
```

| Exit code | Meaning |
|-----------|---------|
| `0` | Valid; formatted summary on stdout |
| `2` | Failed zod validation; per-field errors on stderr; **nothing** rendered (FR-027) |
| `1` | File unreadable or not JSON |

The formatter re-implements no triage rule (FR-028). It validates, then displays.
