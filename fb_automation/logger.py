from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("message_log.csv")
_FIELDNAMES = ["timestamp", "first_name", "last_name", "profile_url", "status", "message_preview"]


def _ensure_log_file() -> None:
    if not LOG_PATH.exists():
        with LOG_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            writer.writeheader()


def already_sent(profile_url: str) -> bool:
    """Check whether a message was already successfully sent to this profile."""
    if not LOG_PATH.exists():
        return False
    with LOG_PATH.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["profile_url"] == profile_url and row["status"] == "sent":
                return True
    return False


def log_message(
    contact: dict[str, str],
    status: str,
    message_preview: str = "",
) -> None:
    """Append a send attempt to the message log CSV."""
    _ensure_log_file()
    with LOG_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "first_name": contact.get("first_name", ""),
                "last_name": contact.get("last_name", ""),
                "profile_url": contact.get("profile_url", ""),
                "status": status,
                "message_preview": message_preview[:80],
            }
        )
