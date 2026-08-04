#!/usr/bin/env bash
# Materialize repo-declared plugins so their skills are available in-session.
set -euo pipefail
claude plugin marketplace add mattpocock/skills --scope project >/dev/null 2>&1 || true
claude plugin install mattpocock-skills@mattpocock --scope project >/dev/null 2>&1 || true
exit 0
