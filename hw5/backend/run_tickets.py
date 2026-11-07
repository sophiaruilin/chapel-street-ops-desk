"""Work the Campus Customs ticket board with the agent team.

Run from hw5/backend/ (with hw5/.venv activated):
    python run_tickets.py                 # reset DB, all open tickets, ask you before any payment
    python run_tickets.py --tickets 102   # only some tickets
    python run_tickets.py --no-reset      # keep the current working DB
    python run_tickets.py --decline-all   # non-interactive test: every payment is declined

Every step is appended to ../output/audit_trail.json. The Boss's final report
is printed and saved to ../output/last_run_report.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from agents.team import build_task, run_team
from config import MODEL_NAME, REASONING_EFFORT, ROOT
from models import ApprovalDecision, ApprovalRequest
from reset_db import reset_db


async def terminal_approver(req: ApprovalRequest) -> ApprovalDecision:
    """Ask the human at the keyboard. Their typed name becomes payments.approved_by."""
    print("\n" + "=" * 64)
    print(f"PAYMENT APPROVAL NEEDED  (requested by the {req.agent} agent)")
    print(f"  tool: {req.tool}")
    for key, value in req.args.items():
        print(f"  {key}: {value}")
    print("=" * 64)
    name = (await asyncio.to_thread(input, "Type your full name to APPROVE, or press Enter to decline: ")).strip()
    if name:
        return ApprovalDecision(approved=True, approved_by=name)
    reason = (await asyncio.to_thread(input, "Reason for declining (optional): ")).strip()
    return ApprovalDecision(approved=False, reason=reason or "declined at the terminal")


async def decline_all(req: ApprovalRequest) -> ApprovalDecision:
    print(f"[decline-all] {req.agent} asked for {req.tool} {req.args}: declined")
    return ApprovalDecision(approved=False, reason="test run: --decline-all")




def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # em dashes etc. in the report
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team on the ticket board")
    parser.add_argument("--tickets", type=int, nargs="*", help="ticket ids to work (default: all open)")
    parser.add_argument("--no-reset", action="store_true", help="don't reset the working DB first")
    parser.add_argument("--decline-all", action="store_true", help="decline every payment (non-interactive)")
    args = parser.parse_args()

    if not args.no_reset:
        reset_db()
        print("Database reset: data/campus_customs_new.db restored from the original.")
    print(f"Model: {MODEL_NAME} (reasoning effort {REASONING_EFFORT}) for all five agents.\n")

    result = asyncio.run(run_team(build_task(args.tickets),
                                  decline_all if args.decline_all else terminal_approver))
    report_path = ROOT / "output" / "last_run_report.md"
    report_path.write_text(f"# Team run {result.team_run_id}\n\n{result.report}\n", encoding="utf-8")
    print("\n" + result.report)
    print(f"\n[run {result.team_run_id}] delegations={result.delegations} requests={result.requests} "
          f"tokens={result.total_tokens}  audit: output/audit_trail.json  report: {report_path.name}")


if __name__ == "__main__":
    main()
