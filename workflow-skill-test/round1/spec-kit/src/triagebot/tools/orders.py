"""Order lookup tool (task T015).

Returns a discriminated union, never ``None`` and never an exception, so "no such order" is
an inspectable value that the rationale can render and a test can assert on (FR-006).

The function is clock-free: ``as_of`` is supplied by the caller. A tool that read the system
clock would make triage results change from one day to the next, breaking SC-004.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from ..models import OrderFound, OrderNotFound, OrderState

_DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "orders.json"


@lru_cache(maxsize=8)
def _load(path: Path) -> dict[str, dict[str, str | None]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):  # pragma: no cover - fixture is ours
        raise ValueError(f"order fixture {path} must be a JSON object")
    return data


def get_order_status(
    order_id: str,
    *,
    as_of: date,
    fixtures_path: Path | None = None,
) -> OrderFound | OrderNotFound:
    """Look up ``order_id`` (FR-005, FR-006).

    ``days_since_delivery`` is computed against ``as_of`` and is ``None`` when the order has
    not been delivered -- an undelivered order has not started its refund window.
    """
    records = _load(fixtures_path or _DEFAULT_FIXTURE)
    record = records.get(order_id)
    if record is None:
        return OrderNotFound(order_id=order_id)

    delivered_raw = record.get("delivered_on")
    delivered_on = date.fromisoformat(delivered_raw) if delivered_raw else None
    days_since_delivery = (as_of - delivered_on).days if delivered_on is not None else None

    return OrderFound(
        order_id=order_id,
        state=OrderState(record["state"]),
        placed_on=date.fromisoformat(str(record["placed_on"])),
        delivered_on=delivered_on,
        days_since_delivery=days_since_delivery,
    )
