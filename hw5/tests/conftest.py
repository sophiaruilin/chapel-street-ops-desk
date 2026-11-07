"""Shared test setup: every test works on a temp copy of the ORIGINAL database and a temp
audit trail, so the real data/ and output/ files are never touched. No model calls."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

HW5 = Path(__file__).resolve().parent.parent
ORIGINAL_DB = HW5 / "data" / "campus_customs.db"

# Point everything at temp files BEFORE any backend module is imported.
_TMP = Path(tempfile.mkdtemp(prefix="hw5-tests-"))
os.environ["CAMPUS_DB_PATH"] = str(_TMP / "working.db")
os.environ["CAMPUS_AUDIT_PATH"] = str(_TMP / "audit_trail.json")
os.environ.setdefault("PORTKEY_API_KEY", "test-key-not-used")
shutil.copyfile(ORIGINAL_DB, _TMP / "working.db")
sys.path.insert(0, str(HW5 / "backend"))


def _load_server():
    spec = importlib.util.spec_from_file_location("campus_server", HW5 / "mcp_server" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """A fresh copy of the original database for one test."""
    path = tmp_path / "working.db"
    shutil.copyfile(ORIGINAL_DB, path)
    return path


@pytest.fixture()
def server(db: Path):
    """The MCP server module, pointed at this test's database."""
    mod = _load_server()
    mod.DB_PATH = db
    mod.SECOND_APPROVER_ABOVE = 5000.0
    return mod


@pytest.fixture()
def shared_db() -> Path:
    """The temp database the backend/MCP subprocess use (reset to the original for each test)."""
    path = Path(os.environ["CAMPUS_DB_PATH"])
    shutil.copyfile(ORIGINAL_DB, path)
    return path
