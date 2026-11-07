"""Shared settings for the Campus Customs agent team: paths, model, and limits."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

HERE = Path(__file__).resolve().parent          # hw5/backend
ROOT = HERE.parent                              # hw5
PROMPTS_DIR = HERE / "prompts"
MCP_SERVER_SCRIPT = ROOT / "mcp_server" / "server.py"
MCP_SERVER_PYTHON = Path(sys.executable)  # same venv as the backend (one hw5/.venv)

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
load_dotenv(ROOT / ".env")         # hw5/.env (copy .env.example and add your key)
load_dotenv(ROOT.parent / ".env")  # fallback: a .env one folder up

# Tests point these at temp files so they never touch the real trail or database.
AUDIT_PATH = Path(os.getenv("CAMPUS_AUDIT_PATH") or ROOT / "output" / "audit_trail.json")
DB_PATH = Path(os.getenv("CAMPUS_DB_PATH") or ROOT / "data" / "campus_customs_new.db")

# ---- Who may sign (dashboard approvals) ------------------------------------
# A signature needs the desk PIN from .env; without one set, the desk refuses every approval.
APPROVAL_PIN = os.getenv("DESK_APPROVAL_PIN", "").strip()
# Optional allow-list of approver names (comma separated). Empty = any human name.
APPROVERS = [n.strip() for n in os.getenv("DESK_APPROVERS", "").split(",") if n.strip()]

# Model: one model for every agent (school policy: gpt-6-astra through the class Portkey key).
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-6-astra").strip() or "gpt-6-astra"
REASONING_EFFORT = "medium"
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1").rstrip("/")

# ---- Limits that keep loops and token use in check ------------------------
# Sized from the Problem 9 runs (27-37 requests, 74k-110k tokens per ticket), then cut so the
# hub-and-spoke design has to stay lean.
MAX_DEPTH = 2                 # Boss = 0, its teammates = 1, their teammates = 2 (no deeper)
MAX_DELEGATIONS = 6           # ask_teammate calls allowed in one team run (one ticket)
SPECIALIST_DELEGATIONS = 1    # each specialist run may ask at most one teammate (hub-and-spoke)
TEAM_REQUEST_LIMIT = 30       # model requests across all agents in one team run
TEAM_TOTAL_TOKENS_LIMIT = 150_000  # tokens across all agents in one team run
MAX_APPROVAL_ROUNDS = 3       # pause-for-human rounds per agent run
AUDIT_TEXT_CHARS = 1500       # long texts/tool results are trimmed in the audit trail


def mcp_env() -> dict[str, str]:
    """Environment for the MCP server subprocess: same as ours, pinned to our database path."""
    return {**os.environ, "CAMPUS_DB_PATH": str(DB_PATH)}


def build_model() -> tuple[OpenAIResponsesModel, OpenAIResponsesModelSettings]:
    """The single model + settings every agent uses (Portkey, Responses API, medium reasoning)."""
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Copy .env.example to .env and add your key.")
    client = AsyncOpenAI(
        api_key="unused",  # Portkey authenticates with the header below
        base_url=PORTKEY_BASE_URL,
        default_headers={
            "x-portkey-api-key": api_key,
            "x-portkey-provider": "openai",
            # The class key caches identical requests; a replay could quote stale cash/stock.
            "x-portkey-cache-force-refresh": "true",
        },
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    settings = OpenAIResponsesModelSettings(openai_reasoning_effort=REASONING_EFFORT)
    return model, settings
