# 04 — An unsure model gets one more look, then a human

**What to build:** when the Driver comes back under the confidence threshold, TriageBot asks it
again — this time with the Tool Context it withheld the first time. If the second answer clears
the threshold, that answer is used. If it does not, the Ticket goes to a human.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] A Suggestion below the threshold triggers exactly one retry
- [ ] The retry call receives the Tool Context; the first call does not
- [ ] A retry that clears the threshold produces a Verdict from the second Suggestion
- [ ] A retry that stays below the threshold escalates
- [ ] Confidence exactly at the threshold does not retry
- [ ] A confident first Suggestion causes no second Driver call
