# Guards adjudicate; Drivers only suggest

A Driver's output is a **Suggestion** — a separate type from the **Verdict** — and the only way
to obtain a Verdict is to run the Suggestion through the Guard chain. We considered the cheaper
shape, where the Driver returns a `TriageResult` directly and the rules merely "validate" it,
and rejected it: with one type for both, any code path that forgets to validate silently ships
an LLM opinion as a decision, and the compiler cannot tell the two apart. Two types make the
unsafe path unrepresentable — you cannot hand a caller a Verdict without having run the Guards,
because there is no other constructor for one.

## Consequences

Guards must be total: for every Suggestion, including a malicious or nonsense one, the chain has
to produce a defensible Verdict rather than throwing. Escalation is the fallback for everything
the rules cannot vouch for.
