"""gridcalc: an in-memory spreadsheet engine. See BRIEF.md.

The public API below is fixed: keep these names and signatures.
"""

from __future__ import annotations

from ._errors import CellError
from ._sheet import Sheet

__all__ = ["Sheet", "CellError"]
