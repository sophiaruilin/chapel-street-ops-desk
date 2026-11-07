"""The audit trail is append-only and tamper-evident."""

from __future__ import annotations

import json

import audit
import config
from models import AuditEvent
from verify_audit import verify


def test_append_only_and_hash_chain(tmp_path, monkeypatch):
    path = tmp_path / "audit_trail.json"
    monkeypatch.setattr(config, "AUDIT_PATH", path)
    for i in range(5):
        audit.record(AuditEvent(team_run_id="t", event="model_response", detail={"i": i}))
    events = json.loads(path.read_text(encoding="utf-8"))
    assert [e["detail"]["i"] for e in events] == [0, 1, 2, 3, 4]       # appended in order, nothing wiped
    assert events[0]["prev_hash"] == "genesis"
    assert all(events[i]["prev_hash"] == events[i - 1]["hash"] for i in range(1, 5))
    ok, _ = verify(path)
    assert ok


def test_tampering_is_detected(tmp_path, monkeypatch):
    path = tmp_path / "audit_trail.json"
    monkeypatch.setattr(config, "AUDIT_PATH", path)
    for i in range(3):
        audit.record(AuditEvent(team_run_id="t", event="approval_signed", detail={"amount": 840 + i}))
    events = json.loads(path.read_text(encoding="utf-8"))
    events[1]["detail"]["amount"] = 1                                   # someone edits history
    path.write_text(json.dumps(events), encoding="utf-8")
    ok, msg = verify(path)
    assert not ok and "event 1" in msg


def test_chain_anchors_to_older_unhashed_history(tmp_path, monkeypatch):
    path = tmp_path / "audit_trail.json"
    path.write_text(json.dumps([{"team_run_id": "old", "event": "team_start", "detail": {}}]), encoding="utf-8")
    monkeypatch.setattr(config, "AUDIT_PATH", path)
    audit.record(AuditEvent(team_run_id="new", event="team_start"))
    events = json.loads(path.read_text(encoding="utf-8"))
    assert len(events) == 2 and events[1]["prev_hash"] == audit.anchor_hash(events[0])
    assert verify(path)[0]
