"""Refund policy lookup tool (task T016).

Like the order tool, this returns a discriminated union so a missing policy is a value the
refund guard can act on rather than an exception it must catch (FR-007, FR-016).

The fixture deliberately has no ``OTHER`` record, which keeps the "no policy exists" path
reachable in production code rather than only in tests.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..models import ActionKind, Category, PolicyFound, PolicyNotFound

_DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "refund_policies.json"


@lru_cache(maxsize=8)
def _load(path: Path) -> dict[str, dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):  # pragma: no cover - fixture is ours
        raise ValueError(f"policy fixture {path} must be a JSON object")
    return data


def get_refund_policy(
    category: Category,
    *,
    fixtures_path: Path | None = None,
) -> PolicyFound | PolicyNotFound:
    """Return the policy record for ``category``, or an explicit not-found marker."""
    records = _load(fixtures_path or _DEFAULT_FIXTURE)
    record = records.get(category.value)
    if record is None:
        return PolicyNotFound(category=category)

    return PolicyFound(
        category=category,
        window_days=int(record["window_days"]),  # type: ignore[call-overload]
        permitted_actions=tuple(
            ActionKind(name) for name in record["permitted_actions"]  # type: ignore[union-attr]
        ),
        requires_human_approval=bool(record["requires_human_approval"]),
        summary=str(record["summary"]),
    )
