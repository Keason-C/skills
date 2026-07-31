"""Write the JSON Schema for TriageBot's public models into `schema/`.

Usage: python scripts/export_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from triagebot.schema_export import export_schemas  # noqa: E402


def main() -> None:
    for path in export_schemas():
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
