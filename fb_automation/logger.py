from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from fb_automation.paths import data_path

PREVIEW_LIMIT = 80
_LOG_TAGS = re.compile(r"^\s*(?:\[(?:IG|FB|reply|follow-up \d+)\]\s*)+")
LOG_PATH = data_path("message_log.csv")
REPLIES_PATH = data_path("reply_log.csv")
_FIELDNAMES = ["timestamp", "first_name", "last_name", "profile_url", "status", "message_preview"]
_REPLY_FIELDNAMES = [
    "collected_at",
    "platform",
    "first_name",
    "last_name",
    "profile_url",
    "reply_text",
    "outbound_reply",
    "reply_status",
    "replied_at",
]


def _ensure_log_file() -> None:
    if not LOG_PATH.exists():
        with LOG_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            writer.writeheader()


def _ensure_replies_file() -> None:
    if not REPLIES_PATH.exists():
        with REPLIES_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_REPLY_FIELDNAMES)
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
                "message_preview": message_preview[:PREVIEW_LIMIT],
            }
        )


def normalize_message_text(text: str) -> str:
    """Drop log tags such as "[IG] [follow-up 2]" and fold case/whitespace."""
    return " ".join(_LOG_TAGS.sub("", text).lower().split())


def sent_message_matcher(sent_previews: list[str]) -> Callable[[str], bool]:
    """Return a predicate telling whether visible thread text is one of our sends.

    Logged previews are cut at PREVIEW_LIMIT characters, so a cut preview
    matches any longer text that starts with it.
    """
    previews = [
        (normalize_message_text(raw), len(raw) >= PREVIEW_LIMIT)
        for raw in sent_previews if raw
    ]

    def is_sent(text: str) -> bool:
        norm = normalize_message_text(text)
        return any(norm == sent or (cut and sent and norm.startswith(sent)) for sent, cut in previews)

    return is_sent


def load_message_log() -> list[dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


def load_replies() -> list[dict[str, str]]:
    if not REPLIES_PATH.exists():
        return []
    with REPLIES_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return [{field: row.get(field, "") for field in _REPLY_FIELDNAMES} for row in rows]


def log_reply(contact: dict[str, str], platform: str, profile_url: str, reply_text: str) -> bool:
    """Append a collected reply if it is not already in the reply log."""
    text = " ".join(reply_text.split())
    if not text:
        return False

    _ensure_replies_file()
    existing = load_replies()
    for row in existing:
        if (
            row.get("platform") == platform
            and row.get("profile_url") == profile_url
            and row.get("reply_text") == text
        ):
            return False

    with REPLIES_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_REPLY_FIELDNAMES)
        writer.writerow(
            {
                "collected_at": datetime.now().isoformat(timespec="seconds"),
                "platform": platform,
                "first_name": contact.get("first_name", ""),
                "last_name": contact.get("last_name", ""),
                "profile_url": profile_url,
                "reply_text": text,
                "outbound_reply": "",
                "reply_status": "",
                "replied_at": "",
            }
        )
    return True


def update_reply_status(index: int, outbound_reply: str, status: str) -> dict[str, str]:
    """Update a collected reply row after sending an answer."""
    replies = load_replies()
    if index < 0 or index >= len(replies):
        raise IndexError("Reply index out of range")

    replies[index]["outbound_reply"] = outbound_reply
    replies[index]["reply_status"] = status
    replies[index]["replied_at"] = datetime.now().isoformat(timespec="seconds")

    with REPLIES_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_REPLY_FIELDNAMES)
        writer.writeheader()
        writer.writerows(replies)
    return replies[index]
