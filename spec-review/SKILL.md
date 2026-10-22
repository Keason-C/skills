---
name: spec-review
description: Only when implementing an existing spec, delegate a review to a subagent to check for missing, partially implemented, or incorrectly implemented requirements.
---

Use only while implementing an existing spec; writing, discussing, or reviewing a spec alone, and tasks without a spec, do not trigger this skill.

Before declaring the implementation complete, delegate a read-only review to an independent subagent. Provide the applicable spec, changes confirmed by the user, implementation locations, and available verification methods so the reviewer can inspect the implementation and verification evidence directly.

Have the subagent check every requirement and acceptance criterion for missing functionality, partial implementation, or functionality that appears implemented but is implemented incorrectly.

The review must report each requirement's status (met / partially met / unmet / unverifiable). For each finding, quote the relevant spec text and provide the implementation location and supporting evidence. Mark requirements as unverifiable when evidence is insufficient.

The main agent fixes discrepancies and has the subagent recheck the affected items before declaring completion. If a blocker cannot be resolved, clearly report the unmet items and reasons to the user.
