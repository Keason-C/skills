# Tech stack — Backend (Python)

Defaults for new projects; preserve existing project choices. Layout: Netflix Dispatch style.

- Contracts: Pydantic for external inputs, configuration, and explicit data contracts; ordinary Python types for internal temporary data.
- API: FastAPI. HTTP client: httpx2. Configuration: pydantic-settings.
- Workflows: functions for ordinary flows; pydantic-graph for explicit state transitions and branching orchestration.
- Background jobs: PgQueuer or Taskiq for durable execution and cross-process scheduling; request-local or in-process work for simpler, restart-tolerant tasks.
- Tooling: uv (existing conda projects keep conda), ruff, ty. Deployment: Docker + docker-compose.
- Ruff handles lint and formatting; version ≥ 0.16 defaults are the baseline, with project-specific `extend-select` additions.
- Symbol navigation: available LSP (`ty server`), with text search as fallback.

## Testing

- pytest; new async suites use AnyIO's pytest plugin with the asyncio backend. Preserve existing async test runners.
- HTTP mocks: httpx2-pytest's `httpx2_mock`; integration-marked tests may use real services. The similarly named pytest-httpx2 has a different API.
- Coverage: pytest-cov, including branches.
- Mutation testing: mutmut + pytest for critical business logic and test-hardening work; requires a fork-capable environment (WSL on Windows).
