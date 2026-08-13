# Constitution docs

Project design docs live in `constitution-doc/`. Read them before starting work; write back as work progresses.

- `constitution.md` — Mission and Roadmap: what the product is and how far the current Phase ships; stages track progress via `Status:` lines (`closed` is user-only). **During implement, only a Stage's `Status:` may be updated; any change to Mission or a Phase requires user confirmation.**
- `api-design.md` — the single API contract doc for the whole project, one section per endpoint (params, response, auth, idempotency, errors); update it **before** touching any endpoint code.
