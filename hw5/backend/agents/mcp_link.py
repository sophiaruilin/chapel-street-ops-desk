"""The one link between the agents and the shop: the campus-customs-ops MCP server.

The server runs as a stdio subprocess (the same way Claude Code launches it).
Each agent gets a filtered view of its tools; payment tools are wrapped so they
pause for human approval, and their `approved_by` argument is hidden from the
model so only the human's own answer can fill it in.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.tools import ToolDefinition

from agents.roles import ROLE_TOOLS
from config import MCP_SERVER_PYTHON, MCP_SERVER_SCRIPT
from models import PAY_TOOLS, Role, TeamDeps

_shared: MCPToolset | None = None


def shop_mcp() -> MCPToolset:
    """The single MCPToolset (one server process) shared by every agent."""
    global _shared
    if _shared is None:
        transport = StdioTransport(
            command=str(MCP_SERVER_PYTHON),
            args=[str(MCP_SERVER_SCRIPT)],
            cwd=str(MCP_SERVER_SCRIPT.parent),
        )
        # tool_error_behavior="failed": the model sees a server error instead of silent retries.
        _shared = MCPToolset(Client(transport), id="campus-customs-ops", tool_error_behavior="failed")
    return _shared


def _hide_approved_by(td: ToolDefinition) -> ToolDefinition:
    schema = copy.deepcopy(td.parameters_json_schema)
    schema.get("properties", {}).pop("approved_by", None)
    if "required" in schema:
        schema["required"] = [p for p in schema["required"] if p != "approved_by"]
    note = (" The approver is filled in by the human who approves this payment;"
            " calling this tool pauses the run for that approval.")
    return replace(td, parameters_json_schema=schema, description=(td.description or "") + note)


async def _prepare(ctx: RunContext[TeamDeps], tool_defs: list[ToolDefinition]) -> list[ToolDefinition]:
    return [_hide_approved_by(td) if td.name in PAY_TOOLS else td for td in tool_defs]


def toolset_for(role: Role) -> AbstractToolset[TeamDeps]:
    """The MCP tools this role may call, with payments gated behind human approval."""
    allowed = ROLE_TOOLS[role]
    return (
        shop_mcp()
        .filtered(lambda ctx, td: td.name in allowed)
        .prepared(_prepare)
        .approval_required(lambda ctx, td, args: td.name in PAY_TOOLS)
    )
