"""Letters between the two people who hold private dashboard links.

Each person's private link (fb_automation.access) says who they are, so a
letter always goes to the other person and nobody chooses a recipient. A
letter with a delivery time stays hidden from its recipient until then; no
browser automation or background job is involved.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from fb_automation import access

MAX_SCHEDULE_AHEAD = timedelta(days=3 * 366)

router = APIRouter(prefix="/api/letters", tags=["letters"])


@contextmanager
def database():
    path = Path(os.environ.get("APP_DATA_DIR", ".")) / "letters.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with private permissions before SQLite opens it.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                deliver_at TEXT NOT NULL,
                read_at TEXT
            );
            CREATE INDEX IF NOT EXISTS letters_recipient ON letters (recipient, deliver_at);
        """)
        yield db
        db.commit()
    finally:
        db.close()


def stamp(moment: datetime) -> str:
    """UTC timestamps in one fixed format, so they also sort and compare as text."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def now() -> datetime:
    return datetime.now(timezone.utc)


def identity(request: Request, response: Response) -> dict[str, str]:
    """The person behind this browser's private link, and their partner."""
    response.headers["Cache-Control"] = "no-store"
    me = access.person_for(request.cookies.get(access.COOKIE_NAME))
    if not me:
        raise HTTPException(401, detail={"code": "link_required"})
    partner = next((name for name in access.people() if name != me), None)
    return {"me": me, "partner": partner}


class Letter(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    deliver_at: datetime | None = None


def _row(row: sqlite3.Row) -> dict:
    return dict(row)


@router.get("")
def letters(who: dict = Depends(identity)):
    current = stamp(now())
    with database() as db:
        inbox = db.execute(
            "SELECT * FROM letters WHERE recipient = ? AND deliver_at <= ? ORDER BY deliver_at DESC, id DESC LIMIT 200",
            (who["me"], current),
        ).fetchall()
        sent = db.execute(
            "SELECT * FROM letters WHERE sender = ? ORDER BY deliver_at DESC, id DESC LIMIT 200",
            (who["me"],),
        ).fetchall()
    return {
        **who,
        "now": current,
        "inbox": [_row(row) for row in inbox],
        "sent": [_row(row) for row in sent],
        "unread": sum(1 for row in inbox if not row["read_at"]),
    }


@router.post("", status_code=201)
def send(letter: Letter, who: dict = Depends(identity)):
    body = letter.body.strip()
    if not body:
        raise HTTPException(422, detail={"code": "empty"})
    if not who["partner"]:
        raise HTTPException(409, detail={"code": "no_partner"})
    current = now()
    deliver = current
    if letter.deliver_at is not None:
        requested = letter.deliver_at if letter.deliver_at.tzinfo else letter.deliver_at.replace(tzinfo=timezone.utc)
        if requested - current > MAX_SCHEDULE_AHEAD:
            raise HTTPException(422, detail={"code": "too_far"})
        deliver = max(requested, current)
    with database() as db:
        cursor = db.execute(
            "INSERT INTO letters (sender, recipient, body, created_at, deliver_at) VALUES (?, ?, ?, ?, ?)",
            (who["me"], who["partner"], body, stamp(current), stamp(deliver)),
        )
        row = db.execute("SELECT * FROM letters WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row(row)


@router.post("/{letter_id}/read")
def mark_read(letter_id: int, who: dict = Depends(identity)):
    with database() as db:
        cursor = db.execute(
            "UPDATE letters SET read_at = COALESCE(read_at, ?) WHERE id = ? AND recipient = ? AND deliver_at <= ?",
            (stamp(now()), letter_id, who["me"], stamp(now())),
        )
        if not cursor.rowcount:
            raise HTTPException(404, detail={"code": "not_found"})
    return {"ok": True}


@router.delete("/{letter_id}")
def cancel(letter_id: int, who: dict = Depends(identity)):
    """Take back one of my letters that has not been delivered yet."""
    with database() as db:
        cursor = db.execute(
            "DELETE FROM letters WHERE id = ? AND sender = ? AND deliver_at > ?",
            (letter_id, who["me"], stamp(now())),
        )
        if not cursor.rowcount:
            raise HTTPException(404, detail={"code": "not_found"})
    return {"ok": True}
