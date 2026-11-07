"""Reset the working database to the original values (shop rule R7).

Run this before every full run that resolves the tickets (from hw5/backend/):
    python reset_db.py

It copies data/campus_customs.db (the untouched original) over
data/campus_customs_new.db (the copy the MCP server reads and writes).
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # hw5/
ORIGINAL = ROOT / "data" / "campus_customs.db"
WORKING = ROOT / "data" / "campus_customs_new.db"


def reset_db() -> Path:
    if not ORIGINAL.exists():
        raise FileNotFoundError(f"Original database not found at {ORIGINAL}")
    shutil.copyfile(ORIGINAL, WORKING)
    return WORKING


if __name__ == "__main__":
    print(f"Reset {reset_db().relative_to(ROOT)} from {ORIGINAL.relative_to(ROOT)}")
