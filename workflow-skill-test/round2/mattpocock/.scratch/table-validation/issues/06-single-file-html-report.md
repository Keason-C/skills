# 06 — One HTML file you can email

**What to build:** `--html report.html` produces a single file that an operations
colleague can double-click on a machine with no network and use immediately.
Python's whole contribution is packaging: read the committed bundle, encode the
validation result safely, interpolate both into a small skeleton.

**Blocked by:** 04, 05

**Status:** ready-for-agent

- [ ] `--html PATH` writes a file that opens and works from `file://` with no network
- [ ] The file references nothing external — no URL, no CDN, no remote font, no external stylesheet or script
- [ ] The embedded data survives hostile content — a value containing `</script>` cannot break out
- [ ] End-to-end: a deliberately dirty table validated through the CLI produces an HTML report containing the expected violations
- [ ] No absolute filesystem paths appear anywhere in the output
- [ ] `--json` and `--html` can be produced in the same run
