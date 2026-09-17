# Tech stack — Frontend (TypeScript)

Default for new projects; an existing project keeps its stack unless the user asks to change it.

- Base: React + Vite + Tailwind CSS + shadcn/ui. Package manager: bun.
- Routing: TanStack Router. Server state: TanStack Query.
- API client & forms: openapi-ts generates the client and the zod schemas from FastAPI's OpenAPI; forms are react-hook-form + those schemas — generated, never hand-written.
- Testing: Vitest + Playwright.
- Symbols: prefer an available LSP (tsserver); otherwise use text search.
- Escape hatch: single-view / pure-chat UIs may omit TanStack Router and react-hook-form.
