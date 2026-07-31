# 05 — Refund answers come from the policy, not from the model

**What to build:** for a REFUND Ticket, the Action a customer is told is the one the refund policy
prescribes — if the model recommended something else, the policy wins and the substitution is
recorded. And when a Ticket cites an order we cannot find, no refund Action may stand, with
REFUND and BILLING Tickets going to a human because the evidence is missing.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] A REFUND Suggestion whose Action contradicts the Policy Entry is rewritten to the policy's
      Action
- [ ] A REFUND Suggestion already agreeing with the policy is left alone
- [ ] The rationale records that the Action came from the policy
- [ ] A refund Action is never executed automatically — recommending it always escalates
- [ ] An unknown cited order is stated in the rationale
- [ ] An unknown cited order escalates REFUND and BILLING Tickets, and only those
- [ ] An unknown cited order forbids any refund Action regardless of Category
