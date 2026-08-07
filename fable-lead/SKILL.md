---
name: fable-lead
description: The user's optional working model — Fable 5 acts as the lead, driving explore → plan → execute → verify and delegating by difficulty to Opus/Sonnet subagents to save lead-model tokens. ONLY use when the user explicitly invokes this skill or names it. Do NOT load automatically based on task type, topic, or routing — explicit user invocation is required.
---

# Optional Working Model — opt-in

This skill is the sole home of the working model below; it applies only when the user has explicitly invoked this skill.

<optional-working-model>
When running as the Fable 5 model, Fable 5 acts as the lead, driving four phases: explore → plan → execute → verify.
Routing by difficulty: high → Opus first, Fable 5 takes over on failure; medium (regular code work) → Opus; low (mechanical, simple) → Sonnet.
- Explore: delegate research to subagents, choosing Opus or Sonnet by difficulty.
- Plan: done by Fable 5 itself, never delegated.
- Execute: assign subtasks to subagents, choosing Opus or Sonnet by difficulty. A failed subtask may be retried by subagents at most twice; if it still fails verification or cannot be completed, Fable 5 takes over directly.
- Trivial tasks (small edits, one-file changes, quick lookups) are done by the lead directly — delegation overhead exceeds the savings.
- Verify: Fable 5 leads acceptance; for critical output, optionally delegate adversarial verification to Opus or Sonnet via a workflow, choosing model and rigor by difficulty.
</optional-working-model>
