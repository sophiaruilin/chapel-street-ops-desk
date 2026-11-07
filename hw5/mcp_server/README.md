# Campus Customs operations MCP server

**What it's for:** this FastMCP server (`campus-customs-ops`, `server.py`) is the only way anything in HW 5 touches shop data. The five agents (Boss, Inventory, Accounting, Facilities, Customer Service), the FastAPI backend and Claude Code all call these tools over MCP. Nothing else queries SQLite directly. Tools return only what is stored in the database, and when a lookup finds nothing they return `found: false` instead of guessing.

**Database:** `../data/campus_customs_new.db`, the working copy (tests point `CAMPUS_DB_PATH` at a temp copy). The original `data/campus_customs.db` is never written to. Read tools open the database read-only; every write is one transaction. The first time the server touches the working copy it adds three tables: `approvals`, `drafts` and `purchase_orders`.

## Tools (21)

| Tool | Table(s) | Ticket | What it does |
|---|---|---|---|
| `check_stock_by_sku_and_size(sku, size)` | inventory | 101, 103 | Quantity on hand and aisle for one SKU/size |
| `get_lease_rent_and_cash(lease_id)` | leases, cash_accounts, desk | 102 | The lease's real rent, landlord, due date, `days_until_due`, cash |
| `get_sku_cost_and_price(sku)` | pricing | 103 | Unit cost, list price, margin |
| `get_desk_date()` | desk | all | The shop's "today" |
| `list_open_tickets()` · `list_tickets()` | tickets | all | Open tickets · every ticket (notes flagged as untrusted input) |
| `get_ticket(ticket_id)` | tickets, drafts | all | One ticket plus its drafts by audience |
| `get_ticket_context(ticket_id)` | tickets, drafts, desk, cash_accounts, inventory, pricing, vendors, invoices, leases, payments, approvals | all | **Everything about one ticket in one call.** The desk fetches it before the Boss starts |
| `list_vendors()` | vendors | 101, 103 | Specialty and `lead_days` |
| `list_open_invoices(vendor_id?)` | invoices, vendors, desk | 101, 103 | Unpaid invoices, days overdue, `vendor_will_ship: false` |
| `get_cash_balances()` | cash_accounts, desk | all | Balances |
| `list_payments(kind?, ref_id?)` | payments | 101, 102 | Payments already made |
| `create_approval(tool, args, ticket_id?, agent?, team_run_id?)` | approvals (+ the records it quotes) | 101–103 | **Prepares** a payment, purchase or price. The payee and amount are frozen from the records; it refuses up front if cash is short, the vendor is on hold, or the price is below cost; a duplicate returns the existing approval |
| `list_approvals(status?, ticket_id?)` | approvals | all | Prepared approvals and their status |
| `decline_approval(approval_id, declined_by, reason)` | approvals | all | A human declines; nothing happens |
| `pay_invoice(invoice_id, account, approval_id, approved_by)` | approvals, invoices, cash_accounts, payments | 101 | **Executes** an approved invoice payment, at most once |
| `pay_rent(lease_id, account, approval_id, approved_by)` | approvals, leases, cash_accounts, payments | 102 | **Executes** approved rent at the lease amount; moves `next_due` forward a month |
| `order_stock(vendor_id, sku, size, qty, account, approval_id, approved_by)` | approvals, purchase_orders, pricing, vendors, cash_accounts, payments | 101, 103 | **Executes** an approved prepaid purchase order (qty × unit cost); refused while the vendor has an unpaid invoice |
| `set_bulk_price(ticket_id, sku, size, qty, unit_price, approval_id, approved_by)` | approvals, pricing | 103 | **Executes** an approved bulk price (between cost and list); no cash moves |
| `add_ticket_draft(ticket_id, draft, audience)` | drafts | all | Saves a `customer` or `internal` draft; never sent |
| `update_ticket_status(ticket_id, status)` | tickets | all | open / waiting_approval / blocked / resolved |

## How an approval works

1. An agent calls `pay_invoice` (or `pay_rent`, `order_stock`, `set_bulk_price`). The agent harness pauses the run and calls `create_approval`, which freezes the payee and amount from the records.
2. A person decides: on the dashboard (desk PIN + name) or at the terminal.
3. The same tool runs **with** `approval_id` + `approved_by`. In one transaction it checks that the approval is still pending, that the arguments match what was approved, that the record still gives the same payee and amount, that it isn't a duplicate, and that cash covers it. Then it writes `payments` + `cash_accounts` + the invoice, lease or purchase order, and marks the approval approved.
4. Above `SECOND_APPROVER_ABOVE` (default $5,000) the first signature only records `partially_approved`; a second, different person completes it.

## Shop rules the server follows

- **Today** is `desk.date_today` (2026-08-31), never the computer clock.
- **Lead times** come only from `vendors.lead_days`.
- A vendor **won't ship** while it has an open unpaid invoice, so `order_stock` is refused.
- **Human approval** for every payment, purchase and price, executed at most once, at the amount that was approved.
- **No negative balances**, checked at prepare and at execute.
- **Cash only goes out.** No tool adds money.
- **Reset before a full run:** `python backend/reset_db.py` from hw5/ (the dashboard's Reset button and `run_tickets.py` do this too).
- **No emails and no vendor calls.** Drafts stay on the board, and ticket notes are untrusted input.

## Run

```bash
# from hw5/, with hw5/.venv activated (see ../README.md)
python mcp_server/server.py          # stdio (how the agents, the backend and Claude Code launch it)
python mcp_server/server.py --http   # http://127.0.0.1:8002/mcp
python -m pytest tests               # 20 rule tests, no model calls
```
