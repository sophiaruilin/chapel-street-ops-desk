"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field
from pydantic_ai.usage import RunUsage

Role = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
ROLES: tuple[Role, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

# Tools that move money or set a price. Calling one pauses the run; the harness prepares an
# approval in the database (amount frozen) and only a human decision lets it execute.
APPROVAL_TOOLS = frozenset({"pay_invoice", "pay_rent", "order_stock", "set_bulk_price"})


class ApprovalRequest(BaseModel):
    """What the human sees before anything is paid, ordered or priced (amount frozen in the DB)."""

    agent: Role
    tool: str
    args: dict[str, Any]
    tool_call_id: str
    approval_id: str
    kind: str                   # payment | purchase | price
    payee: str | None = None
    amount: float
    memo: str | None = None
    needs_two_approvers: bool = False


class ApprovalDecision(BaseModel):
    """The human's answer. approved_by is the approver's own name, typed by them."""

    approved: bool = False
    approved_by: str | None = None
    co_approver: str | None = None  # second, different person when the amount needs two signatures
    reason: str = ""
    queued: bool = False        # dashboard runs: left in the signature tray for a person


Approver = Callable[[ApprovalRequest], Awaitable[ApprovalDecision]]


class AuditEvent(BaseModel):
    """One line in output/audit_trail.json (one agent-loop step or one control event).

    `prev_hash` / `hash` chain every event to the one before it (sha256), so any later
    edit to the trail is detectable with backend/verify_audit.py.
    """

    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    team_run_id: str
    agent_run_id: str | None = None
    agent: Role | None = None
    depth: int | None = None
    chain: list[Role] = Field(default_factory=list)
    step: int | None = None
    event: str                    # team_start, agent_start, model_request, model_response, delegation,
                                  # delegation_refused, approval_*, payment_*, agent_end, team_end, error
    detail: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int] | None = None
    prev_hash: str | None = None
    hash: str | None = None


@dataclass
class TeamState:
    """Shared by every agent in one team run (counters, budget, approver, the ticket's context)."""

    team_run_id: str
    approver: Approver
    ticket_id: int | None = None
    context_packet: str = ""      # compact JSON from get_ticket_context, verified at run start
    usage: RunUsage = field(default_factory=RunUsage)
    delegations: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class TeamDeps:
    """Per-agent-run dependencies: who I am, how deep I am, and the shared team state."""

    role: Role
    depth: int
    chain: list[Role]
    agent_run_id: str
    team: TeamState
    delegations_used: int = 0                              # this agent run's own hand-offs
    seen_tool_calls: set[str] = field(default_factory=set)  # de-duplicates replayed calls in the audit


class TeamRunResult(BaseModel):
    """What one full team run returns to the caller."""

    team_run_id: str
    ticket_id: int | None = None
    report: str
    delegations: int
    requests: int
    total_tokens: int
