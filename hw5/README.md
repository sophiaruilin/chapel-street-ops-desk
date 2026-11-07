# HW 5 — Campus Customs Multi-Agent Operations

Five PydanticAI agents (**Boss, Inventory, Accounting, Facilities, Customer Service**) work the Campus Customs ticket board. They get every shop fact from one **MCP server** over a SQLite database, a **FastAPI** backend runs them, and a **React** desk lets a person watch the agents and sign (or decline) any payment. No agent can move money: only a human's signature on the dashboard does.

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
│   ├── server.py            FastMCP server "campus-customs-ops" (15 tools)
│   └── README.md
├── frontend/                React + Vite + TypeScript ops desk (npm run dev)
├── backend/
│   ├── main.py              FastAPI routes the desk calls
│   ├── models.py            data types
│   ├── prompts/             boss.md, inventory.md, accounting.md, facilities.md,
│   │                        customer_service.md (+ shop_rules.md shared by all)
│   ├── agents/              the team, the agent loop, MCP wiring, role → tool map
│   ├── config.py · audit.py · approvals.py · reset_db.py · run_tickets.py
└── output/
    ├── harness.md           tables, MCP tools, agents, routes, dashboard, safety
    ├── mcp_smoke.json       MCP tool smoke test from Claude Code
    ├── desk_tickets.html    expected vs actual per ticket, cash, reflection
    ├── design.md            dashboard design notes
    ├── resolved_tickets.json
    ├── resolved_board.html  board screenshots per ticket (self-contained)
    ├── audit_trail.json     every agent-loop step, append-only
    └── github_url.txt
```

## 0 · One-time setup

You need **Python 3.11+** and **Node 20+**.

```bash
cd hw5
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env            # macOS/Linux: cp .env.example .env
# then edit .env and set PORTKEY_API_KEY=<your class Portkey key>

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

> The committed working copy holds the state at the end of my Problem 9 run (tickets 101/102 `waiting_approval`, 103 `blocked`, drafts on the tickets, checking $3,400.00, nothing paid). The pending-payment queue isn't committed, so **reset before you start** (step 5).

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

## 5 · A full three-ticket run

1. **Reset the database** (step 1, or **↺ Reset the shop**). Checking should read **$3,400.00**.
2. Send **101**, wait for "Run complete", then **102**, then **103**. Runs go one at a time.
3. Sign or decline the cheques in the tray. Rent and invoice payments must be signed by a person.
4. If you sign both: $3,400.00 − $840.00 (invoice 501) − $2,400.00 (rent) = **$160.00**. The pay tools refuse anything that would go negative.

Terminal-only alternative, with no browser: `cd backend` then `python run_tickets.py`. It resets first, works all open tickets, and asks you in the terminal before any payment.

## Shop rules (enforced in code, not just prompts)

`desk.date_today` is "today" · lead times only from `vendors` · a vendor with an open unpaid invoice won't ship · **every payment needs human approval** and updates `payments` + `cash_accounts` + the invoice or lease together · **no negative balances** · cash only goes out · reset before a full run · no emails or vendor calls, so drafts stay on the board. Details: `output/harness.md`.
