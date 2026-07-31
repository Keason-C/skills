# Clarification Session — 2026-07-31

Working artifact for the `/speckit-clarify` phase. Records the ambiguity coverage scan, the
prioritized question queue, and (once answered) the disposition of each question.

## Protocol deviation, recorded deliberately

The `speckit-clarify` skill prescribes a *sequential* loop: "Present EXACTLY ONE question at a
time." This agent cannot conduct a synchronous back-and-forth with the requester — questions are
delivered to Iris asynchronously between turns, with a hard budget of at most two rounds. Asking one
question per round would consume the entire budget on the first two of five questions.

All five questions are therefore presented together in a single round. Everything else about the
skill's questioning rules is honoured: the 5-question cap, the MC-or-short-answer constraint, the
"lead with a full interrogative" rule, the "Why it matters" sentence, the recommended-option-first
format, and the requirement that every question materially affect architecture, data modeling, test
design, or acceptance.

## Ambiguity & Coverage Scan

| Category | Status | Disposition |
|---|---|---|
| Core user goals & success criteria | Clear | Ticket is explicit; captured in SC-001..SC-008. |
| Explicit out-of-scope declarations | Clear | Recorded in Assumptions (no auto-fix, no cross-table, no history). |
| User roles / personas | Clear | Two personas, both named in the ticket: data engineer, ops reader. |
| Entities, attributes, relationships | Partial | Violation shape settled; **value semantics not** → Q1, Q3, Q4. |
| Identity & uniqueness rules | Partial | How to identify a row in the report. **Resolved technically** — see below. |
| Lifecycle / state transitions | Clear | Validation is a stateless read-only run. No lifecycle. |
| Data volume / scale assumptions | Partial | Millions of rows stated; limit policy explicitly delegated to us by Iris. **Resolved technically.** |
| Critical user journeys | Clear | Four prioritized user stories. |
| Error / empty / loading states | Clear | Empty table, missing table, bad schema all specified as edge cases. |
| Accessibility / localization | Outstanding | Low impact; will apply sane defaults (semantic HTML, keyboard-operable controls, no colour-only signalling). Not worth a question. |
| Performance targets | Outstanding | No hard target stated; bounded by the truncation limit. Low impact. |
| Scalability limits | Partial | Same as data volume. **Resolved technically.** |
| Reliability / availability | Clear | Not applicable — a local CLI, no service. |
| Observability | Clear | Not applicable at this scope. |
| **Security & privacy** | **Missing** | Report is forwarded to a wider audience and embeds raw cell values → **Q5**. |
| Compliance / regulatory | Missing | Folded into Q5 rather than asked separately. |
| External services / APIs | Clear | None. Offline is a hard requirement (FR-014). |
| Data import/export formats | Partial | JSON Schema in, JSON + HTML out. **Which JSON Schema subset is undecided** → Q2. |
| Protocol / versioning | Partial | JSON Schema draft version. Folded into Q2. |
| Negative scenarios | Clear | Enumerated under Edge Cases. |
| Rate limiting / throttling | Clear | Not applicable. |
| Conflict resolution | Clear | Not applicable — read-only, single run. |
| Technical constraints | Clear | Dictated by the Tech Lead in the ticket; encoded in the constitution. |
| Explicit tradeoffs / rejected alternatives | Deferred | Belongs in the plan's decision record, not the spec. |
| Terminology & glossary | Clear | "violation", "run", "summary", "report" used consistently. |
| Acceptance criteria testability | Clear | Each FR has a matching acceptance scenario. |
| TODO markers / unresolved decisions | Partial | Three `[NEEDS CLARIFICATION]` markers → Q1, Q2/Q3, Q4. |
| Ambiguous adjectives | Clear | Checked for "robust"/"intuitive"/"fast"; none present unqualified. |

## Resolved as technical decisions (NOT asked — per ticket, "技术决策自己定")

These were candidate questions that were deliberately dropped from the queue because the ticket
assigns them to the implementer. Each is recorded here and will be restated in the plan's decision
record.

1. **How a row is identified in the report.** Use the table's declared primary key when it has one,
   otherwise `rowid`. This is not invented: `Table.pks` in `db.py` already implements exactly this
   fallback (returns `["rowid"]` when `use_rowid` is true), so following it makes violation
   identifiers consistent with every other part of the library.
2. **Truncation limit default.** Iris explicitly delegated this ("你们定个合理的策略"). Default to
   1,000 retained violations, caller-overridable (FR-025), with true totals always preserved
   (FR-024). Rationale: a 1,000-row list renders and filters instantly in a browser with no
   virtualization, and keeps the self-contained file comfortably small enough to send over chat.
3. **Exit status numbering.** `0` = passed, `1` = violations found, `2` = the tool could not run.
   `2` is not an arbitrary pick — it is what `click` already returns for usage errors, so aligning
   with it avoids a third convention inside the same CLI.
4. **Whether validation streams or materializes rows.** Stream; never hold the whole table in memory.
5. **Frontend build tool, module layout, test framework wiring.** Plan-level decisions.

## Question Queue (5, ordered by Impact × Uncertainty)

Status: **ASKED — awaiting answers from Iris.**

| # | Topic | Category | Blocking? |
|---|---|---|---|
| Q1 | Type coercion for text-stored values | Domain & Data Model | Yes — determines whether the feature works at all on CSV-loaded tables |
| Q2 | JSON Schema keyword coverage & draft | Integration & Data Formats | Yes — sets implementation scope and dependency decision |
| Q3 | Columns the schema does not mention | Domain & Data Model | Yes — changes violation counts on every real table |
| Q4 | NULL semantics | Domain & Data Model | Yes — changes required/type outcomes on most rows |
| Q5 | Raw value exposure in the shareable report | Security & Privacy | Yes — the report leaves the data team |

## Answers

Received 2026-07-31. Integrated into `spec.md` under `## Clarifications`; downstream sections
updated and contradictions removed.

| # | Recommended | Chosen | Outcome |
|---|---|---|---|
| Q1 | D (lenient default) | **C (strict default)** | Overridden. Plus a new requirement: split type failures into coercible vs invalid. |
| Q2 | B (practical subset) | **B, with conditions** | Accepted, plus a hard new requirement to reject unsupported keywords loudly. |
| Q3 | C (honour `additionalProperties`) | **C** | Accepted as recommended. |
| Q4 | A (NULL = absent) | **B (NULL = JSON null)** | Overridden. Inverted an existing acceptance scenario. |
| Q5 | A (show values) | **A, with conditions** | Accepted, narrowed to offending column only; no absolute paths. |
| — | — | **New requirement** | Independent row-scan cap for script spot-checks. |

### Why the two overrides matter

**Q1 → C.** I recommended a lenient default on the grounds that strict typing would flag every row
of every CSV-derived table and make the tool look broken. The requester's answer reframes that
outcome: a 100% violation rate on an untyped CSV import is *an accurate report about the data*, and
surfacing it is the primary reason she wants the tool. My recommendation optimised for the tool
appearing useful; hers optimises for the tool being honest. She also disarmed my actual objection —
that a uniform wall of violations is untriageable — by requiring the coercible/invalid split, which
is a better solution than the leniency I proposed because it preserves the signal *and* makes it
navigable. This is now FR-008a/FR-008b and a report filter.

**Q4 → B.** I recommended treating NULL as an absent value so `required` would catch empty CSV
cells. The requester chose the JSON-Schema-faithful reading: the column always exists, so `required`
is never triggered by NULL; `type` rejects it unless the schema says `"null"`. The consequence she
is buying is that *nullability becomes something the schema author states explicitly*, and the tool
never quietly decides on their behalf. This is more principled than my answer and consistent with
Q3's "don't invent private rules on top of JSON Schema". It also invalidated User Story 1's
scenario 3, which had to be rewritten rather than extended.

### Naming decisions arising from the new requirement (technical, mine)

- `--scan-limit N` — examine at most the first N rows. Independent of detail truncation.
- `--max-violations N` — retain at most N violation records in the outputs. Default 1,000.

Chosen so neither name can be misread as the other; a bare `--limit` would have been ambiguous
between the two, which is precisely the confusion FR-025b forbids.

### Disposition of all five questions

All resolved. No questions deferred, no second round required. The two-round budget was not
exhausted; one round sufficed because all five were asked together.
