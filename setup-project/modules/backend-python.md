# Tech stack — Backend (Python)

Default for new projects. In an existing project, stick to the stack it already uses unless the user asks to change it.

Code organization: Netflix Dispatch style.

## Core

- Data contracts: pydantic, types-first — fields that travel together get a model declared before the code that uses them; raw dicts only at (de)serialization edges
- API layer: FastAPI, with pydantic models defining request/response contracts
- HTTP client: httpx2
- Workflow: pydantic-graph
- Config: pydantic-settings

## Data

- Database: PostgreSQL 18 + SQLModel + Alembic (table models stay out of API signatures) — dev/tests/demo: embedded `pixeltable-pgserver` ≥0.6.0 (persistent datadir; bundles PG 18 + pgvector, same major as prod); prod: the existing PostgreSQL 18 instance; never pgserver / py-pglite (defunct); DB behind a connection-URL seam
  - When the user confirms the switch to the full prod PostgreSQL: verify migrations + integration tests against real `postgres:18` (just swap DATABASE_URL).
- Task queue (optional): arq (queue Redis: persistence on, eviction off)

## Testing

- Runner: pytest
- HTTP mocking: pytest-httpx2 (maintained by the respx author; its `httpx2_mock` fixture is a respx Router) — unit tests route every outbound HTTP call through it; only tests explicitly marked as integration talk to real services
- DB in tests: the embedded `pixeltable-pgserver` above — tests run real SQL against real PostgreSQL, no SQL-level mocks

## Tooling & deploy

- Tooling: uv (existing conda-based projects stay on conda), ruff, pyright
- Code navigation: pyright doubles as the LSP server — navigate by LSP (go-to-definition, references, hover) rather than text search when resolving symbols
- Deploy: Docker + docker-compose
