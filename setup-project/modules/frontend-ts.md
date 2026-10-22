# Tech stack — Frontend (TypeScript)

Defaults for new projects; preserve existing project choices.

- Base: React + Vite + Tailwind CSS + shadcn/ui. Package manager: bun.
- Routing: TanStack Router. Server state: TanStack Query.
- API client and schemas: openapi-ts generates the client and zod schemas from FastAPI's OpenAPI. Forms: react-hook-form with those generated schemas.
- Symbol navigation: available LSP (tsserver), with text search as fallback.
- Single-view or pure-chat UIs may omit TanStack Router and react-hook-form.

## Testing

- Unit/component: Vitest + React Testing Library + user-event. End-to-end: Playwright for critical browser journeys across frontend and backend.
- Coverage: @vitest/coverage-v8, including lines and branches.
- Mutation testing: StrykerJS (@stryker-mutator/core + @stryker-mutator/vitest-runner) for critical business logic and test-hardening work.
- Runtime: Node.js matching Vitest/StrykerJS engine requirements; Bun manages dependencies and invokes project scripts.
