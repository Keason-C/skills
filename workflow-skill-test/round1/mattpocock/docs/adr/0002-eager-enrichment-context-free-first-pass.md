# Enrichment is eager, but the first classification pass is deliberately context-free

Tool Context (order status, refund Policy Entries) is fetched once, at the `NEW → ENRICHED`
transition, before any Driver call — but the *first* Driver call is made without it. Only the
low-confidence retry is given the Tool Context.

This looks backwards, so it is worth recording why. The confidence Guard says: when a Suggestion
comes back under the threshold, retry *with tool context*. If the first pass already carried the
full context, the retry would be the identical call and could only differ by sampling noise — a
retry that adds no information is not a Guard, it is a coin flip. Withholding the context on
pass one makes the retry a genuinely different, better-informed question.

Enrichment stays eager (rather than fetching lazily inside the retry) so that the Ticket's stage
means what it says: `ENRICHED` is "every fact we can gather has been gathered", the tools are hit
exactly once per Ticket regardless of path, and the Guard chain stays pure — no Guard performs
I/O.
