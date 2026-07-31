# 08 — Chinese Tickets get the same quality as English ones

**What to build:** the shipped Driver understands Chinese as well as English — category keywords
and sentiment markers in both. A Ticket in any other language is honestly labelled OTHER with
confidence capped low enough that the ordinary confidence Guard routes it to a human; no special
case, no crash.

**Blocked by:** 01, 06

**Status:** ready-for-agent

- [ ] A Chinese refund complaint is categorised and sentiment-scored like its English twin
- [ ] A Chinese angry Ticket registers as angry
- [ ] A Ticket in an unsupported language is Category OTHER with confidence at or below the cap
- [ ] That Ticket reaches a human through the ordinary confidence path, not a bespoke branch
- [ ] Non-Latin text never causes a crash anywhere in the pipeline
