#!/usr/bin/env bash
# Keep the router layout intact after `npx skills add/update mattpocock/skills`.
#
# The upstream installer writes into .claude/skills/, which Claude Code
# auto-registers. We want exactly one registered skill (the router) and the
# bodies parked in .claude/mp-skills/ where nothing auto-loads them.
#
# Run after every add/update:  .claude/reroute-skills.sh
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .claude/mp-skills
moved=0
for d in .claude/skills/*/; do
  n=$(basename "$d")
  [ "$n" = "mattpocock" ] && continue          # the router itself stays put
  rm -rf ".claude/mp-skills/$n"
  mv "$d" ".claude/mp-skills/$n"
  moved=$((moved + 1))
done
echo "moved $moved skill(s) out of .claude/skills/"

python3 - <<'PY'
import os, re

root = ".claude/mp-skills"
rows = []
for n in sorted(os.listdir(root)):
    f = os.path.join(root, n, "SKILL.md")
    if not os.path.isfile(f):
        continue
    m = re.match(r"^---\n(.*?)\n---\n", open(f).read(), re.S)
    desc = ""
    if m:
        dm = re.search(r"^description:\s*(.+?)(?=\n[a-zA-Z-]+:|\Z)", m.group(1), re.S | re.M)
        if dm:
            desc = " ".join(dm.group(1).split())
    if len(desc) > 150:
        desc = desc[:147].rsplit(" ", 1)[0] + "…"
    rows.append((n, desc.replace("|", "/")))

router = ".claude/skills/mattpocock/SKILL.md"
body = open(router).read()
head = body.split("## Index")[0]
table = "## Index\n\n| skill | use when |\n|---|---|\n" + "\n".join(
    f"| `{n}` | {d} |" for n, d in rows
) + "\n"
open(router, "w").write(head + table)
print(f"router index regenerated: {len(rows)} skills")
PY
