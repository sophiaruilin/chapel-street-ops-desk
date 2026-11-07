"""Work the Campus Customs ticket board with the agent team, from the terminal.

Run from hw5/backend/ (with hw5/.venv activated):
    python run_tickets.py                 # reset DB, every open ticket (one team run each), ask you before any approval
    python run_tickets.py --tickets 102   # only some tickets
    python run_tickets.py --no-reset      # keep the current working DB
    python run_tickets.py --decline-all   # non-interactive test: every approval is declined

Every step is appended to ../output/audit_trail.json. The Boss's reports are
printed and saved to ../output/last_run_report.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from agents.mcp_link import mcp_call, shop_mcp
from agents.team import run_team
from config import MODEL_NAME, REASONING_EFFORT, ROOT
from models import ApprovalDecision, ApprovalRequest
from reset_db import reset_db


async def terminal_approver(req: ApprovalRequest) -> ApprovalDecision:
    """Ask the human at the keyboard. Their typed name becomes payments.approved_by."""
    print("\n" + "=" * 68)
    print(f"APPROVAL NEEDED ({req.kind})  requested by the {req.agent} agent  ·  approval {req.approval_id}")
    print(f"  {req.tool}: {req.payee}  ${req.amount:,.2f}")
    print(f"  {req.memo}")
    print("  (practice ledger: no real money moves)")
    print("=" * 68)
    name = (await asyncio.to_thread(input, "Type your full name to APPROVE, or press Enter to decline: ")).strip()
    if not name:
        reason = (await asyncio.to_thread(input, "Reason for declining (optional): ")).strip()
        return ApprovalDecision(approved=False, reason=reason or "declined at the terminal")
    co = None
    if req.needs_two_approvers:
        co = (await asyncio.to_thread(input, "Second approver (a different person) full name: ")).strip()
    return ApprovalDecision(approved=True, approved_by=name, co_approver=co)


async def decline_all(req: ApprovalRequest) -> ApprovalDecision:
    print(f"[decline-all] {req.agent} prepared {req.tool} {req.payee} ${req.amount:,.2f}: declined")
    return ApprovalDecision(approved=False, approved_by="test harness", reason="test run: --decline-all")


async def main_async(ticket_ids: list[int] | None, approver) -> list:
    async with shop_mcp():
        if not ticket_ids:
            ticket_ids = [t["id"] for t in (await mcp_call("list_open_tickets"))["tickets"]]
        results = []
        for tid in ticket_ids:
            print(f"\n--- ticket {tid} ---")
            results.append(await run_team(tid, approver, label="cli"))
        return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team on the ticket board")
    parser.add_argument("--tickets", type=int, nargs="*", help="ticket ids to work (default: all open)")
    parser.add_argument("--no-reset", action="store_true", help="don't reset the working DB first")
    parser.add_argument("--decline-all", action="store_true", help="decline every approval (non-interactive)")
    args = parser.parse_args()

    if not args.no_reset:
        reset_db()
        print("Database reset: data/campus_customs_new.db restored from the original.")
    print(f"Model: {MODEL_NAME} (reasoning effort {REASONING_EFFORT}) for all five agents.")

    results = asyncio.run(main_async(args.tickets, decline_all if args.decline_all else terminal_approver))
    lines = []
    for r in results:
        print(f"\n{r.report}\n[ticket {r.ticket_id} · run {r.team_run_id}] delegations={r.delegations} "
              f"requests={r.requests} tokens={r.total_tokens}")
        lines.append(f"# Ticket {r.ticket_id} · run {r.team_run_id}\n\n{r.report}\n")
    (ROOT / "output" / "last_run_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
