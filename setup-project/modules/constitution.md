# Constitution

Project design docs live in `constitution-doc/` (repo root).

- `constitution.md` — Mission and Roadmap. **Before writing a plan or the first code edit of a task, read the current Phase (the first not `closed`): its `Decision` bounds scope, its `Acceptance Criteria` define done, and each Stage's `Spec:` points to its spec file.** Set the Stage you start to `Status: in-progress`; never report work complete until you have set it to `awaiting-acceptance` and requested acceptance. Advancing a `Status:` (never to `closed`) is the only edit you may make on your own; every other edit — Mission, Phase, Stage text, adding or removing a Stage — requires user confirmation.
- `api-design.md` — the project's single API contract. **Before editing or adding endpoint code, read — or first write — that endpoint's section**; the contract change lands in the doc before the code.
- If a doc disagrees with the code or with reality, stop and surface it.
