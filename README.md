# Chapel Street Ops Desk · Campus Customs (HW 5)

Multi-agent operations for the Campus Customs shop: five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service) work a ticket board through one MCP server over SQLite. A FastAPI backend runs them, and a React desk lets a human watch the team and sign any payment.

**See it online (GitHub Pages):** https://sophiaruilin.github.io/chapel-street-ops-desk/
- Board gallery (screenshots of the React desk): https://sophiaruilin.github.io/chapel-street-ops-desk/hw5/output/resolved_board.html
- Plan vs actual, cash, reflection: https://sophiaruilin.github.io/chapel-street-ops-desk/hw5/output/desk_tickets.html

**Everything is in [`hw5/`](hw5/).** Start with [`hw5/README.md`](hw5/README.md) for setup, the clean-database reset, and how to start the MCP server, the backend and the board.

- Harness (tables, MCP tools, agents, routes, dashboard, safety): [`hw5/output/harness.md`](hw5/output/harness.md)
- Source of the pages above: [`hw5/output/desk_tickets.html`](hw5/output/desk_tickets.html), [`hw5/output/resolved_board.html`](hw5/output/resolved_board.html)
