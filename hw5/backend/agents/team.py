"""The Campus Customs agent team and its agent loop.

Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer
Service) share one model and one MCP server. Each has `ask_teammate`, so any
agent can delegate to any other (full connectivity), bounded by:
  - no asking yourself, and no asking back the agent that just asked you,
  - MAX_DEPTH levels of delegation and MAX_DELEGATIONS per team run,
  - one team-wide request/token budget shared by every agent.

`run_role` is the agent loop: it steps through agent.iter(), writes every step
to output/audit_trail.json, and when a payment tool pauses the run it asks the
human, then resumes the same run with their decision.
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
from agents.mcp_link import shop_mcp, toolset_for
from config import (
    MAX_APPROVAL_ROUNDS,
    MAX_DELEGATIONS,
    MAX_DEPTH,
    PROMPTS_DIR,
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
    """Record one step of the agent loop (a request to the model, or the model's response)."""
    if Agent.is_model_request_node(node):
        returns, retries = [], []
        for part in node.request.parts:
            if isinstance(part, ToolReturnPart):
                returns.append({"tool": part.tool_name, "tool_call_id": part.tool_call_id,
                                "content": audit.trim(_as_text(part.content))})
            elif isinstance(part, RetryPromptPart):
                retries.append({"tool": part.tool_name, "content": audit.trim(_as_text(part.content))})
        _log(deps, "model_request", {"tool_returns": returns, "retries": retries}, step)
    elif Agent.is_call_tools_node(node):
        resp = node.model_response
        calls = [{"tool": p.tool_name, "tool_call_id": p.tool_call_id, "args": p.args_as_dict()}
                 for p in resp.parts if isinstance(p, ToolCallPart)]
        text = "".join(p.content for p in resp.parts if isinstance(p, TextPart))
        _log(deps, "model_response", {
            "model": resp.model_name,
            "tool_calls": calls,
            "text": audit.trim(text) if text else None,
            "used_reasoning": any(isinstance(p, ThinkingPart) for p in resp.parts),
            "request_tokens": {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
        }, step)


# ---------------------------------------------------------------- delegation
async def ask_teammate(ctx: RunContext[TeamDeps], teammate: Role, request: str) -> str:
    """Delegate a focused request to a teammate and get their report back.

    teammate: one of boss, inventory, accounting, facilities, customer_service.
    request: a short, self-contained request. Include the ticket id and the
    exact SKU, size, quantity, lease id or invoice id it is about.
    """
    me = ctx.deps
    caller = me.chain[-2] if len(me.chain) >= 2 else None
    refusal = None
    if teammate not in ROLES:
        refusal = f"Unknown teammate '{teammate}'."
    elif teammate == me.role:
        refusal = "You can't delegate to yourself."
    elif teammate == caller:
        refusal = f"{teammate} is the one who asked you. Put what you need in your reply to them instead."
    elif me.depth + 1 > MAX_DEPTH:
        refusal = "Delegation depth limit reached. Answer with the facts you have and say what's missing."
    else:
        async with me.team.lock:
            if me.team.delegations >= MAX_DELEGATIONS:
                refusal = f"Team delegation budget ({MAX_DELEGATIONS}) used up. Answer with what you have."
            else:
                me.team.delegations += 1
    if refusal:
        _log(me, "delegation_refused", {"to": teammate, "request": audit.trim(request), "reason": refusal})
        return "Refused: " + refusal

    child = TeamDeps(role=teammate, depth=me.depth + 1, chain=[*me.chain, teammate],
                     agent_run_id=uuid.uuid4().hex[:8], team=me.team)
    _log(me, "delegation", {"to": teammate, "child_agent_run_id": child.agent_run_id,
                            "request": audit.trim(request)})
    return await run_role(child, request)


# ---------------------------------------------------------------- agents
def _instructions(role: Role) -> str:
    rules = (PROMPTS_DIR / "shop_rules.md").read_text(encoding="utf-8")
    text = (PROMPTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    return text.replace("{shop_rules}", rules).replace("{max_delegations}", str(MAX_DELEGATIONS))


@lru_cache(maxsize=None)
def get_agent(role: Role) -> Agent[TeamDeps, str | DeferredToolRequests]:
    model, settings = build_model()
    return Agent(
        model,
        name=role,
        deps_type=TeamDeps,
        output_type=[str, DeferredToolRequests],  # DeferredToolRequests = paused for approval
        instructions=_instructions(role),
        model_settings=settings,
        toolsets=[toolset_for(role)],
        tools=[ask_teammate],
        retries=2,
    )


# ---------------------------------------------------------------- human approval
async def _ask_human(deps: TeamDeps, paused: DeferredToolRequests) -> DeferredToolResults:
    results = DeferredToolResults()
    for call in paused.approvals:
        args = call.args_as_dict()
        args.pop("approved_by", None)  # only the human's own answer may set this
        decision = await deps.team.approver(ApprovalRequest(
            agent=deps.role, tool=call.tool_name, args=args, tool_call_id=call.tool_call_id))
        name = (decision.approved_by or "").strip()
        if decision.queued_approval_id:
            # Dashboard run: the payment is prepared, not made. A human pays it via the approve route.
            results.approvals[call.tool_call_id] = ToolDenied(
                f"Payment PREPARED, not paid: queued for human approval on the dashboard "
                f"(approval id {decision.queued_approval_id}). Cash has not changed. Do not retry; "
                f"report this payment as waiting for human approval.")
            _log(deps, "approval_queued", {"tool": call.tool_name, "args": args,
                                           "tool_call_id": call.tool_call_id,
                                           "approval_id": decision.queued_approval_id})
            continue
        if decision.approved and name:
            results.approvals[call.tool_call_id] = ToolApproved(override_args={**args, "approved_by": name})
        else:
            why = decision.reason or "no reason given"
            results.approvals[call.tool_call_id] = ToolDenied(
                f"A human declined this payment ({why}). It was NOT made. Do not retry it.")
        _log(deps, "approval", {"tool": call.tool_name, "args": args, "tool_call_id": call.tool_call_id,
                                "approved": bool(decision.approved and name), "approved_by": name or None,
                                "reason": decision.reason})
    for call in paused.calls:  # no external tools exist; answer anything unexpected safely
        results.calls[call.tool_call_id] = "This tool is not available."
    return results


# ---------------------------------------------------------------- the agent loop
async def run_role(deps: TeamDeps, request: str) -> str:
    """Run one agent to completion, auditing every step and pausing for payment approval."""
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
                usage=deps.team.usage,  # one shared budget for the whole team
            ) as run:
                async for node in run:
                    step += 1
                    _audit_node(deps, step, node)
                result = run.result
            output = result.output
            if not isinstance(output, DeferredToolRequests):
                _log(deps, "agent_end", {"output": audit.trim(output)}, step)
                return output
            _log(deps, "paused_for_approval",
                 {"tools": [c.tool_name for c in output.approvals]}, step)
            deferred = await _ask_human(deps, output)
            history = result.all_messages()
        msg = "Stopped: too many payment-approval rounds in one run."
    except UsageLimitExceeded as exc:
        msg = f"Stopped: the team's request/token budget is used up ({exc})."
    _log(deps, "agent_end", {"output": msg, "stopped": True}, step)
    return msg


def build_task(ticket_ids: list[int] | None) -> str:
    """The Boss's instruction for one team run."""
    scope = (f"Work only these tickets: {', '.join(map(str, ticket_ids))}."
             if ticket_ids else "Work every open ticket on the board.")
    return (f"{scope} Follow the shop rules, delegate to your team for every shop fact, "
            "get human approval before any payment, keep customer replies as drafts on the board, "
            "update each ticket's status, and finish with your final report.")


async def run_team(task: str, approver: Approver, team_run_id: str | None = None) -> TeamRunResult:
    """One full team run: the Boss gets the task and delegates from there."""
    team = TeamState(team_run_id=team_run_id or uuid.uuid4().hex[:10], approver=approver)
    boss = TeamDeps(role="boss", depth=0, chain=["boss"], agent_run_id=uuid.uuid4().hex[:8], team=team)
    _log(boss, "team_start", {"task": audit.trim(task), "limits": {
        "max_depth": MAX_DEPTH, "max_delegations": MAX_DELEGATIONS,
        "team_request_limit": TEAM_REQUEST_LIMIT, "team_total_tokens_limit": TEAM_TOTAL_TOKENS_LIMIT}})
    try:
        async with shop_mcp():  # one MCP server process for the whole run
            report = await run_role(boss, task)
    except Exception as exc:
        _log(boss, "error", {"type": type(exc).__name__, "message": audit.trim(str(exc))})
        raise
    _log(boss, "team_end", {"delegations": team.delegations})
    return TeamRunResult(team_run_id=team.team_run_id, report=report, delegations=team.delegations,
                         requests=team.usage.requests, total_tokens=team.usage.total_tokens)
