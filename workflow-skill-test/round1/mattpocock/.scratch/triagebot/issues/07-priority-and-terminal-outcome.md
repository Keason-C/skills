# 07 — Priority is ours, and every Ticket ends somewhere

**What to build:** the Priority on a Verdict is computed by the rules from what actually happened
to the Ticket — the model's suggested priority is recorded but never used. Every Ticket then ends
in exactly one terminal Triage Stage: auto-resolved, or escalated to a human.

**Blocked by:** 03, 04, 05, 06

**Status:** ready-for-agent

- [ ] An Injection Attempt yields the top Priority tier
- [ ] An amount-Guard escalation floors at the second tier, not the top one
- [ ] Any escalation floors at the second tier
- [ ] An angry customer on a REFUND or BILLING Ticket floors at the second tier
- [ ] Ordinary TECHNICAL and ACCOUNT Tickets sit at the third tier; everything else at the fourth
- [ ] A wildly wrong suggested priority from the Driver never appears on the Verdict
- [ ] Auto-resolution requires all of: no Guard fired, confidence at or above the threshold,
      Priority below the top tier, Category not OTHER
- [ ] An escalated Ticket ends ESCALATED; an auto-resolved one ends AUTO_RESOLVED; the escalation
      flag and the terminal stage never disagree
