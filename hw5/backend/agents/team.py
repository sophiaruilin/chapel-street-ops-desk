"""The Campus Customs agent team and its agent loop.

Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer
Service) share one model and one MCP server. Every agent has `ask_teammate`,
so any agent can delegate to any other (full connectivity), but the design is
hub-and-spoke by default to keep runs cheap:

  - The desk fetches the ticket's whole context in CODE (one MCP call,
    get_ticket_context) before the Boss's first turn, and attaches it to every
    hand-off as verified facts, so nobody re-fetches what the team already knows.
  - Code-level routing suggests the specialists for each ticket type (ROUTES).
  - The Boss may delegate up to MAX_DELEGATIONS times per ticket; a specialist
    run may ask at most SPECIALIST_DELEGATIONS teammate(s).
  - No asking yourself or bouncing a request back to your caller; MAX_DEPTH
    levels; one team-wide request/token budget per ticket.

`run_role` is the agent loop: it steps through agent.iter(), writes every step
to output/audit_trail.json (replayed tool calls are logged once), and when an
approval tool pauses the run it prepares the approval in the database (amount
frozen by the MCP server), asks the human (terminal) or leaves it in the
dashboard's signature tray, then resumes the same run with the outcome.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Any

from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    DeferredToolResults,
    RunContext,
    ToolApproved,
    ToolDenied,
)
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import UsageLimits

import audit
from agents.mcp_link import HIDDEN_ARGS, mcp_call, shop_mcp, toolset_for
from agents.roles import DEFAULT_ROUTE, ROLE_SUMMARY, ROUTES
from config import (
    MAX_APPROVAL_ROUNDS,
    MAX_DELEGATIONS,
    MAX_DEPTH,
    PROMPTS_DIR,
    SPECIALIST_DELEGATIONS,
    TEAM_REQUEST_LIMIT,
    TEAM_TOTAL_TOKENS_LIMIT,
    build_model,
)
from models import (
    ROLES,
    ApprovalRequest,
    Approver,
    AuditEvent,
    Role,
    TeamDeps,
    TeamRunResult,
    TeamState,
)


# ---------------------------------------------------------------- audit helpers
def _usage(deps: TeamDeps) -> dict[str, int]:
    u = deps.team.usage
    return {"requests": u.requests, "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens, "total_tokens": u.total_tokens}


def _log(deps: TeamDeps, event: str, detail: dict[str, Any] | None = None, step: int | None = None) -> None:
    audit.record(AuditEvent(
        team_run_id=deps.team.team_run_id, agent_run_id=deps.agent_run_id, agent=deps.role,
        depth=deps.depth, chain=list(deps.chain), step=step, event=event,
        detail=detail or {}, usage=_usage(deps),
    ))


def _as_text(content: Any) -> str:
    return content if isinstance(content, str) else json.dumps(content, default=str, ensure_ascii=False)


def _audit_node(deps: TeamDeps, step: int, node: Any) -> None:
    """Record one step of the agent loop. A tool call replayed when a paused run resumes is logged once."""
    if Agent.is_model_request_node(node):
        returns, retries = [], []
        for part in node.request.parts:
            if isinstance(part, ToolReturnPart):
                returns.append({"tool": part.tool_name, "tool_call_id": part.tool_call_id,
                                "content": audit.trim(_as_text(part.content))})
            elif isinstance(part, RetryPromptPart):
                retries.append({"tool": part.tool_name, "content": audit.trim(_as_text(part.content))})
        if returns or retries or step == 1:
            _log(deps, "model_request", {"tool_returns": returns, "retries": retries}, step)
    elif Agent.is_call_tools_node(node):
        resp = node.model_response
        calls = []
        for p in resp.parts:
            if isinstance(p, ToolCallPart) and p.tool_call_id not in deps.seen_tool_calls:
                deps.seen_tool_calls.add(p.tool_call_id)
                calls.append({"tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args_as_dict()})
        text = "".join(p.content for p in resp.parts if isinstance(p, TextPart))
        has_calls = any(isinstance(p, ToolCallPart) for p in resp.parts)
        if has_calls and not calls and not text:
            return  # the same response replayed on resume: already in the trail
        _log(deps, "model_response", {
            "model": resp.model_name,
            "tool_calls": calls,
            "text": audit.trim(text) if text else None,
            "used_reasoning": any(isinstance(p, ThinkingPart) for p in resp.parts),
            "request_tokens": {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
        }, step)


# ---------------------------------------------------------------- delegation
def _handoff(request: str, known_facts: str, packet: str) -> str:
    parts = [request.strip()]
    if known_facts.strip():
        parts.append("Facts your teammate already verified with tools in this run (treat as verified, "
                     f"do not re-fetch):\n{known_facts.strip()}")
    if packet:
        parts.append("Ticket context packet (fetched by the desk from MCP at the start of this run; "
                     f"verified, do not re-fetch these facts):\n{packet}")
    return "\n\n".join(parts)


async def ask_teammate(ctx: RunContext[TeamDeps], teammate: Role, request: str, known_facts: str = "") -> str:
    """Delegate a focused request to a teammate and get their report back.

    teammate: one of boss, inventory, accounting, facilities, customer_service.
    request: a short, self-contained request naming the ticket id and exact
      SKU, size, quantity, lease id or invoice id.
    known_facts: facts you already verified with tools in this run (numbers and
      their source), so the teammate doesn't fetch them again.
    """
    me = ctx.deps
    caller = me.chain[-2] if len(me.chain) >= 2 else None
    budget = MAX_DELEGATIONS if me.role == "boss" else SPECIALIST_DELEGATIONS
    refusal = None
    if teammate not in ROLES:
        refusal = f"Unknown teammate '{teammate}'."
    elif teammate == me.role:
        refusal = "You can't delegate to yourself."
    elif teammate == caller:
        refusal = f"{teammate} is the one who asked you. Put what you need in your reply to them instead."
    elif me.depth + 1 > MAX_DEPTH:
        refusal = "Delegation depth limit reached. Answer with the facts you have and say what's missing."
    elif me.delegations_used >= budget:
        refusal = (f"Your delegation budget ({budget}) is used. Answer with the facts you have (the context "
                   "packet is already verified) and say what's missing.")
    else:
        async with me.team.lock:
            if me.team.delegations >= MAX_DELEGATIONS:
                refusal = f"Team delegation budget ({MAX_DELEGATIONS}) used up. Answer with what you have."
            else:
                me.team.delegations += 1
                me.delegations_used += 1
    if refusal:
        _log(me, "delegation_refused", {"to": teammate, "request": audit.trim(request), "reason": refusal})
        return "Refused: " + refusal

    child = TeamDeps(role=teammate, depth=me.depth + 1, chain=[*me.chain, teammate],
                     agent_run_id=uuid.uuid4().hex[:8], team=me.team)
    _log(me, "delegation", {"to": teammate, "child_agent_run_id": child.agent_run_id,
                            "request": audit.trim(request), "known_facts": audit.trim(known_facts)})
    return await run_role(child, _handoff(request, known_facts, me.team.context_packet))


# ---------------------------------------------------------------- agents
def _instructions(role: Role) -> str:
    rules = (PROMPTS_DIR / "shop_rules.md").read_text(encoding="utf-8")
    text = (PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    return (text.replace("{shop_rules}", rules).replace("{max_delegations}", str(MAX_DELEGATIONS))
            .replace("{specialist_delegations}", str(SPECIALIST_DELEGATIONS)))


@lru_cache(maxsize=None)
def get_agent(role: Role) -> Agent[TeamDeps, str | DeferredToolRequests]:
    model, settings = build_model()
    return Agent(
        model,
        name=role,
        deps_type=TeamDeps,
        output_type=[str, DeferredToolRequests],  # DeferredToolRequests = paused for a human
        instructions=_instructions(role),
        model_settings=settings,
        toolsets=[toolset_for(role)],
        tools=[ask_teammate],
        retries=2,
    )


# ---------------------------------------------------------------- human approval
async def _ask_human(deps: TeamDeps, paused: DeferredToolRequests) -> DeferredToolResults:
    """Prepare each paused action as an approval (amount frozen in the DB), then get the human's call."""
    results = DeferredToolResults()
    for call in paused.approvals:
        args = {k: v for k, v in call.args_as_dict().items() if k not in HIDDEN_ARGS}
        prep = await mcp_call("create_approval", {"tool": call.tool_name, "args": args,
                                                  "ticket_id": deps.team.ticket_id, "agent": deps.role,
                                                  "team_run_id": deps.team.team_run_id})
        appr = prep.get("approval")
        if appr is None:  # refused up front: not enough cash, vendor on hold, below cost...
            msg = prep.get("message", "Refused.")
            results.approvals[call.tool_call_id] = ToolDenied(f"NOT prepared. {msg} Report this; do not retry.")
            _log(deps, "approval_refused", {"tool": call.tool_name, "args": args, "message": msg})
            continue
        req = ApprovalRequest(agent=deps.role, tool=call.tool_name, args=args, tool_call_id=call.tool_call_id,
                              approval_id=appr["id"], kind=appr["kind"], payee=appr["payee"],
                              amount=appr["amount"], memo=appr["memo"],
                              needs_two_approvers=bool(prep.get("needs_two_approvers")))
        _log(deps, "approval_prepared", {"approval_id": appr["id"], "tool": call.tool_name, "args": args,
                                         "payee": appr["payee"], "amount": appr["amount"], "memo": appr["memo"],
                                         "already_pending": bool(prep.get("already_pending"))})
        decision = await deps.team.approver(req)
        name = (decision.approved_by or "").strip()
        if decision.queued:
            results.approvals[call.tool_call_id] = ToolDenied(
                f"PREPARED, not done: approval {appr['id']} ({appr['payee']}, ${appr['amount']:,.2f}) is in the "
                "dashboard's signature tray waiting for a person. Nothing has changed yet. Do not retry; report it "
                "as waiting for human approval.")
            _log(deps, "approval_queued", {"approval_id": appr["id"], "tool": call.tool_name})
        elif decision.approved and name:
            signer = name
            if req.needs_two_approvers:
                co = (decision.co_approver or "").strip()
                if not co or co.lower() == name.lower():
                    results.approvals[call.tool_call_id] = ToolDenied(
                        "NOT done: this amount needs two different human approvers. Report it as waiting.")
                    _log(deps, "approval_incomplete", {"approval_id": appr["id"], "approved_by": name})
                    continue
                first = await mcp_call(call.tool_name, {**args, "approval_id": appr["id"], "approved_by": name})
                _log(deps, "approval_first_signature", {"approval_id": appr["id"], "approved_by": name,
                                                        "result": audit.trim(_as_text(first))})
                signer = co
            results.approvals[call.tool_call_id] = ToolApproved(
                override_args={**args, "approval_id": appr["id"], "approved_by": signer})
            _log(deps, "approval_granted", {"approval_id": appr["id"], "approved_by": signer})
        else:
            why = decision.reason or "no reason given"
            await mcp_call("decline_approval", {"approval_id": appr["id"], "declined_by": name or "desk",
                                                "reason": why})
            results.approvals[call.tool_call_id] = ToolDenied(
                f"A human declined this ({why}). It was NOT done. Do not retry.")
            _log(deps, "approval_declined", {"approval_id": appr["id"], "reason": why})
    for call in paused.calls:  # no external tools exist; answer anything unexpected safely
        results.calls[call.tool_call_id] = "This tool is not available."
    return results


# ---------------------------------------------------------------- the agent loop
async def run_role(deps: TeamDeps, request: str) -> str:
    """Run one agent to completion, auditing every step and pausing for human approval."""
    agent = get_agent(deps.role)
    limits = UsageLimits(request_limit=TEAM_REQUEST_LIMIT, total_tokens_limit=TEAM_TOTAL_TOKENS_LIMIT)
    _log(deps, "agent_start", {"request": audit.trim(request)})
    history, deferred, step = None, None, 0
    try:
        for _ in range(MAX_APPROVAL_ROUNDS + 1):
            async with agent.iter(
                request if history is None else None,
                message_history=history,
                deferred_tool_results=deferred,
                deps=deps,
                usage_limits=limits,
                usage=deps.team.usage,  # one shared budget for the whole team run
            ) as run:
                async for node in run:
                    step += 1
                    _audit_node(deps, step, node)
                result = run.result
            output = result.output
            if not isinstance(output, DeferredToolRequests):
                _log(deps, "agent_end", {"output": audit.trim(output, 8000 if deps.depth == 0 else 1500)}, step)
                return output
            _log(deps, "paused_for_approval", {"tools": [c.tool_name for c in output.approvals]}, step)
            deferred = await _ask_human(deps, output)
            history = result.all_messages()
        msg = "Stopped: too many approval rounds in one run."
    except UsageLimitExceeded as exc:
        msg = f"Stopped: the team's request/token budget is used up ({exc})."
    _log(deps, "agent_end", {"output": msg, "stopped": True}, step)
    return msg


def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)


def build_task(ticket: dict, packet: str) -> str:
    """The Boss's instruction for one ticket: the verified context packet plus the suggested route."""
    route = ROUTES.get(ticket.get("type", ""), DEFAULT_ROUTE)
    team = "\n".join(f"- {r}: {ROLE_SUMMARY[r]}" for r in route)
    return (
        f"Work ticket {ticket['id']} ({ticket.get('type')}: {ticket.get('subject')}).\n\n"
        f"Suggested specialists for this ticket type, in order (call others only if a fact is truly missing):\n"
        f"{team}\n\n"
        "The desk already fetched this ticket's context from MCP. Treat it as verified; don't re-fetch it, and "
        "pass the facts a teammate needs in `known_facts` when you delegate:\n"
        f"{packet}\n\n"
        "Follow the shop rules: human approval before any payment, purchase or price change; replies stay drafts; "
        "set the ticket's status; finish with your final report."
    )


async def run_team(ticket_id: int, approver: Approver, team_run_id: str | None = None,
                   label: str = "dashboard") -> TeamRunResult:
    """One team run on one ticket. Opens the MCP server if the caller hasn't already."""
    team = TeamState(team_run_id=team_run_id or uuid.uuid4().hex[:10], approver=approver, ticket_id=ticket_id)
    boss = TeamDeps(role="boss", depth=0, chain=["boss"], agent_run_id=uuid.uuid4().hex[:8], team=team)
    async with shop_mcp():  # one MCP server process for the whole run
        ctx = await mcp_call("get_ticket_context", {"ticket_id": ticket_id})
        if not ctx.get("found"):
            raise ValueError(f"No ticket {ticket_id}")
        team.context_packet = _compact({k: v for k, v in ctx.items() if k != "found"})
        _log(boss, "team_start", {"label": label, "ticket_id": ticket_id, "context_chars": len(team.context_packet),
                                  "limits": {"max_depth": MAX_DEPTH, "max_delegations": MAX_DELEGATIONS,
                                             "specialist_delegations": SPECIALIST_DELEGATIONS,
                                             "team_request_limit": TEAM_REQUEST_LIMIT,
                                             "team_total_tokens_limit": TEAM_TOTAL_TOKENS_LIMIT}})
        try:
            report = await run_role(boss, build_task(ctx["ticket"], team.context_packet))
        except Exception as exc:
            _log(boss, "error", {"type": type(exc).__name__, "message": audit.trim(str(exc))})
            raise
    _log(boss, "team_end", {"delegations": team.delegations, "ticket_id": ticket_id})
    return TeamRunResult(team_run_id=team.team_run_id, ticket_id=ticket_id, report=report,
                         delegations=team.delegations, requests=team.usage.requests,
                         total_tokens=team.usage.total_tokens)
