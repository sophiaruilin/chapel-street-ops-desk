"""Campus Customs ops desk API for the React dashboard.

Run from hw5/backend/:
    uvicorn main:app --reload --port 8000      (with hw5/.venv activated)
API docs: http://localhost:8000/docs

All shop data goes through the campus-customs-ops MCP server (one stdio
client for the API; each agent run opens its own). During dashboard runs the
agents only PREPARE approvals: the MCP server stores each one in the database
with its payee and amount frozen. POST /api/approvals/{id}/approve is the only
thing that executes one, and only with the desk PIN and a human name; the MCP
server then pays (or orders, or records a price) exactly once, and only if the
records still match what was approved. Nothing here touches a real bank: the
"checking account" is a number in the practice database.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel, Field

import audit
from agents.team import run_team
from config import (
    APPROVAL_PIN,
    APPROVERS,
    AUDIT_PATH,
    MCP_SERVER_PYTHON,
    MCP_SERVER_SCRIPT,
    MODEL_NAME,
    mcp_env,
)
from models import ApprovalDecision, ApprovalRequest, AuditEvent
from reset_db import reset_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ MCP client
class ShopMCP:
    """One long-lived MCP client for the API routes (agent runs open their own)."""

    def __init__(self) -> None:
        self.client = Client(StdioTransport(command=str(MCP_SERVER_PYTHON), args=[str(MCP_SERVER_SCRIPT)],
                                            cwd=str(MCP_SERVER_SCRIPT.parent), env=mcp_env()))
        self.lock = asyncio.Lock()

    async def call(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self.lock:
            res = await self.client.call_tool(tool, args or {}, raise_on_error=False)
        if res.is_error:
            text = " ".join(getattr(c, "text", "") for c in res.content)
            raise HTTPException(502, f"MCP tool {tool} failed: {text}")
        if res.structured_content is not None:
            return res.structured_content
        return json.loads(res.content[0].text)


shop = ShopMCP()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with shop.client:
        yield


app = FastAPI(title="Campus Customs ops desk", version="2.0", lifespan=lifespan)
# The React desk (Vite) runs on port 5173; the browser may only call these routes from there.
VITE_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(CORSMiddleware, allow_origins=VITE_ORIGINS, allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ run state
class RunState(BaseModel):
    team_run_id: str
    ticket_id: int
    status: Literal["running", "finished", "failed"] = "running"
    started: str = Field(default_factory=_now)
    finished: str | None = None
    report: str | None = None
    error: str | None = None
    delegations: int | None = None
    requests: int | None = None
    total_tokens: int | None = None


RUNS: dict[str, RunState] = {}
_current: dict[str, str | None] = {"run_id": None}


def _running() -> RunState | None:
    run_id = _current["run_id"]
    run = RUNS.get(run_id) if run_id else None
    return run if run and run.status == "running" else None


async def _queue_in_tray(req: ApprovalRequest) -> ApprovalDecision:
    """Dashboard runs never execute anything: the prepared approval waits in the signature tray."""
    return ApprovalDecision(queued=True, reason="left in the dashboard signature tray for a person")


async def _run_ticket(run: RunState) -> None:
    try:
        result = await run_team(run.ticket_id, _queue_in_tray, team_run_id=run.team_run_id, label="dashboard")
        run.status, run.report = "finished", result.report
        run.delegations, run.requests, run.total_tokens = result.delegations, result.requests, result.total_tokens
        await _settle_ticket(run.ticket_id, run.team_run_id)
    except Exception as exc:  # recorded for the dashboard; the team run already logged it to the audit trail
        run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
    run.finished = _now()


def _human_event(event: str, team_run_id: str, detail: dict[str, Any]) -> None:
    audit.record(AuditEvent(team_run_id=team_run_id or "dashboard", event=event, detail=detail))


async def _settle_ticket(ticket_id: int | None, team_run_id: str | None) -> str | None:
    """Resolve a ticket that was only waiting on approvals once none are left pending (and none declined)."""
    if ticket_id is None:
        return None
    t = await shop.call("get_ticket", {"ticket_id": ticket_id})
    if not t.get("found") or t["ticket"]["status"] != "waiting_approval":
        return None
    items = (await shop.call("list_approvals", {"ticket_id": ticket_id}))["approvals"]
    if not items or any(a["status"] in ("pending", "partially_approved") for a in items):
        return None
    if any(a["status"] in ("declined", "failed") for a in items):
        new = "blocked"
    else:
        new = "resolved"
    await shop.call("update_ticket_status", {"ticket_id": ticket_id, "status": new})
    _human_event("ticket_status", team_run_id or "dashboard", {
        "ticket_id": ticket_id, "message": f"Desk set ticket {ticket_id}: waiting_approval -> {new} "
                                           f"(every approval for it is {'signed' if new == 'resolved' else 'decided'})"})
    return new


def _check_signer(name: str, pin: str) -> str:
    """The desk PIN (from .env) plus an optional allow-list of approver names."""
    if not APPROVAL_PIN:
        raise HTTPException(403, "Approvals are locked: set DESK_APPROVAL_PIN in .env and restart the backend.")
    if not hmac.compare_digest(pin.strip(), APPROVAL_PIN):
        raise HTTPException(403, "Wrong desk PIN.")
    name = name.strip()
    if APPROVERS and name.lower() not in {a.lower() for a in APPROVERS}:
        raise HTTPException(403, f"{name} is not on the approver list (DESK_APPROVERS).")
    return name


# ------------------------------------------------------------------ routes
@app.get("/", include_in_schema=False)
async def root():
    """This is the API; the desk people use is the React board on port 5173."""
    return RedirectResponse("http://localhost:5173")


@app.get("/api/health")
async def health():
    return {"ok": True, "model": MODEL_NAME, "running": _running() is not None,
            "approvals_unlocked": bool(APPROVAL_PIN), "practice_ledger": True}


@app.get("/api/tickets")
async def list_tickets():
    """The tickets and whether each is open or resolved."""
    data = await shop.call("list_tickets")
    pending = [a for a in (await shop.call("list_approvals"))["approvals"]
               if a["status"] in ("pending", "partially_approved")]
    return [{
        "id": t["id"], "type": t["type"], "subject": t["subject"], "requester": t["requester"],
        "sku": t["sku"], "size": t["size"], "qty": t["qty"],
        "status": t["status"],                                   # open / waiting_approval / blocked / resolved
        "state": "resolved" if t["status"] == "resolved" else "open",
        "pending_approvals": sum(1 for p in pending if p["ticket_id"] == t["id"]),
    } for t in data["tickets"]]


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int):
    """One ticket in full, with its customer and internal drafts listed separately."""
    data = await shop.call("get_ticket", {"ticket_id": ticket_id})
    if not data.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}")
    return {**data["ticket"], "drafts": data["drafts"]}


class StatusBody(BaseModel):
    status: Literal["open", "waiting_approval", "blocked", "resolved"]
    by: str = "dashboard"


@app.post("/api/tickets/{ticket_id}/status")
async def set_ticket_status(ticket_id: int, body: StatusBody):
    """A human moves a ticket on the board (for example closes it as resolved)."""
    result = await shop.call("update_ticket_status", {"ticket_id": ticket_id, "status": body.status})
    if not result.get("updated"):
        raise HTTPException(404 if "No ticket" in result.get("message", "") else 400, result.get("message"))
    _human_event("ticket_status", "dashboard", {
        "ticket_id": ticket_id, "message": f"{body.by} set ticket {ticket_id}: {result['from']} -> {result['to']}"})
    return result


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int):
    """Start the agent team on one ticket (runs in the background; poll /api/events and /api/runs/{id})."""
    if (busy := _running()) is not None:
        raise HTTPException(409, f"Run {busy.team_run_id} on ticket {busy.ticket_id} is still running")
    found = await shop.call("get_ticket", {"ticket_id": ticket_id})
    if not found.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}")
    run = RunState(team_run_id=uuid.uuid4().hex[:10], ticket_id=ticket_id)
    RUNS[run.team_run_id] = run
    _current["run_id"] = run.team_run_id
    asyncio.create_task(_run_ticket(run))
    return run


@app.get("/api/runs/latest")
async def latest_run() -> RunState | None:
    """The most recent run since the server started (null if none yet)."""
    run_id = _current["run_id"]
    return RUNS[run_id] if run_id else None


@app.get("/api/tickets/{ticket_id}/last_run")
async def last_run_for_ticket(ticket_id: int) -> RunState | None:
    """The ticket's most recent team run, rebuilt from the audit trail, so the board survives restarts
    (and a grader who clones the repo sees every run that's in output/audit_trail.json)."""
    raw = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
    starts = [e for e in raw if e["event"] == "team_start" and (e.get("detail") or {}).get("ticket_id") == ticket_id]
    if not starts:
        return None
    rid = starts[-1]["team_run_id"]
    if rid in RUNS:
        return RUNS[rid]
    ev = [e for e in raw if e["team_run_id"] == rid]
    end = next((e for e in reversed(ev) if e["event"] == "team_end"), None)
    report = next((e["detail"].get("output") for e in reversed(ev)
                   if e["event"] == "agent_end" and e.get("depth") == 0), None)
    usage = next((e["usage"] for e in reversed(ev) if e.get("usage")), {}) or {}
    return RunState(team_run_id=rid, ticket_id=ticket_id, status="finished" if end else "failed",
                    started=starts[-1]["ts"], finished=end["ts"] if end else None, report=report,
                    error=None if end else "run did not finish (see the audit trail)",
                    delegations=(end or {}).get("detail", {}).get("delegations"),
                    requests=usage.get("requests"), total_tokens=usage.get("total_tokens"))


@app.get("/api/runs/{team_run_id}")
async def get_run(team_run_id: str):
    if team_run_id not in RUNS:
        raise HTTPException(404, f"No run {team_run_id} since the server started")
    return RUNS[team_run_id]


def _simplify(index: int, e: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one audit event into what the board shows: who said what, which tools they used."""
    d, ev = e.get("detail", {}), e["event"]
    said, tools, tool_results = None, [], []
    if ev == "model_response":
        said = d.get("text")
        tools = [{"tool": c["tool"], "args": c["args"]} for c in d.get("tool_calls", [])]
    elif ev == "model_request":
        tool_results = [{"tool": r["tool"], "result": r["content"]} for r in d.get("tool_returns", [])]
        if not tool_results:
            return None  # the opening prompt; nothing new for the board
    elif ev == "agent_start":
        said = f"Received: {d.get('request')}"
    elif ev == "agent_end":
        said = d.get("output")
    elif ev == "delegation":
        said = f"Asked {d.get('to')}: {d.get('request')}"
        tools = [{"tool": "ask_teammate", "args": {"teammate": d.get("to")}}]
    elif ev == "delegation_refused":
        said = f"Delegation to {d.get('to')} refused: {d.get('reason')}"
    elif ev in ("approval_prepared", "approval_queued", "approval_refused", "approval_granted",
                "approval_declined", "paused_for_approval", "approval", "approval_first_signature",
                "approval_incomplete"):
        if d.get("payee"):
            said = f"Prepared for a human: {d.get('tool')} · {d.get('payee')} · ${d.get('amount', 0):,.2f}"
        else:
            said = d.get("message") or f"{ev.replace('_', ' ')}: {d.get('tool') or d.get('tools') or ''}"
    elif ev in ("payment_approved", "payment_refused", "payment_declined", "approval_signed", "approval_partly_signed",
                "db_reset", "ticket_status"):
        said = d.get("message")
    elif ev in ("team_start", "team_end", "error"):
        said = d.get("task") or d.get("message") or (f"Run finished, {d.get('delegations')} delegations"
                                                     if ev == "team_end" else f"Run opened ({d.get('label', '')})")
    return {"index": index, "ts": e["ts"], "team_run_id": e["team_run_id"], "agent": e.get("agent"),
            "depth": e.get("depth"), "event": ev, "said": said, "tools": tools, "tool_results": tool_results}


@app.get("/api/events")
async def events(
    limit: int = Query(50, ge=1, le=500),
    since: int | None = Query(None, description="only events with index greater than this"),
    team_run_id: str | None = None,
):
    """Recent agent events (newest last): what each agent said and which tools it used."""
    raw = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
    out = []
    for i, e in enumerate(raw):
        if since is not None and i <= since:
            continue
        if team_run_id and e["team_run_id"] != team_run_id:
            continue
        if (item := _simplify(i, e)) is not None:
            out.append(item)
    return {"total_events": len(raw), "last_index": len(raw) - 1, "events": out[-limit:]}


@app.get("/api/approvals")
async def list_approvals(status: str | None = None):
    """Everything the agents prepared (payments, purchases, prices), with the frozen payee and amount."""
    data = await shop.call("list_approvals", {"status": status} if status else {})
    return [{**a, "preview": {"payee": a["payee"], "amount": a["amount"], "memo": a["memo"], "due": a["due"]},
             "needs_two_approvers": a["kind"] != "price" and a["amount"] > data["second_approver_above"]}
            for a in data["approvals"]]


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=2, description="Full name of the human approving")
    pin: str = Field(min_length=1, description="Desk approval PIN from .env (DESK_APPROVAL_PIN)")


class DeclineBody(BaseModel):
    declined_by: str = Field(min_length=2)
    pin: str = Field(min_length=1)
    reason: str = ""


async def _get_approval(approval_id: str) -> dict:
    items = (await shop.call("list_approvals"))["approvals"]
    item = next((a for a in items if a["id"] == approval_id), None)
    if item is None:
        raise HTTPException(404, f"No approval {approval_id}")
    return item


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApproveBody):
    """A human signs: the ONLY route that executes an approval (pays, orders stock, or approves a price).

    Idempotent: signing an approval that already went through returns the original result.
    """
    name = _check_signer(body.approved_by, body.pin)
    item = await _get_approval(approval_id)
    if item["status"] not in ("pending", "partially_approved", "approved"):
        raise HTTPException(409, f"Approval {approval_id} is already {item['status']}")
    result = await shop.call(item["tool"], {**item["args"], "approval_id": approval_id, "approved_by": name})
    if result.get("done") and not result.get("already_done"):
        what = (f"paid ${result['amount']:,.2f} to {result['payee']}, {result['account']} "
                f"${result['balance_before']:,.2f} -> ${result['balance_after']:,.2f}") if result.get("paid") else \
               f"approved {result.get('memo', item['memo'])}"
        _human_event("approval_signed", item["team_run_id"], {
            "approval_id": approval_id, "ticket_id": item["ticket_id"], "result": result,
            "message": f"{name} signed {item['tool']} ({approval_id}): {what}"})
        await _settle_ticket(item["ticket_id"], item["team_run_id"])
    elif result.get("needs_second_approver"):
        _human_event("approval_partly_signed", item["team_run_id"], {
            "approval_id": approval_id, "message": f"{name} signed first; a second, different approver is needed."})
    elif not result.get("done"):
        _human_event("payment_refused", item["team_run_id"], {
            "approval_id": approval_id, "message": f"{name} signed {item['tool']}, but it was refused: "
                                                   f"{result.get('message')}"})
    return {"done": bool(result.get("done")), "paid": bool(result.get("paid")), "result": result,
            "approval": await _get_approval(approval_id)}


@app.post("/api/approvals/{approval_id}/decline")
async def decline(approval_id: str, body: DeclineBody):
    """A human declines: nothing is paid, ordered or priced."""
    name = _check_signer(body.declined_by, body.pin)
    item = await _get_approval(approval_id)
    result = await shop.call("decline_approval", {"approval_id": approval_id, "declined_by": name,
                                                  "reason": body.reason or "declined on the dashboard"})
    if not result.get("declined"):
        raise HTTPException(409, result.get("message", "Not pending"))
    _human_event("payment_declined", item["team_run_id"], {
        "approval_id": approval_id, "message": f"{name} declined {item['tool']} ({approval_id}): "
                                               f"{body.reason or 'no reason given'}"})
    await _settle_ticket(item["ticket_id"], item["team_run_id"])
    return {"done": False, "approval": await _get_approval(approval_id)}


@app.get("/api/cash")
async def cash():
    """Current checking balance from cash_accounts (a practice ledger: no real money)."""
    data = await shop.call("get_cash_balances")
    checking = next((a for a in data["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account")
    paid = await shop.call("list_payments", {})
    out_of_checking = sum(p["amount"] for p in paid["payments"] if p["account"] == "checking")
    return {"account": "checking", "balance": checking["balance"], "as_of": checking["date"],
            "opening_balance": round(checking["balance"] + out_of_checking, 2),  # cash only goes out
            "paid_out": round(out_of_checking, 2), "date_today": data["date_today"], "practice_ledger": True}


class ResetBody(BaseModel):
    pin: str = Field(min_length=1)


@app.post("/api/reset")
async def reset(body: ResetBody):
    """Reset the working DB to the original values (clears prepared approvals and drafts too). Needs the PIN."""
    if not APPROVAL_PIN or not hmac.compare_digest(body.pin.strip(), APPROVAL_PIN):
        raise HTTPException(403, "Wrong or missing desk PIN.")
    if (busy := _running()) is not None:
        raise HTTPException(409, f"Run {busy.team_run_id} is still running; wait for it to finish")
    reset_db()
    _human_event("db_reset", "dashboard", {"message": "Database reset to original values "
                                                      "(approvals and drafts start empty)."})
    return {"reset": True, "cash": await cash()}
