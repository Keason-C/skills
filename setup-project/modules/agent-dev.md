# Tech stack — Agent dev

Defaults for AI-agent capabilities the project needs; preserve existing project choices.

## Backend

- Agents: pydantic-ai / Open Interpreter.
- Lightweight sandbox: monty, Pydantic's experimental Python interpreter for untrusted or agent-generated code.
- Observability: OpenTelemetry; Logfire as a swappable OTLP backend.
- Evals: pydantic-evals.

## Frontend

- Chat UI: Vercel AI SDK (useChat) + AI Elements.
- Agent↔UI: Vercel AI Data Stream protocol. For persisted conversations, backend ModelMessage in the project's database is the source of truth for rebuilding the UI.
