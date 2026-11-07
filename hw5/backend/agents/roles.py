"""The five roles: which MCP tools each may use, and what teammates know them for.

Every shop fact comes from the campus-customs-ops MCP server; this file only
decides which of its tools each agent can see.
"""

from __future__ import annotations

from models import Role

ROLE_TOOLS: dict[Role, frozenset[str]] = {
    "boss": frozenset({
        "get_desk_date", "list_open_tickets", "get_ticket", "update_ticket_status",
    }),
    "inventory": frozenset({
        "get_desk_date", "check_stock_by_sku_and_size", "list_vendors", "list_open_invoices",
    }),
    "accounting": frozenset({
        "get_desk_date", "get_cash_balances", "list_open_invoices", "get_sku_cost_and_price",
        "list_payments", "pay_invoice", "pay_rent",
    }),
    "facilities": frozenset({
        "get_desk_date", "get_lease_rent_and_cash", "get_ticket", "list_payments",
    }),
    "customer_service": frozenset({
        "get_desk_date", "list_open_tickets", "get_ticket", "check_stock_by_sku_and_size",
        "add_ticket_draft",
    }),
}

ROLE_SUMMARY: dict[Role, str] = {
    "boss": "runs the ticket board and makes the final call on each ticket",
    "inventory": "stock by SKU/size and aisle, vendors, lead times, open-invoice shipping holds",
    "accounting": "cash, open invoices, cost/price/margin, and payments (human-approved)",
    "facilities": "leases, rent and due dates, verifying landlord notices",
    "customer_service": "reading tickets and saving customer-facing drafts (never sent)",
}
