# 03 — Large sums always reach a human

**What to build:** a Ticket disputing more than 1000.00 USD is escalated no matter how confident
or how relaxed the model was about it. A Ticket disputing exactly 1000.00 is not — the line is
unambiguous.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] An amount strictly above the threshold escalates even when the Suggestion is high-confidence
      and recommends self-service
- [ ] An amount exactly equal to the threshold does not escalate on this Guard's account
- [ ] A Ticket with no amount is unaffected
- [ ] The reason for the escalation appears in the rationale
- [ ] The comparison is exact — a value one cent over the threshold escalates
