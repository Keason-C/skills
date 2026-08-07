# Tech stack — Agent dev

Adds to the backend/frontend stack when the project is an AI-agent app.

## Backend

- Agents: pydantic-ai / Claude Agent SDK
- Lightweight sandbox: monty (Pydantic's lightweight Python interpreter for safely running untrusted / agent-generated code; still experimental as of 2026-07)
- Observability: OpenTelemetry — Logfire as a swappable OTLP backend
- Evals: pydantic-evals

## Frontend

- AI chat UI: Vercel AI SDK (useChat) + AI Elements
- Agent↔UI: Vercel AI Data Stream protocol; backend ModelMessage in Postgres is the source of truth, UI rebuilds from it
