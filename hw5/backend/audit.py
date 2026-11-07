"""Append-only audit trail at output/audit_trail.json.

The file is one JSON array, one event per line. Each event is appended in
place (the closing "]" is moved to after it), so history is never rewritten or
wiped between runs. If OneDrive or another program briefly locks the file, the
write is retried; if it stays locked, the event goes to audit_trail.pending.jsonl
so nothing is lost.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import config
from models import AuditEvent

_lock = threading.Lock()


def trim(value: Any, limit: int = config.AUDIT_TEXT_CHARS) -> Any:
    """Keep audit entries readable: long strings are cut, everything else passes through."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [+{len(value) - limit} chars]"
    return value


def _append(path, line: bytes) -> None:
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
    """Append one event to the audit trail."""
    line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    path = config.AUDIT_PATH
    with _lock:
        for attempt in range(8):
            try:
                _append(path, line)
                return
            except PermissionError:
                time.sleep(0.25 * (attempt + 1))
        with open(path.with_suffix(".pending.jsonl"), "ab") as f:
            f.write(line + b"\n")
