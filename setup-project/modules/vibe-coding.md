# Vibe coding: technical reference

- API facts (existence, signature, deprecation): the installed package is the
  authority. Not installed? Fall back to official docs for the candidate version,
  and tell the user explicitly that it is unverified against an installed package.
- Concepts & patterns: skill (project → plugin → bundled in package) → context7
  → official docs. A source that is silent, unavailable, or tracking a different
  version doesn't count — move down the list.
- API facts inside a concept answer still get checked against the installed package.
