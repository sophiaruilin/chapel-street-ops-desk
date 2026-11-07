"""Campus Customs operations MCP server (HW 5).

Every agent in HW 5 gets its database tools from this FastMCP server.
It reads ../data/campus_customs_new.db and only returns rows that exist there:
when a lookup finds nothing it says so instead of guessing. Read tools open
the database read-only; only pay_invoice, pay_rent, add_ticket_draft and
update_ticket_status write, each in a single transaction.

Shop rules the tools follow (full list in ../output/harness.md):
- "Today" is desk.date_today, never the computer clock; overdue is judged against it.
- Vendor lead times come only from the vendors table.
- A vendor won't ship while it has an open unpaid invoice.
- Payments need human approval, must refuse if cash is short (no negative
  balances), and must update payments + cash_accounts + the invoice/lease.
  pay_invoice / pay_rent require approved_by (a human name); the agent
  harness only fills it in after a person approves in the terminal.
- Cash only goes out; no revenue is modeled.
- Nothing here emails customers or contacts vendors; drafts stay on the board.

Run from this folder (stdio):  python server.py
Run (HTTP):                    python server.py --http
HTTP URL:                      http://127.0.0.1:8002/mcp
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs-ops")


def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a read-only query against campus_customs_new.db and return plain dicts."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Campus Customs database not found at {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def _date_today() -> str | None:
    """The shop's "today" (desk.date_today). Never use the computer clock."""
    rows = _query("SELECT date_today FROM desk LIMIT 1")
    return rows[0]["date_today"] if rows else None


def _days_between(start: str, end: str) -> int:
    """Whole days from start to end (ISO dates; any time part is ignored)."""
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


@mcp.tool
def check_stock_by_sku_and_size(sku: str, size: str) -> dict:
    """Check how many units of one SKU in one size are on the shelf, and where.

    Use this before promising an item to a customer (for example ticket 101,
    a CC-TEE-WHITE in size S). Returns the inventory row, or found=False plus
    the sizes that do exist for that SKU, if the size is not in the database.
    """
    sku, size = sku.strip().upper(), size.strip().upper()
    rows = _query(
        "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
        (sku, size),
    )
    if rows:
        row = rows[0]
        return {"found": True, **row, "in_stock": row["qty"] > 0}
    other_sizes = _query(
        "SELECT size, qty FROM inventory WHERE sku = ? ORDER BY size", (sku,)
    )
    return {
        "found": False,
        "sku": sku,
        "size": size,
        "message": "No inventory row for this SKU and size.",
        "sizes_on_record": other_sizes,
    }


@mcp.tool
def get_lease_rent_and_cash(lease_id: int) -> dict:
    """Get the lease's real rent and due date, the shop's cash, and today's date.

    Use this to check a rent notice (for example ticket 102, lease 1) against
    the lease on file instead of trusting the email. Returns the lease row,
    every cash account balance, the desk date ("today"), and how many days
    until rent is due measured from that date. It does not pay anything:
    any payment needs human approval.
    """
    leases = _query(
        "SELECT id, space_name, landlord, monthly_rent, next_due, notes "
        "FROM leases WHERE id = ?",
        (lease_id,),
    )
    if not leases:
        return {"found": False, "lease_id": lease_id, "message": "No lease with this id."}
    lease = leases[0]
    today = _date_today()
    days_until_due = _days_between(today, lease["next_due"]) if today else None
    return {
        "found": True,
        "lease": lease,
        "cash_accounts": _query("SELECT name, balance, date FROM cash_accounts"),
        "date_today": today,
        "days_until_due": days_until_due,
        "overdue": days_until_due is not None and days_until_due < 0,
    }


@mcp.tool
def get_sku_cost_and_price(sku: str) -> dict:
    """Get one SKU's unit cost, list price, and the margin between them.

    Use this before answering a discount request (for example ticket 103,
    20 CC-HOOD-NAVY hoodies) so any offered price is checked against what the
    item costs the shop. Margin is computed only from the two stored prices.
    """
    sku = sku.strip().upper()
    rows = _query(
        "SELECT p.sku, i.name, p.unit_cost, p.list_price "
        "FROM pricing p LEFT JOIN (SELECT DISTINCT sku, name FROM inventory) i "
        "ON i.sku = p.sku WHERE p.sku = ?",
        (sku,),
    )
    if not rows:
        return {"found": False, "sku": sku, "message": "No pricing row for this SKU."}
    row = rows[0]
    margin = row["list_price"] - row["unit_cost"]
    return {
        "found": True,
        **row,
        "margin_per_unit": round(margin, 2),
        "margin_pct_of_list": round(100 * margin / row["list_price"], 1)
        if row["list_price"]
        else None,
    }


# --------------------------------------------------------------------------
# Problem 5 tools: the rest of what the agent team needs for the open tickets.
# --------------------------------------------------------------------------

TICKET_STATUSES = ("open", "waiting_approval", "blocked", "resolved")


def _write_conn() -> sqlite3.Connection:
    """A read-write connection for the few tools that change the board or pay."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Campus Customs database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, isolation_level=None)  # explicit BEGIN/COMMIT below
    conn.row_factory = sqlite3.Row
    return conn


def _add_one_month(iso_day: str) -> str:
    """Same day next month (clamped to the month's last day), for advancing rent."""
    d = date.fromisoformat(iso_day[:10])
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Cannot advance {iso_day}")


def _check_approver(approved_by: str) -> str | None:
    """Return an error message if the approver isn't a usable human name."""
    name = (approved_by or "").strip()
    if not name:
        return "Refused: a payment needs a named human approver (approved_by)."
    if name.lower() in {"boss", "inventory", "accounting", "facilities", "customer_service",
                        "agent", "ai", "assistant", "system"}:
        return f"Refused: '{name}' is an agent role, not a human approver."
    return None


@mcp.tool
def get_desk_date() -> dict:
    """Get the shop's "today" (desk.date_today) and any desk notes.

    Every agent should judge due dates, overdue items and lead times against
    this date, never against the computer clock.
    """
    rows = _query("SELECT date_today, notes FROM desk LIMIT 1")
    if not rows:
        return {"found": False, "message": "The desk table has no date."}
    return {"found": True, **rows[0]}


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket on the board that is not resolved yet.

    Use this first in a run to see the work queue: each ticket's id, type,
    requester, subject, the SKU/size/qty, lease or invoice it refers to,
    status and notes.
    """
    rows = _query("SELECT * FROM tickets WHERE status != 'resolved' ORDER BY id")
    return {"count": len(rows), "tickets": rows}


@mcp.tool
def list_tickets() -> dict:
    """List every ticket on the board, resolved or not, with its current status."""
    rows = _query("SELECT * FROM tickets ORDER BY id")
    return {"count": len(rows), "tickets": rows}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket exactly as it sits on the board (all fields, including drafts in notes)."""
    rows = _query("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if not rows:
        return {"found": False, "ticket_id": ticket_id, "message": "No ticket with this id."}
    return {"found": True, "ticket": rows[0]}


@mcp.tool
def list_vendors() -> dict:
    """List every vendor with its specialty and lead_days (the only source of lead times)."""
    return {"vendors": _query("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id")}


@mcp.tool
def list_open_invoices(vendor_id: int | None = None) -> dict:
    """List unpaid (open) vendor invoices, optionally for one vendor.

    A vendor will not ship new product while it has an open invoice, so check
    this before promising any restock. Each invoice says whether it is overdue
    as of desk.date_today and by how many days.
    """
    sql = (
        "SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date, "
        "i.status, i.description FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
        "WHERE i.status = 'open'"
    )
    params: tuple = ()
    if vendor_id is not None:
        sql += " AND i.vendor_id = ?"
        params = (vendor_id,)
    today = _date_today()
    invoices = []
    for inv in _query(sql + " ORDER BY i.due_date", params):
        days_overdue = _days_between(inv["due_date"], today) if today else None
        invoices.append({
            **inv,
            "overdue": days_overdue is not None and days_overdue > 0,
            "days_overdue": max(days_overdue, 0) if days_overdue is not None else None,
            "vendor_will_ship": False,  # rule: no shipping while an invoice is open
        })
    return {
        "date_today": today,
        "vendor_id": vendor_id,
        "count": len(invoices),
        "total_open": round(sum(i["amount"] for i in invoices), 2),
        "invoices": invoices,
    }


@mcp.tool
def get_cash_balances() -> dict:
    """Get every cash account's balance and balance date. Cash only goes out in this shop."""
    rows = _query("SELECT name, balance, date FROM cash_accounts ORDER BY name")
    return {"date_today": _date_today(), "accounts": rows,
            "total": round(sum(r["balance"] for r in rows), 2)}


@mcp.tool
def list_payments(kind: str | None = None, ref_id: int | None = None) -> dict:
    """List payments already made (read-only), optionally filtered.

    kind: 'invoice' or 'rent'. ref_id: the invoice id or lease id paid.
    Use this to check something isn't already paid before asking to pay it.
    """
    sql, params = "SELECT * FROM payments WHERE 1=1", []
    if kind:
        sql += " AND kind = ?"
        params.append(kind.strip().lower())
    if ref_id is not None:
        sql += " AND ref_id = ?"
        params.append(ref_id)
    rows = _query(sql + " ORDER BY id", tuple(params))
    return {"count": len(rows), "payments": rows,
            "total_paid": round(sum(r["amount"] for r in rows), 2)}


@mcp.tool
def pay_invoice(invoice_id: int, account: str, approved_by: str) -> dict:
    """Pay one open vendor invoice in full from a cash account. NEEDS HUMAN APPROVAL.

    approved_by must be the name of the human who approved this payment; the
    agent harness fills it in only after a person says yes. Refuses if the
    invoice is not open, the account doesn't exist, or the balance is too low
    (no negative balances). On success, in one transaction: inserts a payments
    row, lowers cash_accounts.balance, and marks the invoice paid.
    """
    if (err := _check_approver(approved_by)) is not None:
        return {"paid": False, "message": err}
    conn = _write_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]
        refusal = None
        if inv is None:
            refusal = f"No invoice with id {invoice_id}."
        elif inv["status"] != "open":
            refusal = f"Invoice {invoice_id} is '{inv['status']}', not open."
        elif acct is None:
            refusal = f"No cash account named '{account}'."
        elif acct["balance"] < inv["amount"]:
            refusal = (f"Not enough cash: {account} has {acct['balance']:.2f}, "
                       f"invoice needs {inv['amount']:.2f}. No negative balances.")
        if refusal:
            conn.execute("ROLLBACK")
            return {"paid": False, "message": "Refused: " + refusal}
        new_balance = round(acct["balance"] - inv["amount"], 2)
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES ('invoice', ?, ?, ?, ?, ?)",
            (invoice_id, inv["amount"], account, today, approved_by.strip()),
        )
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                     (new_balance, today, account))
        conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice_id,))
        conn.execute("COMMIT")
        return {"paid": True, "payment_id": cur.lastrowid, "invoice_id": invoice_id,
                "vendor_id": inv["vendor_id"], "amount": inv["amount"], "account": account,
                "balance_before": acct["balance"], "balance_after": new_balance,
                "paid_at": today, "approved_by": approved_by.strip()}
    except Exception:
        conn.execute("ROLLBACK") if conn.in_transaction else None
        raise
    finally:
        conn.close()


@mcp.tool
def pay_rent(lease_id: int, account: str, approved_by: str) -> dict:
    """Pay one month's rent for a lease (the monthly_rent on file). NEEDS HUMAN APPROVAL.

    The amount always comes from the lease, never from an email. Refuses if
    the lease doesn't exist, the account doesn't exist, the balance is too low,
    or rent is already paid ahead (next_due more than 31 days after today).
    On success, in one transaction: inserts a payments row, lowers the cash
    balance, and moves leases.next_due forward one month.
    """
    if (err := _check_approver(approved_by)) is not None:
        return {"paid": False, "message": err}
    conn = _write_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]
        refusal = None
        if lease is None:
            refusal = f"No lease with id {lease_id}."
        elif _days_between(today, lease["next_due"]) > 31:
            refusal = f"Rent for lease {lease_id} is already paid ahead (next due {lease['next_due']})."
        elif acct is None:
            refusal = f"No cash account named '{account}'."
        elif acct["balance"] < lease["monthly_rent"]:
            refusal = (f"Not enough cash: {account} has {acct['balance']:.2f}, "
                       f"rent is {lease['monthly_rent']:.2f}. No negative balances.")
        if refusal:
            conn.execute("ROLLBACK")
            return {"paid": False, "message": "Refused: " + refusal}
        new_balance = round(acct["balance"] - lease["monthly_rent"], 2)
        new_due = _add_one_month(lease["next_due"])
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
            "VALUES ('rent', ?, ?, ?, ?, ?)",
            (lease_id, lease["monthly_rent"], account, today, approved_by.strip()),
        )
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                     (new_balance, today, account))
        conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, lease_id))
        conn.execute("COMMIT")
        return {"paid": True, "payment_id": cur.lastrowid, "lease_id": lease_id,
                "landlord": lease["landlord"], "amount": lease["monthly_rent"],
                "account": account, "balance_before": acct["balance"],
                "balance_after": new_balance, "paid_for_due_date": lease["next_due"],
                "next_due_now": new_due, "paid_at": today, "approved_by": approved_by.strip()}
    except Exception:
        conn.execute("ROLLBACK") if conn.in_transaction else None
        raise
    finally:
        conn.close()


@mcp.tool
def add_ticket_draft(ticket_id: int, draft: str) -> dict:
    """Save a draft reply on a ticket's notes. Nothing is emailed or sent.

    Use this for anything meant for a customer, landlord or vendor. The draft
    is appended under a "[DRAFT - not sent]" header with the desk date, and the
    original notes are kept.
    """
    draft = (draft or "").strip()
    if not draft:
        return {"saved": False, "message": "Draft text is empty."}
    conn = _write_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"saved": False, "message": f"No ticket with id {ticket_id}."}
        today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]
        block = f"[DRAFT - not sent, {today}]\n{draft}"
        notes = f"{row['notes']}\n\n{block}" if row["notes"] else block
        conn.execute("UPDATE tickets SET notes = ? WHERE id = ?", (notes, ticket_id))
        conn.execute("COMMIT")
        return {"saved": True, "ticket_id": ticket_id, "sent": False, "draft": block}
    finally:
        conn.close()


@mcp.tool
def update_ticket_status(ticket_id: int, status: str) -> dict:
    """Move a ticket on the board: open, waiting_approval, blocked, or resolved."""
    status = status.strip().lower()
    if status not in TICKET_STATUSES:
        return {"updated": False, "message": f"Status must be one of {', '.join(TICKET_STATUSES)}."}
    conn = _write_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"updated": False, "message": f"No ticket with id {ticket_id}."}
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute("COMMIT")
        return {"updated": True, "ticket_id": ticket_id, "from": row["status"], "to": status}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs operations MCP server")
    parser.add_argument("--http", action="store_true", help="serve over HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=args.port, show_banner=False)
    else:
        mcp.run(show_banner=False)
