# Tech stack — Frontend (TypeScript)

Default for new projects; an existing project keeps its stack unless the user asks to change it.

- Base: React + Vite + Tailwind CSS + shadcn/ui. Package manager: bun.
- Routing: TanStack Router. Server state: TanStack Query.
- API client & forms: openapi-ts generates the client and the zod schemas from FastAPI's OpenAPI; forms are react-hook-form + those schemas — generated, never hand-written.
- Symbols: prefer an available LSP (tsserver); otherwise use text search.
- Escape hatch: single-view / pure-chat UIs may omit TanStack Router and react-hook-form.

## Testing

- Unit and component tests: Vitest; React Testing Library + user-event for user-visible React interactions. End-to-end: Playwright for critical browser journeys across the frontend and backend.
- Coverage: @vitest/coverage-v8; inspect line and branch gaps in changed behavior.
- Mutation testing: StrykerJS (@stryker-mutator/core + @stryker-mutator/vitest-runner) for changed critical business logic or explicit test-hardening work. Start from passing tests, add behavioral assertions for genuine survivors, and rerun the affected scope. Finish with each survivor resolved or documented as equivalent, out of scope, or unresolved.
- Runtime: Node.js for Vitest and StrykerJS, matching their engine requirements; Bun manages dependencies and invokes project scripts.
- Run the minimum sufficient type checks, lint, Vitest tests, and Playwright journeys for the change's impact through configured project commands. Fix issues introduced by the change; report necessary checks that could not run.
