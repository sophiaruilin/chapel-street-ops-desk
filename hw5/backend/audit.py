"""Append-only, tamper-evident audit trail at output/audit_trail.json.

The file is one JSON array, one event per line. Each event is appended in
place (the closing "]" is moved to after it), so history is never rewritten
or wiped between runs. Every event carries `prev_hash` (the hash of the
event before it) and `hash` = sha256(prev_hash + the event's canonical JSON),
so editing or deleting any earlier event breaks the chain. Check it with
`python verify_audit.py`. (Events written before the chain existed have no
hash; the first chained event anchors to a hash of the last one of those.)

If OneDrive or another program briefly locks the file, the write is retried;
if it stays locked, the event goes to audit_trail.pending.jsonl so nothing is lost.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import config
from models import AuditEvent

_lock = threading.Lock()


def trim(value: Any, limit: int = config.AUDIT_TEXT_CHARS) -> Any:
    """Keep audit entries readable: long strings are cut, everything else passes through."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [+{len(value) - limit} chars]"
    return value


def canonical(event: dict) -> str:
    """Stable JSON for hashing: sorted keys, no spaces, the `hash` field itself left out."""
    return json.dumps({k: v for k, v in event.items() if k != "hash"}, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)


def event_hash(prev_hash: str, event: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(event)).encode("utf-8")).hexdigest()


def anchor_hash(event: dict) -> str:
    """Hash used as prev_hash after an event that has no hash of its own (older history)."""
    return hashlib.sha256(canonical(event).encode("utf-8")).hexdigest()


def _last_event(path: Path) -> dict | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 400_000))
        tail = f.read().decode("utf-8", "ignore")
    for line in reversed(tail.splitlines()):
        line = line.strip().rstrip(",")
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:  # not one-event-per-line (e.g. older pretty-printed history): parse the whole array
        events = json.loads(path.read_text(encoding="utf-8") or "[]")
        return events[-1] if events else None
    except (json.JSONDecodeError, OSError):
        return None


def _append(path: Path, line: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        path.write_bytes(b"[\n" + line + b"\n]\n")
        return
    with open(path, "r+b") as f:
        f.seek(0, 2)
        size = f.tell()
        back = min(size, 256)
        f.seek(size - back)
        tail = f.read(back)
        close = tail.rfind(b"]")
        if close < 0:
            raise ValueError(f"{path.name} does not end with ']' - not touching it")
        pos = size - back + close
        f.seek(0)
        empty = f.read(pos).strip() == b"["  # file was "[]"
        f.seek(pos)
        f.truncate()
        f.write((b"" if empty else b",\n") + line + b"\n]\n")


def record(event: AuditEvent) -> None:
    """Append one hash-chained event to the audit trail."""
    path = config.AUDIT_PATH
    with _lock:
        data = event.model_dump(mode="json")
        last = _last_event(path)
        if last is None:
            prev = "genesis"
        else:
            prev = last.get("hash") or anchor_hash(last)
        data["prev_hash"] = prev
        data["hash"] = event_hash(prev, data)
        line = json.dumps(data, ensure_ascii=False).encode("utf-8")
        for attempt in range(8):
            try:
                _append(path, line)
                return
            except PermissionError:
                time.sleep(0.25 * (attempt + 1))
        with open(path.with_suffix(".pending.jsonl"), "ab") as f:
            f.write(line + b"\n")
