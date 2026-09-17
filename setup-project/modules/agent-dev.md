# Tech stack — Agent dev

Adds to the backend/frontend stack when the project is an AI-agent app.
These are defaults for capabilities the current task needs; preserve an existing project's stack.

## Backend

- Agents: pydantic-ai / Open Interpreter
- Lightweight sandbox: monty (Pydantic's lightweight Python interpreter for safely running untrusted / agent-generated code; experimental)
- Observability: OpenTelemetry — Logfire as a swappable OTLP backend
- Evals: pydantic-evals

## Frontend

- AI chat UI: Vercel AI SDK (useChat) + AI Elements
- Agent↔UI: Vercel AI Data Stream protocol; when persistence is needed, store backend ModelMessage in the project's selected database as the source of truth and rebuild the UI from it.
