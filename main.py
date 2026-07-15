"""Backward-compatible local launcher.

Prefer `uvicorn app.main:app --app-dir src` for deployment.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from app.main import app

__all__ = ["app"]
