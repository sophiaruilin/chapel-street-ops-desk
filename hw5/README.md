# HW 5 — Campus Customs Multi-Agent Operations

Five PydanticAI agents (**Boss, Inventory, Accounting, Facilities, Customer Service**) work the Campus Customs ticket board. They get every shop fact from one **MCP server** over a SQLite database, a **FastAPI** backend runs them, and a **React** desk lets a person watch the agents and sign (or decline) what they prepare. No agent can move money: agents only *prepare* payments, purchases and prices, and only a person's signature (name + desk PIN) executes one, exactly once, at the amount shown. The "checking account" is a practice ledger in SQLite: no bank or card is connected.

```
hw5/
├── AI_prompts.md            prompt log for every problem
├── requirements.txt         one Python environment for everything
├── .env.example             copy to .env and add your Portkey key
├── .gitignore               keeps .env, .venv and node_modules out of git
├── .mcp.json                lets Claude Code connect to the MCP server
├── README.md                this file
├── data/
│   ├── campus_customs.db       the ORIGINAL database (never modified)
│   └── campus_customs_new.db   the WORKING copy the app reads and writes
├── mcp_server/
│   ├── server.py            FastMCP server "campus-customs-ops" (21 tools)
│   └── README.md
├── frontend/                React + Vite + TypeScript ops desk (npm run dev)
├── backend/
│   ├── main.py              FastAPI routes the desk calls
│   ├── models.py            data types
│   ├── prompts/             boss.md, inventory.md, accounting.md, facilities.md,
│   │                        customer_service.md (+ shop_rules.md shared by all)
│   ├── agents/              the team, the agent loop, MCP wiring, role → tool map
│   ├── config.py · audit.py · reset_db.py · run_tickets.py · verify_audit.py
└── output/
    ├── harness.md           tables, MCP tools, agents, routes, dashboard, safety
    ├── mcp_smoke.json       MCP tool smoke test from Claude Code
    ├── desk_tickets.html    expected vs actual per ticket, cash, reflection
    ├── design.md            dashboard design notes
    ├── resolved_tickets.json
    ├── resolved_board.html  board screenshots per ticket (self-contained)
    ├── audit_trail.json     every agent-loop step, append-only and hash-chained
    └── github_url.txt
(tests/                     20 pytest tests for the shop rules: no model calls)
```

## 0 · One-time setup

You need **Python 3.11+** and **Node 20+**.

```bash
cd hw5
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env            # macOS/Linux: cp .env.example .env
# then edit .env: set PORTKEY_API_KEY=<your class Portkey key>
#                 and DESK_APPROVAL_PIN=<a PIN you choose> (needed to sign on the desk)

cd frontend
npm install
cd ..
```

Every agent uses `gpt-6-astra` (reasoning effort medium) through Portkey and the OpenAI Responses API (`backend/config.py`). `MODEL_NAME` in `.env` can override it.

## 1 · Get a clean database: copy the original to the working copy

`data/campus_customs.db` is the original and is never written to. The app only uses `data/campus_customs_new.db`. **Whenever you want a clean run, copy the original over the working copy.** Any one of these does it:

```bash
python backend/reset_db.py                                   # from hw5/
copy data\campus_customs.db data\campus_customs_new.db       # Windows by hand
cp data/campus_customs.db data/campus_customs_new.db         # macOS/Linux by hand
```

Once the backend is running you can also click **↺ Reset the shop** on the desk, or call `POST http://localhost:8000/api/reset`. Those also clear any queued (unsigned) payments.

> The committed working copy holds the end of the final Problem 9 run: all three tickets resolved, checking $160.00, two signed payments, and the approvals and drafts in their tables. It's consistent as committed, so the board shows exactly that state. **Reset before you start a new run** (step 5).

## 2 · Start the MCP server (optional on its own)

The backend starts the MCP server **automatically** as a stdio subprocess, so you don't need a separate terminal for the app. To run or inspect it on its own:

```bash
python mcp_server/server.py           # stdio (how the agents and Claude Code launch it)
python mcp_server/server.py --http    # or HTTP at http://127.0.0.1:8002/mcp
```

**Claude Code:** open this `hw5/` folder and approve the `campus-customs-ops` server from `.mcp.json` (with the venv activated so `python` has `fastmcp`). Then the 15 tools are available, for example `check_stock_by_sku_and_size`. See `mcp_server/README.md` for the full tool list.

## 3 · Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

This serves http://localhost:8000 (interactive docs at http://localhost:8000/docs) and allows the Vite origin `http://localhost:5173`. Every route is listed in `output/harness.md`.

## 4 · Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Pick a ticket on the left and click **Send to the team →**. Watch the agents on the team table and the live wire. When a payment is prepared it lands in the **Signature tray**: type your name and **Sign & pay** (checking drops), or **Decline**.

**Signing:** in the Signature tray, type your name under **Signing as** and your **Desk PIN** (from `.env`). Then use **Sign & pay** on a cheque, **Sign & order** on a purchase order, or **Approve price** on a green price card (or **Decline**). Each executes once, at the frozen amount. Amounts above `SECOND_APPROVER_ABOVE` (default $5,000) need a second, different person. Opening http://localhost:8000 redirects to the board.

## 5 · A full three-ticket run

1. **Reset the database** (step 1, or **↺ Reset the shop**). Checking should read **$3,400.00**.
2. Send **101**, wait for "Run complete", then **102**, then **103**. Runs go one at a time.
3. Sign or decline what lands in the tray (name + desk PIN). Tickets that were only waiting on a signature resolve automatically. Anything else, use **Mark resolved ✓** when you're satisfied.
4. If you sign both: $3,400.00 − $840.00 (invoice 501) − $2,400.00 (rent) = **$160.00**. The pay tools refuse anything that would go negative.

Terminal-only alternative, with no browser: `cd backend` then `python run_tickets.py`. It resets first, works all open tickets, and asks you in the terminal before any payment.

## Shop rules (enforced in code, not just prompts)

`desk.date_today` is "today" · lead times only from `vendors` · a vendor with an open unpaid invoice won't ship · **every payment needs human approval** and updates `payments` + `cash_accounts` + the invoice or lease together · **no negative balances** · cash only goes out · reset before a full run · no emails or vendor calls, so drafts stay on the board. Details: `output/harness.md`.

## Tests and audit check

```bash
python -m pytest tests            # from hw5/: 20 tests, temp databases, no model calls
cd backend && python verify_audit.py   # recomputes the audit trail's hash chain (exit 0 = intact)
```

