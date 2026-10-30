---
name: human-review-report
disable-model-invocation: true
description: Use only when the user invokes human-review-report or explicitly requests this report. Review the system impact of the current changes and report directly in chat, following the user's language conventions and grouping findings by area and review priority. Do not write a document.
---

# Human Review Report

Identify system impacts and risks in the current task's changes that warrant human review. Produce a clear, readable report to help the user decide whether to make further changes.

Run only when explicitly requested by the user. Review read-only and output the report directly in chat; do not create or write documents. Leave code changes, data migrations, permission changes, and deployment to a separate user decision.

## Review Scope

Use the user-specified scope or the current task's changes. Exercise judgment about what to investigate and how, informed by the project context.

Use these areas to organize the report, letting the actual changes determine what deserves attention. Add an area when a significant system impact falls outside these categories:

- Database and data migrations
- Permissions and security boundaries
- Interfaces and compatibility
- Deployment configuration and dependencies
- Data consistency and failure handling
- Background tasks and external side effects

## Report Requirements

- Follow the user's language conventions. Write plainly and briefly state the review scope.
- Group findings by area. Within each area, order them by review priority, label the priority, and explain the reasoning.
- Explain each change, its potential impact, the supporting evidence, and the recommended action so the user knows what to decide. Include locatable code or configuration references.
- Distinguish confirmed facts, conditional risks, and unverified information. Disclose material review limitations.
- Focus on matters worth attention in the current changes. Briefly note areas that are unaffected or have no pending decisions. If there are no findings, say so without inventing risks.
- Choose the format and length to suit the findings and help the user read and decide.
- Finish with a paragraph giving your own overall assessment of system risk, supported by the findings. State your conclusion, the key reasons and any uncertainty that affects it, and whether you recommend further changes.
