# Campus Customs operations MCP server

**What it's for:** this FastMCP server (`campus-customs-ops`) is the only way any HW 5 agent touches shop data. The five agents (Boss, Inventory, Accounting, Facilities, Customer Service), and Claude Code itself, call these tools over MCP. Nothing queries SQLite directly. Tools return only what is stored in the database, and when a lookup finds nothing they return `found: false` instead of guessing.

**Database:** `../data/campus_customs_new.db`, the working copy. The original `data/campus_customs.db` is never touched. Read tools open the database read-only. Only the 4 write tools below change it, each in a single transaction.

## Tools (15)

| Tool | Table(s) | Ticket | What it does |
|---|---|---|---|
| `check_stock_by_sku_and_size(sku, size)` | inventory | 101, 103 | Quantity on hand and aisle for one SKU/size, plus `in_stock`; if the size doesn't exist, lists the sizes that do |
| `get_lease_rent_and_cash(lease_id)` | leases, cash_accounts, desk | 102 | The lease's real rent, landlord and due date, cash balances, today, `days_until_due`, `overdue` |
| `get_sku_cost_and_price(sku)` | pricing (+ inventory for the name) | 103 | Unit cost, list price, margin per unit and as a % of list |
| `get_desk_date()` | desk | all | The shop's "today" |
| `list_open_tickets()` | tickets | all | Every ticket not yet resolved |
| `list_tickets()` | tickets | all | Every ticket, including resolved ones (used by the dashboard API) |
| `get_ticket(ticket_id)` | tickets | all | One ticket, including drafts saved in its notes |
| `list_vendors()` | vendors | 101, 103 | Vendor specialty and `lead_days` |
| `list_open_invoices(vendor_id?)` | invoices, vendors, desk | 101 | Unpaid invoices, overdue days, `vendor_will_ship: false` |
| `get_cash_balances()` | cash_accounts, desk | 101, 102 | Every account's balance and total |
| `list_payments(kind?, ref_id?)` | payments | 101, 102 | Payments already made, so nothing is paid twice |
| `pay_invoice(invoice_id, account, approved_by)` | invoices, cash_accounts, payments | 101 | **Writes, needs human approval.** Pays an open invoice in full |
| `pay_rent(lease_id, account, approved_by)` | leases, cash_accounts, payments | 102 | **Writes, needs human approval.** Pays `monthly_rent` and moves `next_due` forward a month |
| `add_ticket_draft(ticket_id, draft)` | tickets (notes) | all | **Writes.** Saves a "DRAFT – not sent" reply on the ticket; nothing is emailed |
| `update_ticket_status(ticket_id, status)` | tickets (status) | all | **Writes.** Sets `open`, `waiting_approval`, `blocked` or `resolved` |

## Shop rules the server follows

- **Today** is `desk.date_today` (2026-08-31), never the computer clock. Due dates and "overdue" are measured from it.
- **Lead times** come only from `vendors.lead_days`.
- A vendor **won't ship** while it has an open unpaid invoice (`list_open_invoices` flags this).
- **Payments need human approval.** `approved_by` must be a human name: blank or agent-role names like "accounting" are refused. The agent harness hides this argument from the model and fills it only with the name the human types when approving.
- **No negative balances.** Pay tools refuse when cash is short, an invoice isn't open, or rent is already paid ahead. A payment writes `payments`, `cash_accounts` and the invoice or lease in one transaction.
- **Cash only goes out.** No tool adds money.
- **Reset before a full run:** `python backend/reset_db.py` from hw5/ (the agent runner and the dashboard's Reset button do this too).
- **No emails and no vendor calls.** Drafts stay on the board.

The full rule table is in `../output/harness.md`.

## Run

```bash
# from hw5/, with the hw5/.venv activated (see ../README.md)
python mcp_server/server.py          # stdio (how Claude Code and the agents launch it)
python mcp_server/server.py --http   # http://127.0.0.1:8002/mcp
```
