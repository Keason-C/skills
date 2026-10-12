# Tech stack — Backend (Python)

Default for new projects; an existing project keeps its stack unless the user asks to change it. Layout: Netflix Dispatch style.

- Data contracts: use Pydantic for external inputs, configuration, and explicit data contracts. Choose ordinary Python types for internal temporary data; introduce a model when its contract earns one.
- API: FastAPI. HTTP client: httpx2. Config: pydantic-settings.
- Workflows: use functions for ordinary flows; introduce pydantic-graph when explicit state transitions or branching orchestration need a graph.
- Background jobs: choose PgQueuer or Taskiq when jobs need durable execution or scheduling across processes. Work that can finish in the request stays there; simple in-process background work can use the framework's facilities when losing it on restart is acceptable.
- Tooling: uv (conda projects stay on conda), ruff, ty. Deploy: Docker + docker-compose.
- ruff is linter and formatter both; ≥ 0.16 its defaults are the rule set, `extend-select` only what the project needs.
- Symbols: prefer an available LSP (`ty server`); otherwise use text search.

## Testing

- Framework: pytest. New async suites use AnyIO's pytest plugin with the asyncio backend; keep an existing project's async test runner.
- HTTP mocks: httpx2-pytest's `httpx2_mock`; tests marked integration may call real services. The selected package is httpx2-pytest; pytest-httpx2 exposes a different API.
- Coverage: pytest-cov with branch coverage; inspect gaps in changed behavior.
- Mutation testing: mutmut with pytest for changed critical business logic or explicit test-hardening work. Start from passing tests, add behavioral assertions for genuine survivors, and rerun the affected scope. Finish with each survivor resolved or documented as equivalent, out of scope, or unresolved. Requires a fork-capable environment (WSL on Windows).
- Run the minimum sufficient Ruff formatting/lint, ty type checks, and pytest tests for the change's impact through configured project commands and environment. Fix issues introduced by the change; report necessary checks that could not run. Add tests for meaningful behavior and regressions.
