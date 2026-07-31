# 12 — Someone else can run this

**What to build:** a way to go from a raw Ticket to a printed Verdict in two commands, and a
README that explains the architecture, the decisions and how to run everything.

**Blocked by:** 07, 11

**Status:** ready-for-agent

- [ ] A script triages sample Tickets and writes Verdict JSON to disk
- [ ] That output is exactly what the TypeScript CLI consumes
- [ ] The README explains the layering, the Guard order, and why the LLM only suggests
- [ ] The README lists the decisions taken and who took them (product owner vs engineer)
- [ ] The README states how to run both test suites offline
