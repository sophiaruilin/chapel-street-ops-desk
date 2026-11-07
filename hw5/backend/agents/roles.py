"""The five roles: which MCP tools each may use, who usually works each ticket type.

Every shop fact comes from the campus-customs-ops MCP server; this file only
decides which of its tools each agent can see (least privilege) and the
suggested route per ticket type (code-level routing, so the model spends its
tokens on judgment instead of on deciding who to ask).
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
        "get_desk_date", "get_cash_balances", "list_open_invoices", "get_sku_cost_and_price", "list_payments",
        "pay_invoice", "pay_rent", "order_stock", "set_bulk_price",   # all four only PREPARE for a human
    }),
    "facilities": frozenset({
        "get_desk_date", "get_lease_rent_and_cash", "get_ticket", "list_payments",
    }),
    "customer_service": frozenset({
        "get_desk_date", "get_ticket", "check_stock_by_sku_and_size", "add_ticket_draft",
    }),
}

ROLE_SUMMARY: dict[Role, str] = {
    "boss": "runs the ticket board and makes the final call on each ticket",
    "inventory": "stock by SKU/size and aisle, vendors, lead times, open-invoice shipping holds",
    "accounting": "cash, invoices, cost/price/margin; prepares payments, purchases and price approvals",
    "facilities": "leases, rent and due dates, verifying landlord notices",
    "customer_service": "customer-facing and internal drafts (never sent)",
}

# Suggested team per ticket type, in the order the Boss should usually ask them.
ROUTES: dict[str, list[Role]] = {
    "customer_order": ["inventory", "accounting", "customer_service"],
    "rent_notice": ["facilities", "accounting"],
    "price_override": ["accounting", "inventory", "customer_service"],
}
DEFAULT_ROUTE: list[Role] = ["inventory", "accounting", "facilities", "customer_service"]
