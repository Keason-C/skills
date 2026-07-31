# 01 — Tracer bullet: a Ticket goes in, a Verdict comes out

**What to build:** the thinnest complete path through the system. A caller hands a Ticket and a
Driver to one function and gets back a Verdict carrying a Category, Sentiment, confidence, Action
and rationale. Malformed Tickets are refused before any of that happens, and the Ticket's walk
through the Triage Stage machine is real — a caller cannot fabricate a finished Ticket by writing
a stage. No Guards yet: this slice proves the spine.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `triage_ticket(ticket, driver)` returns a Verdict for a well-formed Ticket
- [ ] Empty or whitespace-only body is refused at the boundary
- [ ] Body over 20 000 characters is refused; subject over 200 characters is refused
- [ ] Unknown fields on a Ticket are refused
- [ ] A negative or non-finite `amount` is refused; `amount` is exact, not floating point
- [ ] Advancing a Triage Stage out of order raises rather than being silently corrected
- [ ] The Verdict type cannot be built from a Suggestion except through the adjudication path
