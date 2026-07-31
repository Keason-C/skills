# 06 — A Ticket cannot talk its way past the rules

**What to build:** text inside a Ticket that addresses the triage system instead of describing a
problem is detected, flagged on the Verdict, treated as a security event, and given exactly zero
influence over the outcome. The proof is a pair of Tickets identical except for the injected
lines — they must triage the same way.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Instruction-style text in the body is flagged as an Injection Attempt
- [ ] A flagged Ticket is escalated and its Priority is the security tier
- [ ] Two Tickets identical but for the injected text produce the same Category, Sentiment and
      Action
- [ ] Injected text never becomes an argument to any tool lookup
- [ ] Injection markers are recognised in both supported languages
- [ ] An ordinary Ticket that merely quotes the phrase in a complaint is still handled safely
      (flagging is allowed; changed behaviour is not)
