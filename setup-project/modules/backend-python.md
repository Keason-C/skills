# Tech stack — Backend (Python)

Default for new projects; an existing project keeps its stack unless the user asks to change it. Layout: Netflix Dispatch style.

- Data contracts: pydantic, types-first — fields that travel together get a model before the code that uses them; raw dicts only at (de)serialization edges.
- API: FastAPI. HTTP client: httpx2. Workflow: pydantic-graph. Config: pydantic-settings.
- Tests: pytest. Every outbound HTTP call goes through pytest-httpx2's `httpx2_mock` fixture; only tests marked integration hit real services.
- Tooling: uv (conda projects stay on conda), ruff, ty. Deploy: Docker + docker-compose.
- Symbols: navigate by LSP (`ty server`) — go-to-definition, references, hover — not text search.
