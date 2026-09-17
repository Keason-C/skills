# Tech stack — Backend (Python)

Default for new projects; an existing project keeps its stack unless the user asks to change it. Layout: Netflix Dispatch style.

- Data contracts: use Pydantic for external inputs, configuration, and explicit data contracts. Choose ordinary Python types for internal temporary data; introduce a model when its contract earns one.
- Validate at external boundaries; internal code relies on established types and contracts. Catch exceptions where meaningful recovery or boundary-level translation is possible. Retries and fallbacks need a concrete requirement; introduce an abstraction with its second implementation.
- API: FastAPI. HTTP client: httpx2. Config: pydantic-settings.
- Workflows: use functions for ordinary flows; introduce pydantic-graph when explicit state transitions or branching orchestration need a graph.
- Background jobs: choose PgQueuer or Taskiq when jobs need durable execution or scheduling across processes. Work that can finish in the request stays there; simple in-process background work can use the framework's facilities when losing it on restart is acceptable.
- Tests: pytest. New async test suites use AnyIO's pytest plugin with the asyncio backend; keep an existing project's async test runner. Mock outbound HTTP with httpx2-pytest's `httpx2_mock`; tests marked integration may call real services. The selected package is httpx2-pytest; pytest-httpx2 exposes a different API.
- Tooling: uv (conda projects stay on conda), ruff, ty. Deploy: Docker + docker-compose.
- ruff is linter and formatter both; ≥ 0.16 its defaults are the rule set, `extend-select` only what the project needs.
- Choose the minimum sufficient Ruff formatting/lint, ty type checks, and pytest tests for the change's impact, using the project's configured commands and environment. Fix issues introduced by the change; report necessary checks that could not run. Add tests for meaningful behavior and regressions.
- Symbols: prefer an available LSP (`ty server`); otherwise use text search.
