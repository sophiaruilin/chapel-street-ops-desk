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

# Tools that move money. They pause the run until a human approves in the terminal.
PAY_TOOLS = frozenset({"pay_invoice", "pay_rent"})


class ApprovalRequest(BaseModel):
    """What the human sees before a payment runs."""

    agent: Role
    tool: str
    args: dict[str, Any]
    tool_call_id: str


class ApprovalDecision(BaseModel):
    """The human's answer. approved_by is the approver's own name, typed by them."""

    approved: bool
    approved_by: str | None = None
    reason: str = ""
    queued_approval_id: str | None = None  # dashboard runs: prepared, waiting for a human click


Approver = Callable[[ApprovalRequest], Awaitable[ApprovalDecision]]


class AuditEvent(BaseModel):
    """One line in output/audit_trail.json (one agent-loop step or one control event)."""

    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    team_run_id: str
    agent_run_id: str | None = None
    agent: Role | None = None
    depth: int | None = None
    chain: list[Role] = Field(default_factory=list)
    step: int | None = None
    event: str                    # team_start, agent_start, model_request, model_response,
                                  # delegation, delegation_refused, approval, agent_end, team_end, error
    detail: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int] | None = None


@dataclass
class TeamState:
    """Shared by every agent in one team run (counters, budget, approver)."""

    team_run_id: str
    approver: Approver
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


class PendingApproval(BaseModel):
    """A payment an agent prepared during a dashboard run. Only POST /api/approvals/{id}/approve pays it."""

    id: str
    created_ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    team_run_id: str
    ticket_id: int | None = None
    agent: Role
    tool: str                      # pay_invoice or pay_rent
    args: dict[str, Any]           # invoice_id/lease_id + account (never approved_by)
    status: Literal["pending", "approved", "declined", "failed"] = "pending"
    approved_by: str | None = None
    decided_ts: str | None = None
    reason: str | None = None
    result: dict[str, Any] | None = None


class TeamRunResult(BaseModel):
    """What one full team run returns to the caller."""

    team_run_id: str
    report: str
    delegations: int
    requests: int
    total_tokens: int
