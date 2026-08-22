# Tech stack — Frontend (TypeScript)

Default for new projects. In an existing project, stick to the stack it already uses unless the user asks to change it.

- Base: React + Vite + Tailwind CSS + shadcn/ui
- Package manager: bun
- Routing: TanStack Router
- Server state: TanStack Query
- Forms & validation: react-hook-form + zod (generated from OpenAPI, never hand-written)
- API client: openapi-ts, generated from FastAPI's OpenAPI schema
- Testing: Vitest + Playwright
- Code navigation: typescript-language-server (tsserver) as the LSP server — navigate by LSP (go-to-definition, references, hover) rather than text search when resolving symbols
- Escape hatch: single-view / pure-chat UIs may omit TanStack Router and react-hook-form
