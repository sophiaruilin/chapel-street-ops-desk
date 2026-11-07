"""The agent loop end to end with scripted models (no API calls), over the real MCP server.

Checks: the ticket context is fetched in code and handed to every teammate, a
specialist's delegation budget is enforced, an approval tool only PREPARES an
approval (amount frozen in the DB) on dashboard runs, the terminal path executes
it exactly once, and replayed tool calls are logged once in the audit trail.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3

import config
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from agents import mcp_link
from agents.team import get_agent, run_team
from models import ApprovalDecision

SEEN_PROMPTS: dict[str, str] = {}


def _returns(messages):
    return [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)] if messages else []


def _first_prompt(messages) -> str:
    for p in messages[0].parts:
        if isinstance(p, UserPromptPart):
            return str(p.content)
    return ""


def boss(messages, info):
    SEEN_PROMPTS.setdefault("boss", _first_prompt(messages))
    r = _returns(messages)
    if not r:
        return ModelResponse(parts=[ToolCallPart("ask_teammate", {
            "teammate": "accounting", "request": "Prepare payment of invoice 501 for ticket 101.",
            "known_facts": "invoice 501 open, $840, 3 days overdue (context packet)"})])
    return ModelResponse(parts=[TextPart("BOSS: " + str(r[0].content)[:300])])


def accounting(messages, info):
    SEEN_PROMPTS.setdefault("accounting", _first_prompt(messages))
    r = _returns(messages)
    if not r:
        return ModelResponse(parts=[
            ToolCallPart("pay_invoice", {"invoice_id": 501, "account": "checking"}),
            ToolCallPart("ask_teammate", {"teammate": "inventory", "request": "stock?"}),
            ToolCallPart("ask_teammate", {"teammate": "facilities", "request": "lease?"}),
        ])
    return ModelResponse(parts=[TextPart("ACCT: " + " | ".join(str(p.content)[:200] for p in r))])


def inventory(messages, info):
    return ModelResponse(parts=[TextPart("INV: 0 in Aisle B (from packet)")])


def _run(approver):
    # Each asyncio.run is a new event loop, so start from a fresh MCP connection and fresh agents.
    mcp_link._shared = None
    get_agent.cache_clear()

    async def go():
        with contextlib.ExitStack() as st:
            st.enter_context(get_agent("boss").override(model=FunctionModel(boss)))
            st.enter_context(get_agent("accounting").override(model=FunctionModel(accounting)))
            st.enter_context(get_agent("inventory").override(model=FunctionModel(inventory)))
            return await run_team(101, approver, label="test")
    return asyncio.run(go())


def _events(run_id):
    return [e for e in json.loads(config.AUDIT_PATH.read_text(encoding="utf-8")) if e["team_run_id"] == run_id]


def test_dashboard_run_only_prepares_and_context_is_shared(shared_db):
    async def tray(req):
        assert req.amount == 840.0 and req.payee == "Bulldog Print Co"   # frozen by the server
        return ApprovalDecision(queued=True)

    res = _run(tray)
    c = sqlite3.connect(shared_db)
    assert c.execute("SELECT balance FROM cash_accounts").fetchone()[0] == 3400.0   # nothing paid
    assert c.execute("SELECT tool, amount, status FROM approvals").fetchall() == [("pay_invoice", 840.0, "pending")]
    # the desk fetched the ticket context in code and handed it to the Boss and to the teammate
    assert "Ticket context packet" not in SEEN_PROMPTS["boss"] and '"stock_requested_size"' in SEEN_PROMPTS["boss"]
    assert "Ticket context packet" in SEEN_PROMPTS["accounting"]
    assert "invoice 501 open, $840" in SEEN_PROMPTS["accounting"]                   # known_facts passed along
    ev = _events(res.team_run_id)
    kinds = [e["event"] for e in ev]
    assert "approval_prepared" in kinds and "approval_queued" in kinds
    # specialist budget = 1: accounting's second ask was refused
    refused = [e for e in ev if e["event"] == "delegation_refused"]
    assert any("budget" in e["detail"]["reason"] for e in refused)
    # replayed tool calls are logged once
    ids = [c["tool_call_id"] for e in ev if e["event"] == "model_response" for c in e["detail"]["tool_calls"]]
    assert len(ids) == len(set(ids))


def test_terminal_approval_executes_exactly_once(shared_db):
    async def human(req):
        return ApprovalDecision(approved=True, approved_by="Sophia Lin")

    _run(human)
    c = sqlite3.connect(shared_db)
    assert c.execute("SELECT balance FROM cash_accounts").fetchone()[0] == 2560.0
    assert c.execute("SELECT COUNT(*), MAX(approved_by) FROM payments").fetchone() == (1, "Sophia Lin")
    assert c.execute("SELECT status FROM approvals").fetchone()[0] == "approved"
