#!/usr/bin/env python
"""Regenerate schema/*.schema.json from the pydantic models."""

from pathlib import Path

from triagebot.schema_export import export_schemas

REPO_ROOT = Path(__file__).parent.parent


def main() -> None:
    written = export_schemas(REPO_ROOT / "schema")
    for name, path in sorted(written.items()):
        print(f"wrote {name}: {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
