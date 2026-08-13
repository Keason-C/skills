# Tech stack — Backend (Python)

Default for new projects. In an existing project, stick to the stack it already uses unless the user asks to change it.

Code organization: Netflix Dispatch style.

- Data modeling & validation: pydantic
- API layer: FastAPI, with pydantic models defining request/response contracts
- HTTP client: httpx2 (Pydantic-maintained successor to httpx, separate package name `httpx2`, native WebSocket support since v2.6) — replaces requests / aiohttp / websockets, etc.
- Workflow: pydantic-graph
- Config: pydantic-settings
- Database: PostgreSQL 18 + SQLModel + Alembic (table models stay out of API signatures) — dev/tests/demo: embedded `pixeltable-pgserver` ≥0.6.0 (persistent datadir; bundles PG 18 + pgvector, same major as prod); prod: the existing PostgreSQL 18 instance; never pgserver / py-pglite (defunct); DB behind a connection-URL seam
  - When the user confirms the switch to the full prod PostgreSQL: verify migrations + integration tests against real `postgres:18` (just swap DATABASE_URL).
- Task queue (optional): arq (queue Redis: persistence on, eviction off)
- Tooling: uv (existing conda-based projects stay on conda), ruff, pytest, pyright
- Deploy: Docker + docker-compose
