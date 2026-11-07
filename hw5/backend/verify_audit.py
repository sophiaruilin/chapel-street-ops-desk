"""Check that output/audit_trail.json hasn't been edited since it was written.

Run from hw5/backend/:  python verify_audit.py   (exit code 0 = intact, 1 = broken)

Every chained event must satisfy hash == sha256(prev_hash + canonical JSON) and
prev_hash == the hash of the event before it. Events from before the chain
existed (no hash) are counted and reported, not judged.
"""

from __future__ import annotations

import json
import sys

import config
from audit import anchor_hash, event_hash


def verify(path=None) -> tuple[bool, str]:
    path = path or config.AUDIT_PATH
    events = json.loads(open(path, encoding="utf-8").read())
    prev_event = None
    chained = legacy = 0
    for i, e in enumerate(events):
        if not e.get("hash"):
            legacy += 1
            prev_event = e
            continue
        expected_prev = "genesis" if prev_event is None else (prev_event.get("hash") or anchor_hash(prev_event))
        if e.get("prev_hash") != expected_prev:
            return False, f"event {i}: prev_hash does not match the event before it (inserted or deleted?)"
        if event_hash(e["prev_hash"], e) != e["hash"]:
            return False, f"event {i}: contents changed after it was written"
        chained += 1
        prev_event = e
    return True, f"intact: {chained} chained events verified, {legacy} older unchained events"


if __name__ == "__main__":
    ok, msg = verify()
    print(("OK " if ok else "BROKEN ") + msg)
    sys.exit(0 if ok else 1)
