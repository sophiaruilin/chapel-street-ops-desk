"""Campus Customs ops desk API for the React dashboard.

Run from hw5/backend/:
    uvicorn main:app --reload --port 8000      (with hw5/.venv activated)
API docs: http://localhost:8000/docs

All shop data goes through the campus-customs-ops MCP server (one stdio
client for the API, and the agents' own MCP connection during runs). Agents
only PREPARE payments during dashboard runs; POST /api/approvals/{id}/approve
is the only thing that moves cash, and only after a human clicks Approve.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel, Field

import approvals
import audit
from agents.team import build_task, run_team
from config import AUDIT_PATH, MCP_SERVER_PYTHON, MCP_SERVER_SCRIPT, MODEL_NAME
from models import ApprovalDecision, ApprovalRequest, AuditEvent, PendingApproval
from reset_db import reset_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ MCP client
class ShopMCP:
    """One long-lived MCP client for the API routes (the agents open their own)."""

    def __init__(self) -> None:
        self.client = Client(StdioTransport(command=str(MCP_SERVER_PYTHON), args=[str(MCP_SERVER_SCRIPT)],
                                            cwd=str(MCP_SERVER_SCRIPT.parent)))
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


app = FastAPI(title="Campus Customs ops desk", version="1.0", lifespan=lifespan)
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


async def _run_ticket(run: RunState) -> None:
    async def dashboard_approver(req: ApprovalRequest) -> ApprovalDecision:
        item = approvals.add(team_run_id=run.team_run_id, ticket_id=run.ticket_id,
                             agent=req.agent, tool=req.tool, args=req.args)
        return ApprovalDecision(approved=False, queued_approval_id=item.id,
                                reason="queued for human approval on the dashboard")

    try:
        result = await run_team(build_task([run.ticket_id]), dashboard_approver, team_run_id=run.team_run_id)
        run.status, run.report = "finished", result.report
        run.delegations, run.requests, run.total_tokens = result.delegations, result.requests, result.total_tokens
    except Exception as exc:  # recorded for the dashboard; the team run already logged it to the audit trail
        run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
    run.finished = _now()


def _human_event(event: str, team_run_id: str, detail: dict[str, Any]) -> None:
    audit.record(AuditEvent(team_run_id=team_run_id, event=event, detail=detail))


# ------------------------------------------------------------------ routes
@app.get("/api/health")
async def health():
    return {"ok": True, "model": MODEL_NAME, "running": _running() is not None}


@app.get("/api/tickets")
async def list_tickets():
    """The tickets and whether each is open or resolved."""
    data = await shop.call("list_tickets")
    pending = [p for p in approvals.all_items() if p.status == "pending"]
    return [{
        "id": t["id"], "type": t["type"], "subject": t["subject"], "requester": t["requester"],
        "sku": t["sku"], "size": t["size"], "qty": t["qty"],
        "status": t["status"],                                   # open / waiting_approval / blocked / resolved
        "state": "resolved" if t["status"] == "resolved" else "open",
        "pending_approvals": sum(1 for p in pending if p.ticket_id == t["id"]),
    } for t in data["tickets"]]


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int):
    """One ticket in full, including drafts saved in its notes."""
    data = await shop.call("get_ticket", {"ticket_id": ticket_id})
    if not data.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}")
    return data["ticket"]


class StatusBody(BaseModel):
    status: Literal["open", "waiting_approval", "blocked", "resolved"]
    by: str = "dashboard"


@app.post("/api/tickets/{ticket_id}/status")
async def set_ticket_status(ticket_id: int, body: StatusBody):
    """A human moves a ticket on the board (for example closes it as resolved after approving its payment)."""
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
        said, tools = f"Asked {d.get('to')}: {d.get('request')}", [{"tool": "ask_teammate", "args": {"teammate": d.get("to")}}]
    elif ev == "delegation_refused":
        said = f"Delegation to {d.get('to')} refused: {d.get('reason')}"
    elif ev in ("approval_queued", "paused_for_approval", "approval"):
        said = f"Payment needs human approval: {d.get('tool') or d.get('tools')} {d.get('args', '')}".strip()
    elif ev in ("payment_approved", "payment_refused", "payment_declined", "db_reset", "ticket_status"):
        said = d.get("message")
    elif ev in ("team_start", "team_end", "error"):
        said = d.get("task") or d.get("message") or (f"Run finished, {d.get('delegations')} delegations"
                                                     if ev == "team_end" else None)
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
async def list_approvals(status: Literal["pending", "approved", "declined", "failed"] | None = None):
    """Payments the agents prepared, waiting for (or decided by) a human.

    Pending items carry a `preview` (payee, amount, memo, due date) looked up through
    MCP, so the human sees exactly what they are signing for.
    """
    items = [p for p in approvals.all_items() if status is None or p.status == status]
    out = []
    for p in items:
        row = p.model_dump(mode="json")
        row["preview"] = await _preview(p) if p.status == "pending" else None
        out.append(row)
    return out


async def _preview(p: PendingApproval) -> dict[str, Any] | None:
    if p.tool == "pay_rent":
        data = await shop.call("get_lease_rent_and_cash", {"lease_id": p.args.get("lease_id")})
        if data.get("found"):
            lease = data["lease"]
            return {"payee": lease["landlord"], "amount": lease["monthly_rent"], "due": lease["next_due"],
                    "memo": f"Rent · {lease['space_name']} (lease {lease['id']})"}
    if p.tool == "pay_invoice":
        data = await shop.call("list_open_invoices", {})
        inv = next((i for i in data["invoices"] if i["id"] == p.args.get("invoice_id")), None)
        if inv:
            return {"payee": inv["vendor_name"], "amount": inv["amount"], "due": inv["due_date"],
                    "memo": f"Invoice {inv['id']} · {inv['description']}"}
    return None


class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=2, description="Full name of the human approving")


class DeclineBody(BaseModel):
    reason: str = ""


def _pending_or_404(approval_id: str) -> PendingApproval:
    item = approvals.get(approval_id)
    if item is None:
        raise HTTPException(404, f"No approval {approval_id}")
    if item.status != "pending":
        raise HTTPException(409, f"Approval {approval_id} is already {item.status}")
    return item


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApproveBody):
    """A human approved: this is the only route that actually pays (and changes cash)."""
    item = _pending_or_404(approval_id)
    result = await shop.call(item.tool, {**item.args, "approved_by": body.approved_by.strip()})
    item.approved_by, item.decided_ts, item.result = body.approved_by.strip(), _now(), result
    if result.get("paid"):
        item.status = "approved"
        msg = (f"{item.approved_by} approved {item.tool} {item.args}: paid {result['amount']:.2f}, "
               f"{result['account']} balance {result['balance_before']:.2f} -> {result['balance_after']:.2f}")
        event = "payment_approved"
    else:
        item.status, item.reason = "failed", result.get("message")
        msg = f"{item.approved_by} approved {item.tool} {item.args}, but the server refused: {item.reason}"
        event = "payment_refused"
    approvals.update(item)
    _human_event(event, item.team_run_id, {"approval_id": item.id, "message": msg, "result": result})
    return {"paid": bool(result.get("paid")), "approval": item}


@app.post("/api/approvals/{approval_id}/decline")
async def decline(approval_id: str, body: DeclineBody):
    """A human declined: nothing is paid."""
    item = _pending_or_404(approval_id)
    item.status, item.decided_ts, item.reason = "declined", _now(), body.reason or "declined on the dashboard"
    approvals.update(item)
    _human_event("payment_declined", item.team_run_id,
                 {"approval_id": item.id, "message": f"Declined {item.tool} {item.args}: {item.reason}"})
    return {"paid": False, "approval": item}


@app.get("/api/cash")
async def cash():
    """Current checking balance from cash_accounts."""
    data = await shop.call("get_cash_balances")
    checking = next((a for a in data["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account")
    return {"account": "checking", "balance": checking["balance"], "as_of": checking["date"],
            "date_today": data["date_today"]}


@app.post("/api/reset")
async def reset():
    """Reset the working DB to the original values and clear queued payments (for a fresh run)."""
    if (busy := _running()) is not None:
        raise HTTPException(409, f"Run {busy.team_run_id} is still running; wait for it to finish")
    reset_db()
    cleared = approvals.clear()
    _human_event("db_reset", "dashboard",
                 {"message": f"Database reset to original values; {cleared} queued payment(s) cleared."})
    return {"reset": True, "cleared_approvals": cleared, "cash": await cash()}
