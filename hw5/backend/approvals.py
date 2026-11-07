"""Queue of payments the agents prepared during dashboard runs.

Agents never pay from the dashboard: their pay call is recorded here as
"pending". A human clicking Approve (POST /api/approvals/{id}/approve) is what
calls pay_invoice / pay_rent on the MCP server and actually moves cash.
Stored in output/pending_approvals.json so it survives `uvicorn --reload`.
"""

from __future__ import annotations

import json
import threading
import uuid

from config import ROOT
from models import PendingApproval

PATH = ROOT / "output" / "pending_approvals.json"
_lock = threading.Lock()


def _load() -> list[PendingApproval]:
    if not PATH.exists():
        return []
    return [PendingApproval(**p) for p in json.loads(PATH.read_text(encoding="utf-8") or "[]")]


def _save(items: list[PendingApproval]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps([p.model_dump(mode="json") for p in items], indent=2), encoding="utf-8")


def add(**fields) -> PendingApproval:
    with _lock:
        items = _load()
        item = PendingApproval(id=uuid.uuid4().hex[:8], **fields)
        items.append(item)
        _save(items)
        return item


def all_items() -> list[PendingApproval]:
    with _lock:
        return _load()


def get(approval_id: str) -> PendingApproval | None:
    return next((p for p in all_items() if p.id == approval_id), None)


def update(item: PendingApproval) -> None:
    with _lock:
        _save([item if p.id == item.id else p for p in _load()])


def clear() -> int:
    """Drop every queued payment (used by the reset route: a fresh DB has nothing pending)."""
    with _lock:
        n = len(_load())
        _save([])
        return n
