# 02 — Tool Context: the facts we hold about a Ticket

**What to build:** before anything classifies a Ticket, TriageBot gathers what it already knows —
the status of the order the customer cited, and the refund Policy Entries. An order we cannot
find is an ordinary answer ("not found"), not a crash. The gathering happens exactly once per
Ticket, and the arguments used come only from validated Ticket fields.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Looking up a known order returns its status; looking up an unknown one returns a not-found
      answer rather than raising
- [ ] Looking up the refund policy for a Category returns that Category's Policy Entry
- [ ] A Ticket with no order cited enriches successfully with no order facts
- [ ] Enrichment happens once per Ticket regardless of which path the Ticket later takes
- [ ] The Ticket reaches the ENRICHED stage before any Driver is called
