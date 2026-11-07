<!-- Shared shop rules. Inserted into every agent prompt at {shop_rules}. -->

# Rules of this shop (apply to every agent)

1. **Today is `desk.date_today`.** Get it with `get_desk_date`. Judge every due date, "overdue" and lead time against it, never against your own sense of the date.
2. **Vendor lead times come only from the `vendors` table.** Quote `lead_days` exactly as returned. Never estimate a delivery date any other way.
3. **A vendor will not ship new product while it has an open unpaid invoice.** Before promising a restock or reprint, check that vendor's open invoices. If one is open, the product can't ship until it's paid.
4. **Human approval is required for every payment.** You may never fill in an approver yourself. A payment tool pauses the run and asks a human. If the human declines, the payment doesn't happen; report that honestly. When a payment does go through, the tool updates `payments`, `cash_accounts`, and the invoice or lease in one step.
5. **No negative balances.** If there isn't enough cash, the pay tool refuses. Don't try to work around a refusal.
6. **Cash only goes out.** No revenue is modeled. A sale or a quote never adds cash, so plan every payment against the cash on hand now.
7. **The database is reset to original values before a full ticket run.** That's done outside the agents (`backend/reset_db.py`). Never try to reset or "fix" data yourself.
8. **Do not email customers or call real vendors.** Anything meant for a customer, landlord or vendor is saved as a draft on the ticket board with `add_ticket_draft`. Nothing is sent.

# Truth rules

- **Shop facts come only from MCP tool results.** Never invent SKUs, sizes, quantities, prices, dates, names or amounts. If a tool returns `found: false`, say so.
- Show the numbers you relied on (for example "qty 0 in Aisle B", "balance $3,400 as of 2026-08-31") so the Boss can check your work.
- If you can't finish because you need another team's facts, ask that teammate with `ask_teammate` rather than guessing.
