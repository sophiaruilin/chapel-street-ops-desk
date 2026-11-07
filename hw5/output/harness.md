# HW 5 — Campus Customs Multi-Agent Operations harness

Database: `data/campus_customs_new.db` (working copy of the original `data/campus_customs.db`, which stays untouched).

**What's in this harness:** shop rules (R1–R8) → database tables (P2) → MCP tools (P3 + full list) → the five agents (P5) → safety guardrails and token limits → API routes (P7) → dashboard (P8) → the full run and how to reproduce it (P9).

**How to run everything:**
Setup and the full step-by-step are in `README.md`. In short, with `hw5/.venv` activated:
1. Backend: `cd backend` then `uvicorn main:app --reload --port 8000`. It starts the MCP server (`mcp_server/server.py`) itself over stdio.
2. Dashboard: `cd frontend` then `npm run dev`, and open http://localhost:5173.
3. Optional terminal-only run: `cd backend` then `python run_tickets.py` (resets the DB, then asks you in the terminal before any payment).

## Rules of this shop

Every agent and every MCP tool follows these rules. The right-hand column says where each rule is enforced.

| # | Rule | Where it is enforced |
|---|---|---|
| R1 | `desk.date_today` is "today" for the shop. Use it to decide what is overdue. | MCP tools read today from `desk` (`_date_today()`), never from the computer clock. `get_lease_rent_and_cash` returns `days_until_due` and `overdue` against that date. |
| R2 | Vendor lead times come from the `vendors` table. | Agents quote `vendors.lead_days` only and never estimate delivery times themselves. |
| R3 | A vendor will not ship new product while it still has an open unpaid invoice. | No restock or reprint is promised until that vendor's invoices are paid. Example: Bulldog Print Co has open invoice 501 ($840, due 2026-08-28, overdue as of 2026-08-31), so the size-S tee for ticket 101 cannot be reprinted until 501 is paid. |
| R4 | Human approval is required for any payment, and a payment must update the relevant tables. | Agents only *prepare*: `create_approval` stores each payment in `approvals` with the payee and amount frozen. A person executes it, either on the dashboard (desk PIN + name) or in the terminal. The pay tool runs at most once, refuses if the record changed, and in one transaction writes `payments`, lowers `cash_accounts.balance`, marks the invoice `paid` or advances `leases.next_due`, and marks the approval approved. |
| R5 | If there is not enough cash, the pay tool must refuse. No negative balances. | Cash is checked when an approval is prepared *and* again inside the execute transaction. Either refusal writes nothing (covered by tests). |
| R6 | Cash only goes out. No revenue is modeled, so no money comes in. | Nothing ever raises a cash balance. Selling hoodies in ticket 103 does not add cash, so ticket planning has to fit the $3,400 in checking. |
| R7 | Before a full run to resolve the tickets, reset the database to its original values. | `python backend/reset_db.py`, `POST /api/reset` (PIN) or "Reset the shop" copies `data/campus_customs.db` over `data/campus_customs_new.db` (approvals and drafts start empty). `run_tickets.py` resets automatically. |
| R8 | Do not email customers or call real vendors. Drafts stay on the board. | Agents only write drafts (`drafts` table: customer vs internal, `sent = 0`). No tool sends email or contacts anyone outside the shop. |

## Problem 2 — Database tables

### desk
Fields: `date_today`, `notes`
Why it matters: it gives every agent the shop's "today" (2026-08-31), so due dates and lead times are judged against the database's date, not the computer's clock (R1).

### tickets
Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`
Why it matters: this is the agents' work queue. Each ticket (101 customer order, 102 rent notice, 103 price override) says what is being asked and links to the SKU, lease, or invoice the agent has to look up.

### inventory
Fields: `sku`, `name`, `size`, `qty`, `location`
Why it matters: it tells an agent whether a requested item and size is actually on the shelf, and in which aisle, before it promises anything to a customer.

### pricing
Fields: `sku`, `unit_cost`, `list_price`
Why it matters: it shows cost and selling price per SKU, so an agent can see how much margin there is before agreeing to a discount.

### vendors
Fields: `id`, `name`, `specialty`, `lead_days`
Why it matters: it tells an agent who can restock or deliver, and how many days that takes, when an item is out of stock.

### invoices
Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`
Why it matters: it lists bills the shop owes vendors. Invoice 501 is an open, overdue rush reprint for the tee in ticket 101, and it also takes cash the rent may need.

### leases
Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`
Why it matters: it holds the real rent amount, landlord and due date, so an agent can check a rent notice (ticket 102) against the lease instead of trusting the email.

### cash_accounts
Fields: `name`, `balance`, `date`
Why it matters: it shows how much money the shop has and as of what date, so an agent can tell whether a payment can be covered before asking for approval.

### payments
Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`
Why it matters: it is the record of money going out. It is empty today, and its required `approved_by` field means no payment should be logged without a named approver.

## Problem 3 — MCP tools (`mcp_server/server.py`)

### `check_stock_by_sku_and_size(sku, size)`
- **Reads:** `inventory`
- **Unlocks ticket:** 101 (Tauhid Zaman wants one CC-TEE-WHITE in size S)
- **Why it's the right tool:** ticket 101 hinges on one fact, whether a size-S Classic Bulldog Tee is on the shelf. This tool returns that exact SKU/size row (qty 0, Aisle B), so the agent knows it cannot simply fill the order. Under R3 it must first deal with the open, overdue rush-reprint invoice 501 before any reprint can ship, instead of promising a tee that isn't there.

### `get_lease_rent_and_cash(lease_id)`
- **Reads:** `leases`, `cash_accounts`, `desk`
- **Unlocks ticket:** 102 (an "Email: shop rent due in 2 days" notice from Elm City Properties, linked to lease 1)
- **Why it's the right tool:** ticket 102 is an email claim about money, so the agent has to check it against the lease on file. It needs the real landlord, the $2,400 rent and the 2026-09-02 due date (two days after the desk date of 2026-08-31), plus the $3,400 checking balance, all in one call, before it recommends paying anyone. Any payment still needs human approval (R4).

### `get_sku_cost_and_price(sku)`
- **Reads:** `pricing` (and `inventory` only for the product name)
- **Unlocks ticket:** 103 (Yale AI Club wants 20 CC-HOOD-NAVY hoodies in size M at a bulk discount)
- **Why it's the right tool:** a discount decision needs the floor as well as the sticker price. This tool returns the $22 unit cost against the $58 list price ($36 or 62.1% margin per hoodie), so any offered discount is checked against real cost and never set below it.

## Problem 5 — Agent team

All five agents are PydanticAI agents in `backend/agents/team.py`. Prompts are in `backend/prompts/` (one file per agent, plus `shop_rules.md`, which is inserted into all of them). Data types are in `backend/models.py`. Every agent uses the same model: **gpt-6-astra via Portkey, Responses API, reasoning effort medium** (`backend/config.py`). Run from the dashboard, or from `backend/run_tickets.py`, which runs each open ticket as its own team run.

| Agent | Job | MCP tools it can call | Usually called for |
|---|---|---|---|
| **Boss** (`prompts/boss.md`) | Reads the verified context packet, delegates decisions (not lookups), sets ticket status, writes the final report | `get_desk_date`, `list_open_tickets`, `get_ticket`, `update_ticket_status` | every ticket |
| **Inventory** (`prompts/inventory.md`) | Stock and aisle by SKU/size, vendor lead times, the open-invoice shipping hold | `get_desk_date`, `check_stock_by_sku_and_size`, `list_vendors`, `list_open_invoices` | stock questions the packet can't answer |
| **Accounting** (`prompts/accounting.md`) | Cash math across pending approvals; **prepares** payments, purchases and bulk prices | `get_desk_date`, `get_cash_balances`, `list_open_invoices`, `get_sku_cost_and_price`, `list_payments`, `pay_invoice`, `pay_rent`, `order_stock`, `set_bulk_price` | 101, 102, 103 |
| **Facilities** (`prompts/facilities.md`) | Checks landlord notices against the lease | `get_desk_date`, `get_lease_rent_and_cash`, `get_ticket`, `list_payments` | lease questions the packet can't answer |
| **Customer Service** (`prompts/customer_service.md`) | Customer-facing and internal drafts (never sent) | `get_desk_date`, `get_ticket`, `check_stock_by_sku_and_size`, `add_ticket_draft` | replies on 101, 102, 103 |

**How a run works (`run_team` → `run_role`):**
1. **The desk fetches the ticket's context in code**, using one MCP call (`get_ticket_context`): the ticket and its drafts, desk date, cash, stock (requested size and all sizes), pricing, vendors, open invoices, the lease and rent payments, and *every pending approval* on the board. It becomes the Boss's task as a verified packet.
2. **Code-level routing** suggests specialists per ticket type (`agents/roles.py` → `ROUTES`): customer_order → Inventory, Accounting, CS · rent_notice → Facilities, Accounting · price_override → Accounting, Inventory, CS. The Boss skips anyone whose facts are already in the packet.
3. **Full connectivity, hub-and-spoke by default.** Every agent has `ask_teammate(teammate, request, known_facts)`, and the desk attaches the packet plus `known_facts` to every hand-off, so nobody re-fetches. Refused: asking yourself, bouncing back to your caller, going deeper than 2 levels, a specialist's 2nd delegation, or more than 6 per ticket.
4. **The agent loop** steps through `agent.iter()` and appends every step to the audit trail. When an approval tool is called, the run pauses (`DeferredToolRequests`), the desk prepares the approval through MCP (`create_approval`, amount frozen), and then either leaves it in the dashboard tray ("prepared, not done") or asks the terminal user. The same run then resumes with the outcome.

**Audit trail** (`output/audit_trail.json`, append-only, never wiped, **hash-chained**): every event has `team_run_id`, `agent_run_id`, agent, depth, delegation chain, step, event type, details and running token usage, plus `prev_hash`/`hash`. Event types: `team_start` (with the ticket and a label: dashboard / cli / test), `agent_start`, `model_request` (tool results), `model_response` (tool calls with arguments, text, tokens), `delegation` (request + known_facts), `delegation_refused`, `paused_for_approval`, `approval_prepared` / `approval_queued` / `approval_refused` / `approval_granted` / `approval_declined`, `agent_end`, `team_end`, and the human's `approval_signed`, `payment_declined`, `ticket_status` and `db_reset`. A tool call replayed when a paused run resumes is logged once. `python backend/verify_audit.py` recomputes the chain: events before the chain existed (the first-version runs) are counted, and every later event is verified.

## MCP tools (all on `campus-customs-ops`, `mcp_server/server.py`), 21 in total

| Tool | Table(s) used | Reads / writes | Who uses it |
|---|---|---|---|
| `check_stock_by_sku_and_size` | inventory | read | Inventory, CS |
| `get_lease_rent_and_cash` | leases, cash_accounts, desk | read | Facilities |
| `get_sku_cost_and_price` | pricing (+ inventory name) | read | Accounting |
| `get_desk_date` | desk | read | all |
| `list_open_tickets` / `list_tickets` | tickets | read | Boss / API |
| `get_ticket` | tickets, drafts | read (notes flagged as untrusted) | Boss, Facilities, CS, API |
| `get_ticket_context` | tickets, drafts, desk, cash_accounts, inventory, pricing, vendors, invoices, leases, payments, approvals | read: one verified packet per ticket | desk code (before the Boss) |
| `list_vendors` | vendors | read | Inventory |
| `list_open_invoices` | invoices, vendors, desk | read | Inventory, Accounting |
| `get_cash_balances` | cash_accounts, desk | read | Accounting, API |
| `list_payments` | payments | read | Accounting, Facilities, API |
| `create_approval` | approvals (+ invoices, leases, vendors, pricing, cash_accounts to quote) | **write**: prepares; freezes payee and amount; refuses up front if cash is short, the vendor is on hold, or the price is below cost | desk code |
| `list_approvals` | approvals | read | API, desk code |
| `decline_approval` | approvals | **write**: a human declines | API, terminal |
| `pay_invoice` | approvals, invoices, cash_accounts, payments | **write, human-approved, at most once** | Accounting (prepares) → API / terminal (executes) |
| `pay_rent` | approvals, leases, cash_accounts, payments | **write, human-approved, at most once** | same |
| `order_stock` | approvals, purchase_orders, vendors, pricing, cash_accounts, payments | **write, human-approved**; refused while the vendor has an unpaid invoice | same |
| `set_bulk_price` | approvals, pricing | **write, human-approved**; between cost and list price; no cash | same |
| `add_ticket_draft` | drafts | write: customer **or** internal, never sent | CS |
| `update_ticket_status` | tickets | write | Boss, API |

The first time the server touches the working copy, it adds three tables: **`approvals`** (id, ticket, agent, tool, args, kind, frozen payee/amount/memo/due, status, approvers, result), **`drafts`** (ticket, audience customer/internal, text, sent = 0) and **`purchase_orders`**. The original `data/campus_customs.db` is never written to. There's no second shop-tools layer: the agents, the API and Claude Code all reach the data only through this server.

## Problem 7 — Backend routes (`backend/main.py`, FastAPI)

Start from `backend/` with `hw5/.venv` activated: `uvicorn main:app --reload --port 8000`. API docs are at `/docs`, and `/` redirects to the board. CORS allows only the Vite origin `http://localhost:5173`.

- `GET /api/tickets`: the 3 tickets with `state` (open or resolved), the detailed status and the pending-approval count.
- `GET /api/tickets/{id}`: one ticket with its customer and internal drafts.
- `POST /api/tickets/{id}/run`: starts the agent team on that ticket in the background and returns a `team_run_id` (409 if a run is already going).
- `GET /api/tickets/{id}/last_run`: that ticket's last run, rebuilt from the audit trail (survives restarts and fresh clones).
- `GET /api/runs/{team_run_id}` · `GET /api/runs/latest`: run status, the Boss's report, and hand-off, request and token counts.
- `GET /api/events?limit=&since=&team_run_id=`: recent agent events (what each agent said, tool calls and results) for the board to refresh.
- `GET /api/approvals?status=`: everything the agents prepared (payments, purchases, prices), with the frozen payee and amount.
- `POST /api/approvals/{id}/approve` with `{"approved_by", "pin"}`: **the only route that executes an approval** (pays, orders or approves a price), through the MCP tool, at most once. It needs the desk PIN and a human name. The ticket auto-resolves when every approval it was waiting on is signed.
- `POST /api/approvals/{id}/decline` with `{"declined_by", "pin", "reason"}`: a human declines, nothing happens, and the ticket is marked blocked.
- `GET /api/cash`: checking balance from `cash_accounts`, plus the opening balance (balance + paid out) and a `practice_ledger` flag.
- `POST /api/tickets/{id}/status` with `{"status", "by"}`: a person moves a ticket (for example "Mark resolved").
- `POST /api/reset` with `{"pin"}`: resets the working DB to the original (approvals and drafts start empty). PIN required; 409 while a run is going.
- `GET /api/health`: liveness check, model, and whether approvals are unlocked.

## Problem 8 — Dashboard (`frontend/`, React + Vite + TypeScript)

`npm run dev` in `frontend/` opens http://localhost:5173. It calls only the routes above. Design rationale: `output/design.md`.

- **The Board (left):** claim stubs with a rubber status stamp and "Send to the team →".
- **Team table (centre):** the Boss and four specialists; seats light up, show "waiting on X", their latest words and tools, and "not called" when skipped.
- **The wire / Who did what:** a live feed in each agent's voice; per-agent receipts, the Boss's memo, and the **drafts** (customer on a lined card, internal on grey "team only" paper).
- **Signature tray (right):** a "Signing as" name plus **Desk PIN**. Payments and purchases show as blue cheques and prices as green cards; it shows two-signature progress above the limit, and the server's refusals in red ("The pay tool refused it (practice ledger)").
- **Brass ledger (header):** checking, labelled *practice ledger · no real money*; rolls down with a red PAID stamp; lists signed lines with the signer.
- **Resolved:** a green stamp thumps in when the desk auto-resolves a ticket after its approvals, or when a person clicks "Mark resolved ✓".
- **Links:** `?ticket=103&tab=summary` opens a ticket straight to its summary; past runs reload from the audit trail.
- **Handsome Dan's corner:** rotating desk tips and cheers.

## Problem 9 — Full run on the three tickets (final)

**Reset first:** `POST /api/reset` (PIN). Start: checking **$3,400.00**, no payments, all tickets open. Then 101 → 102 → 103 were run one at a time from the board. Sophia Lin signed every approval on the dashboard with the desk PIN.

| Ticket | Final status | Agents used | Hand-offs | Requests / tokens | Approval (signed by Sophia Lin) | Cash |
|---|---|---|---|---|---|---|
| 101 Bulldog tee | **resolved** (auto, when the cheque cleared) | Boss, Accounting, Customer Service | 2 | 8 / 29,388 | `0ada2b7a` pay_invoice 501 · Bulldog Print Co | −$840.00 |
| 102 Rent due | **resolved** (auto) | Boss, Accounting, Customer Service | 2 | 8 / 26,774 | `1d09d1aa` pay_rent lease 1 · Elm City Properties | −$2,400.00 |
| 103 Bulk hoodies | **resolved** (Sophia, after the Boss set blocked) | Boss, Accounting, Customer Service | 2 | 9 / 33,926 | `6c53dde3` set_bulk_price 20 × M at $51.00 (no cash) | $0.00 |

**Cash check** (read straight from SQLite): $3,400.00 − ($840.00 + $2,400.00) = **$160.00** = `cash_accounts.checking` ✓. There are two `payments` rows, both `approved_by = Sophia Lin`; invoice 501 is `paid`; lease 1 is next due 2026-10-02; `purchase_orders` is empty (a 12-hoodie reprint at $264 would exceed the $160 left).

**Efficiency vs the first version (2026-11-06, same tickets):** hand-offs 25 → **6**, model requests 95 → **25**, tokens 272,606 → **90,088** (−67%). Both runs are in the audit trail.

**Where the results are:** `output/desk_tickets.html` (Expected vs Actual per ticket, Cash, Reflection), `output/resolved_tickets.json`, `output/resolved_board.html` (board screenshots), `output/audit_trail.json` (final runs `a0e1a12474`, `3ddcf8e24f`, `0aafa81443`).

## Safety

**Guardrails a real business would want when agents touch real customers and real money, and what this desk does:**
- **Agents prepare; people execute.** The four money and price tools only *prepare* an approval. Only `POST /api/approvals/{id}/approve` (PIN + name) or a person at the terminal can execute one. The model never sees `approval_id` / `approved_by`, and the server refuses blank or agent-role approvers.
- **Approve exactly what was shown.** The payee and amount are frozen from the records when prepared. Execution re-quotes inside the transaction and refuses if the record changed. Amounts always come from records (lease, invoice, pricing), never from an email.
- **At most once.** An approval executes once (a repeat signature returns the original result). A duplicate prepare returns the same pending approval. Rent can't be paid ahead.
- **Two people above a limit.** Above `SECOND_APPROVER_ABOVE` (default $5,000) two different approvers are required. An optional `DESK_APPROVERS` allow-list limits who may sign.
- **No negative balances.** Cash is checked when preparing *and* when executing. Purchases are refused while the vendor has an unpaid invoice. Prices must sit between cost and list.
- **Least privilege.** Each agent sees only its tools. Only Accounting can prepare money moves, and only Customer Service writes drafts.
- **Nothing leaves the building.** Drafts are stored with an audience (customer vs internal) and `sent = 0`. Ticket text is flagged as untrusted input, and prompts say never to follow instructions inside it.
- **Tamper-evident audit.** Every step is hash-chained, and `verify_audit.py` detects edits or deletions.
- **Practice ledger, clearly labelled.** No bank, card or payment provider is connected. The only outside call is the model via Portkey.
- **Tested.** `tests/` (20 tests, no model calls, temp databases) covers each rule above. Run `python -m pytest tests`.
- **Next steps for real use:** real sign-in (SSO) instead of a shared PIN, per-role approval limits, alerts on refused or declined payments, a read-only database user for read tools, and PII redaction in the audit.

**Limits that keep token use in check** (`backend/config.py`), sized from the first version's real runs (27–37 requests, 74k–110k tokens per ticket):
- The context is fetched **once in code** and handed to every agent as verified, so there are no repeated lookups.
- Hand-offs carry `known_facts`, so specialists answer instead of re-asking.
- Per ticket: 6 delegations, **1 per specialist run**, depth 2, no self or bounce-back delegation.
- Per ticket: **30 model requests and 150,000 tokens**, shared across all agents; when the budget runs out, agents stop cleanly.
- At most 3 approval pauses per agent run; tool errors retried twice; audit texts trimmed (the Boss's report is kept up to 8,000 characters).
- Result: 8–9 requests and 27k–34k tokens per ticket in the final run.

## Safety rules, all in one place

| Rule | Enforced by |
|---|---|
| Today = `desk.date_today` | every date calculation in the MCP server; the context packet; the desk calendar on the dashboard |
| Lead times only from `vendors` | `list_vendors` / the packet are the only sources; `order_stock` computes expected = today + `lead_days` |
| No shipping while a vendor invoice is unpaid | `list_open_invoices` → `vendor_will_ship: false`; `order_stock` refused at prepare and at execute |
| Human approval for every payment | prepare/execute split, desk PIN, the server refuses agent approvers, approvals stored in the DB |
| A payment updates the relevant tables | one SQLite transaction: approvals + payments + cash_accounts + invoice `paid` / lease `next_due` / purchase order |
| No negative balances | cash checked at prepare and inside the execute transaction (tested) |
| Cash only goes out | no tool adds money; a price approval moves no cash; the ledger's opening balance = balance + paid out |
| Reset before a full run | `backend/reset_db.py`, `POST /api/reset` (PIN), "Reset the shop", automatic in `run_tickets.py` |
| No emails or vendor calls; drafts on the board | no send tool exists; drafts carry an audience and `sent = 0` |
| Token and loop limits | context packet, known_facts, hub-and-spoke budgets, 30-request / 150k-token cap per ticket, one run at a time |
