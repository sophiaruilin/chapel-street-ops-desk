"""The one link between the agents and the shop: the campus-customs-ops MCP server.

The server runs as a stdio subprocess (the same way Claude Code launches it).
Each agent gets a filtered view of its tools. The four approval tools
(pay_invoice, pay_rent, order_stock, set_bulk_price) are wrapped so calling
one pauses the run for a human, and their `approval_id` / `approved_by`
arguments are hidden from the model so only the human's decision can fill them.
The harness itself also calls a few tools directly (ticket context, approvals)
through `mcp_call`, still over MCP.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.tools import ToolDefinition

from agents.roles import ROLE_TOOLS
from config import MCP_SERVER_PYTHON, MCP_SERVER_SCRIPT, mcp_env
from models import APPROVAL_TOOLS, Role, TeamDeps

HIDDEN_ARGS = ("approval_id", "approved_by")
_shared: MCPToolset | None = None


def shop_mcp() -> MCPToolset:
    """The single MCPToolset (one server process) shared by every agent and the harness."""
    global _shared
    if _shared is None:
        transport = StdioTransport(command=str(MCP_SERVER_PYTHON), args=[str(MCP_SERVER_SCRIPT)],
                                   cwd=str(MCP_SERVER_SCRIPT.parent), env=mcp_env())
        _shared = MCPToolset(Client(transport), id="campus-customs-ops", tool_error_behavior="failed")
    return _shared


async def mcp_call(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call an MCP tool from harness code (inside `async with shop_mcp():`)."""
    res = await shop_mcp().client.call_tool(tool, args or {}, raise_on_error=False)
    if res.is_error:
        raise RuntimeError(f"MCP tool {tool} failed: {' '.join(getattr(c, 'text', '') for c in res.content)}")
    if res.structured_content is not None:
        return res.structured_content
    return json.loads(res.content[0].text)


def _hide_approval_args(td: ToolDefinition) -> ToolDefinition:
    schema = copy.deepcopy(td.parameters_json_schema)
    for arg in HIDDEN_ARGS:
        schema.get("properties", {}).pop(arg, None)
    if "required" in schema:
        schema["required"] = [p for p in schema["required"] if p not in HIDDEN_ARGS]
    note = (" Calling this PREPARES it for a human: the run pauses, the amount is frozen from the records, and a"
            " person signs or declines. It is not done until the result says so.")
    return replace(td, parameters_json_schema=schema, description=(td.description or "") + note)


async def _prepare(ctx: RunContext[TeamDeps], tool_defs: list[ToolDefinition]) -> list[ToolDefinition]:
    return [_hide_approval_args(td) if td.name in APPROVAL_TOOLS else td for td in tool_defs]


def toolset_for(role: Role) -> AbstractToolset[TeamDeps]:
    """The MCP tools this role may call, with approval tools gated behind a human."""
    allowed = ROLE_TOOLS[role]
    return (
        shop_mcp()
        .filtered(lambda ctx, td: td.name in allowed)
        .prepared(_prepare)
        .approval_required(lambda ctx, td, args: td.name in APPROVAL_TOOLS)
    )
