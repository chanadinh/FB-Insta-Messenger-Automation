"""Resolved data directory for config, contacts, profiles, logs, and browser data."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("APP_DATA_DIR", ".")).resolve()

if os.environ.get("APP_DATA_DIR"):
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def data_path(*parts: str) -> Path:
    return DATA_DIR.joinpath(*parts)
