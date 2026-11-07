# HW 5 — Campus Customs Multi-Agent Operations harness

Database: `data/campus_customs_new.db` (working copy of the original `data/campus_customs.db`, which stays untouched).

**What's in this harness:** shop rules (R1–R8) → database tables (P2) → MCP tools (P3 + full list) → the five agents (P5) → safety guardrails and token limits → API routes (P7) → dashboard (P8) → the full run and how to reproduce it (P9).

**How to run everything** (three terminals):
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
| R4 | Human approval is required for any payment, and a payment must update the relevant tables. | `pay_invoice` and `pay_rent` pause the agent run for a human in the terminal. Only the human's typed name fills `payments.approved_by`, and the server refuses a blank or agent-role approver. In one transaction each inserts the `payments` row, lowers `cash_accounts.balance`, and marks the invoice `paid` or advances `leases.next_due` one month. |
| R5 | If there is not enough cash, the pay tool must refuse. No negative balances. | Both pay tools check `balance >= amount` inside the transaction and refuse otherwise, with nothing written (tested with $500 in checking). |
| R6 | Cash only goes out. No revenue is modeled, so no money comes in. | Nothing ever raises a cash balance. Selling hoodies in ticket 103 does not add cash, so ticket planning has to fit the $3,400 in checking. |
| R7 | Before a full run to resolve the tickets, reset the database to its original values. | Run `python backend/reset_db.py`. It copies `data/campus_customs.db` over `data/campus_customs_new.db`. |
| R8 | Do not email customers or call real vendors. Drafts stay on the board. | Agents only write drafts. No tool sends email or contacts anyone outside the shop. |

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

All five agents are PydanticAI agents in `backend/agents/team.py`. Prompts are in `backend/prompts/` (one file per agent, plus `shop_rules.md`, which is inserted into all of them). Data types are in `backend/models.py`. Every agent uses the same model: **gpt-6-astra via Portkey, Responses API, reasoning effort medium** (see `backend/config.py`). Run with `backend/run_tickets.py`.

| Agent | Job | MCP tools it can call | Can delegate to |
|---|---|---|---|
| **Boss** (`prompts/boss.md`) | Reads the board, delegates, checks total cash across tickets before any payment, sets ticket status, writes the final report | `get_desk_date`, `list_open_tickets`, `get_ticket`, `update_ticket_status` | everyone |
| **Inventory** (`prompts/inventory.md`) | Stock and aisle by SKU/size, vendor and lead time, the open-invoice shipping hold | `get_desk_date`, `check_stock_by_sku_and_size`, `list_vendors`, `list_open_invoices` | everyone |
| **Accounting** (`prompts/accounting.md`) | Cash math, open invoices, cost/price/margin, payments (human-approved) | `get_desk_date`, `get_cash_balances`, `list_open_invoices`, `get_sku_cost_and_price`, `list_payments`, `pay_invoice`, `pay_rent` | everyone |
| **Facilities** (`prompts/facilities.md`) | Checks landlord notices against the lease on file | `get_desk_date`, `get_lease_rent_and_cash`, `get_ticket`, `list_payments` | everyone |
| **Customer Service** (`prompts/customer_service.md`) | Writes draft replies on the board (never sent) | `get_desk_date`, `list_open_tickets`, `get_ticket`, `check_stock_by_sku_and_size`, `add_ticket_draft` | everyone |

**Full connectivity:** every agent has `ask_teammate(teammate, request)`, which runs the teammate as its own agent loop and returns its report. Refused: asking yourself, asking back the agent that just asked you, going deeper than 2 levels, or going over 12 delegations in a run.

**Agent loop** (`run_role`): it steps through `agent.iter()`, and every step is appended to `output/audit_trail.json`. When a pay tool is called, the run pauses (`DeferredToolRequests`), a human approves or declines in the terminal, and the same run resumes with that decision.

**Audit trail** (`output/audit_trail.json`, append-only, never wiped): each event records the team run id, agent run id, agent, depth, delegation chain, step number, and the event type (`team_start`, `agent_start`, `model_request` with tool results, `model_response` with tool calls and arguments, text and token counts, `delegation`, `delegation_refused`, `paused_for_approval`, `approval` with the approver's name or the reason for declining, `agent_end`, `team_end`, `error`). It also records the team's running token and request usage.

## MCP tools (all on `campus-customs-ops`, `mcp_server/server.py`)

| Tool | Table(s) used | Reads or writes | Added in |
|---|---|---|---|
| `check_stock_by_sku_and_size` | inventory | read | P3 |
| `get_lease_rent_and_cash` | leases, cash_accounts, desk | read | P3 |
| `get_sku_cost_and_price` | pricing (+ inventory for the name) | read | P3 |
| `get_desk_date` | desk | read | P5 |
| `list_open_tickets` | tickets | read | P5 |
| `list_tickets` | tickets (all, including resolved) | read; used by the API's ticket list | P7 |
| `get_ticket` | tickets | read | P5 |
| `list_vendors` | vendors | read | P5 |
| `list_open_invoices` | invoices, vendors, desk | read | P5 |
| `get_cash_balances` | cash_accounts, desk | read | P5 |
| `list_payments` | payments | read | P5 |
| `pay_invoice` | invoices, cash_accounts, payments, desk | **write, human approval** | P5 |
| `pay_rent` | leases, cash_accounts, payments, desk | **write, human approval** | P5 |
| `add_ticket_draft` | tickets (notes), desk | write (draft only, nothing sent) | P5 |
| `update_ticket_status` | tickets (status) | write | P5 |

There is no second shop-tools layer. The agents reach the database only through this MCP server, which runs as a stdio subprocess the same way Claude Code launches it.

## Safety

**Guardrails a real business would want when agents touch real customers and real money:**
- **A human approves every payment.** Pay tools are gated in the agent code, the model never sees `approved_by`, and the server refuses a blank or agent-role approver. A real business would add per-amount limits (for example two approvers above $1,000) and sign-in tied to real identities, not a typed name.
- **The amount comes from the record, never from the message.** Rent is paid at `leases.monthly_rent` and invoices at `invoices.amount`. Email amounts are claims to verify, which also protects against invoice-fraud and phishing emails.
- **No negative balances and no double payments.** The server checks cash before writing, refuses an invoice that isn't open, and refuses rent already paid ahead. Each payment is one transaction across `payments`, `cash_accounts` and the invoice or lease.
- **Least privilege.** Each agent sees only the tools its role needs. Only Accounting can pay, only Customer Service writes customer drafts, and only the Boss closes tickets.
- **Nothing leaves the building.** Customer and vendor messages are drafts on the board. A human reviews and sends them.
- **Facts only from tools.** The prompts forbid invented numbers, and the audit trail lets a person check every claim against the tool result behind it.
- **Full, append-only audit trail** of every model call, tool call, delegation and approval, plus a database reset before each full run so test runs never build on each other.
- **Next steps for real use:** run the agents read-only by default, use a separate least-privilege database user, add alerts on refused or declined payments, and keep personal customer data out of prompts unless it's needed.

**Limits that keep token use in check** (`backend/config.py`):
- Delegation depth of 2 at most, 12 delegations per team run, no self-delegation and no bounce-back to the caller (stops A→B→A loops).
- One shared team budget: 60 model requests and 400,000 tokens across all agents. When it runs out, agents stop cleanly and report what they have.
- At most 3 approval pauses per agent run, 2 retries per tool error, long text trimmed to 1,500 characters in the audit trail.
- Focused requests: the Boss is told to send short, self-contained requests and to delegate only to the specialist who holds the facts, with about 12 delegations per run.
- Example: a live run on ticket 102 alone used 8 delegations, 28 requests and about 74k tokens.

## Problem 7 — Backend routes (`backend/main.py`, FastAPI)

Start from `backend/`: `uvicorn main:app --reload --port 8000`. Base URL: `http://localhost:8000`, API docs at `/docs`. Every route gets shop data through the `campus-customs-ops` MCP server.

- `GET /api/tickets`: the 3 tickets, each with `state` open or resolved (plus the detailed status and pending-approval count).
- `GET /api/tickets/{id}`: one ticket in full, including the draft replies saved in its notes.
- `POST /api/tickets/{id}/run`: starts the agent team on that one ticket in the background and returns a `team_run_id` (409 if a run is already going).
- `POST /api/tickets/{id}/status` with body `{"status": "resolved", "by": "Name"}`: a human moves a ticket on the board, for example "Mark resolved" on the dashboard (added in Problem 8).
- `GET /api/runs/{team_run_id}` and `GET /api/runs/latest` (null before the first run): the run's status (running, finished or failed), the Boss's final report, and its delegation, request and token counts.
- `GET /api/events?limit=50&since=N&team_run_id=X`: recent agent events from `audit_trail.json`, showing what each agent said, which tools it called with which arguments, and the tool results. `since` lets the board fetch only new events.
- `GET /api/approvals?status=pending`: payments the agents prepared and that are waiting for a human, each with a `preview` (payee, amount, memo, due date) looked up through MCP so the human sees what they are signing.
- `POST /api/approvals/{id}/approve` with body `{"approved_by": "Full Name"}`: a human approves, and **this is the only route that pays**. It calls `pay_invoice`/`pay_rent` on the MCP server, which changes `cash_accounts`, `payments` and the invoice or lease, or refuses if cash is short.
- `POST /api/approvals/{id}/decline` with body `{"reason": "..."}`: a human declines, and nothing is paid.
- `GET /api/cash`: the current checking balance from `cash_accounts`.
- `POST /api/reset`: resets `campus_customs_new.db` to the original values and clears queued payments, for a fresh run (409 while a run is going).
- `GET /api/health`: liveness check and model name.

**How a dashboard payment works:** during a run, an agent's `pay_invoice`/`pay_rent` call pauses. The backend records it in `output/pending_approvals.json` and tells the agent "prepared, not paid", so the agents never move cash themselves. When a human clicks Approve, the approve route makes the payment with that person's name as `approved_by`. Approvals, declines and refusals are appended to `audit_trail.json` as well.

## Problem 8 — Dashboard (`frontend/`, React + Vite + TypeScript)

Start it with `npm run dev` from `frontend/` (http://localhost:5173). It calls only the Problem 7 routes at http://localhost:8000 (`src/api.ts`), and the backend's CORS allows only the Vite origin. The full design rationale is in `output/design.md`.

- **The Board (left):** the 3 tickets as claim stubs with a rubber status stamp (Open, Awaiting signature, Blocked, Resolved) and a "Send to the team →" button (`POST /api/tickets/{id}/run`).
- **Team table (centre):** the Boss and four specialists. Each seat shows thinking, "waiting on X" or done, the agent's latest words and its tools, live from `GET /api/events` every 1.5 s.
- **The wire / Who did what (centre tabs):** a live feed where each agent writes in its own voice (memo, stockroom tag, ledger, notice, handwritten note), then per-agent receipts and the Boss's memo when the run finishes.
- **Signature tray (right):** each prepared payment as a cheque (payee, amount, memo, due date). **Sign & pay** calls `POST /api/approvals/{id}/approve`, the only path that moves cash; Decline is also offered.
- **Brass ledger (header):** checking from `GET /api/cash`. It counts down with a red "PAID" stamp after an approved payment. Next to it are the desk-date calendar and "Reset the shop" (`POST /api/reset`).
- **Resolved tickets:** the stamp shows the database status. After a run, "Mark resolved ✓" (`POST /api/tickets/{id}/status`) appears once no cheque is pending for that ticket.
- **Handsome Dan's corner:** rotating one-line desk tips, plus cheers on runs and payments.

## Problem 9 — Full run on the three tickets

**Reset first:** `POST /api/reset`, confirmed byte-identical to the original database. Starting checking **$3,400.00**, no payments, all tickets open. Then 101 → 102 → 103 were run one at a time from the React board. On the user's instruction (*"don't send any money but just let it sit"*), the two cheques the agents prepared were **left unsigned**: not approved and not declined.

| Ticket | Final status | Agents used | Hand-offs (refused) | Requests / tokens | Money |
|---|---|---|---|---|---|
| 101 Bulldog tee | `waiting_approval` | Boss, Inventory, Accounting, Customer Service | 7 (5) | 27 / 74,440 | $840 `pay_invoice(501)` prepared, approval `5ef259bd` pending |
| 102 Rent due | `waiting_approval` | Boss, Facilities, Accounting, Customer Service | 9 (3) | 31 / 88,170 | $2,400 `pay_rent(1)` prepared, approval `60ca7e64` pending |
| 103 Bulk hoodies | `blocked` | all five | 9 (9) | 37 / 109,996 | none |

**Cash check** (read straight from SQLite): start $3,400.00 − payments $0.00 = **$3,400.00** = `cash_accounts.checking` ✓. The `payments` table is empty, invoice 501 is still open, and lease 1 is still due 2026-09-02. If both cheques are signed later: $3,400 − $840 − $2,400 = **$160.00**.

**Where the results are:** `output/desk_tickets.html` (Expected vs Actual per ticket, the Cash tab and the Reflection tab), `output/resolved_tickets.json` (per ticket: status, outcome, each agent's contribution and tools, approvals), `output/resolved_board.html` (board screenshots per ticket) and `output/audit_trail.json` (every step, appended; the three real runs are `a02b5d3e49`, `ada701f573` and `c7e2bbaa10`).

**Audit note:** when a paused run resumes after an approval decision, PydanticAI replays the paused tool call, so the trail logs that call twice with the same `tool_call_id`. Count tool calls by unique `tool_call_id`; there was exactly one prepared payment per ticket.

## Safety rules, all in one place

| Rule | Enforced by |
|---|---|
| Today = `desk.date_today` | every date calculation in the MCP server; the desk calendar on the dashboard |
| Lead times only from `vendors` | `list_vendors` is the only source; prompts forbid estimating |
| No shipping while a vendor invoice is unpaid | `list_open_invoices` → `vendor_will_ship: false`; Inventory prompt |
| Human approval for every payment | agent-side approval gate (the model never sees `approved_by`), dashboard cheques with a typed signature, server refuses blank or agent-role approvers |
| A payment updates the relevant tables | one SQLite transaction: `payments` + `cash_accounts` + invoice `paid` or lease `next_due` +1 month |
| No negative balances | pay tools check the balance inside the transaction and refuse (tested at $500) |
| Cash only goes out | no tool adds money; ledger gauge on the dashboard |
| Reset before a full run | `backend/reset_db.py`, `POST /api/reset`, the "Reset the shop" button, and automatic in `run_tickets.py` |
| No emails or vendor calls; drafts on the board | no send tool exists; `add_ticket_draft` marks every draft "not sent" |
| Token and loop limits | depth 2, 12 delegations per run, no self or bounce-back delegation, a 60-request / 400k-token team budget, one run at a time |
