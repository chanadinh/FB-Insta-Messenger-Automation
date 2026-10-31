"""Private two-person mailbox. Run this module locally to create invitation links."""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/mailbox", tags=["mailbox"])
bearer = HTTPBearer(auto_error=False)


@contextmanager
def database():
    path = Path(os.environ.get("APP_DATA_DIR", ".")) / "mailbox.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with private permissions before SQLite opens it.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS people (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                read_at TEXT
            );
        """)
        yield db
        db.commit()
    finally:
        db.close()


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def identity(response: Response, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    response.headers["Cache-Control"] = "no-store"
    if credentials:
        with database() as db:
            person = db.execute("SELECT id, name FROM people WHERE token_hash = ?", (digest(credentials.credentials),)).fetchone()
        if person:
            return dict(person)
    raise HTTPException(401, "Mở liên kết hộp thư riêng của mình để tiếp tục nhé.", headers={"Cache-Control": "no-store"})


class Note(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.get("")
def inbox(person=Depends(identity)):
    with database() as db:
        partner = db.execute("SELECT id, name FROM people WHERE id != ?", (person["id"],)).fetchone()
        messages = db.execute(
            "SELECT * FROM messages WHERE recipient = ? OR sender = ? ORDER BY id DESC LIMIT 200",
            (person["id"], person["id"]),
        ).fetchall()
    return {"person": person, "partner": dict(partner) if partner else None, "messages": [dict(row) for row in messages]}


@router.post("/messages", status_code=201)
def send_note(note: Note, person=Depends(identity)):
    body = note.body.strip()
    if not body:
        raise HTTPException(422, "Viết vài lời nhắn trước nhé.")
    with database() as db:
        partner = db.execute("SELECT id FROM people WHERE id != ?", (person["id"],)).fetchone()
        if not partner:
            raise HTTPException(409, "Hộp thư của đôi mình chưa được thiết lập.")
        cursor = db.execute("INSERT INTO messages (sender, recipient, body) VALUES (?, ?, ?)", (person["id"], partner["id"], body))
        return {"id": cursor.lastrowid}


@router.post("/messages/{message_id}/read")
def read_note(message_id: int, person=Depends(identity)):
    with database() as db:
        cursor = db.execute(
            "UPDATE messages SET read_at = COALESCE(read_at, strftime('%Y-%m-%dT%H:%M:%fZ','now')) WHERE id = ? AND recipient = ?",
            (message_id, person["id"]),
        )
        if not cursor.rowcount:
            raise HTTPException(404, "Không tìm thấy lá thư này.")
    return {"ok": True}


def create_links(base_url: str, your_name: str, her_name: str, rotate: bool = False):
    tokens = {"you": secrets.token_urlsafe(32), "girlfriend": secrets.token_urlsafe(32)}
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM people").fetchone()[0] and not rotate:
            raise ValueError("Links already exist. Use --rotate to replace both links; old links will stop working. Notes are kept.")
        for person_id, name in (("you", your_name), ("girlfriend", her_name)):
            db.execute("INSERT OR REPLACE INTO people (id, name, token_hash) VALUES (?, ?, ?)", (person_id, name, digest(tokens[person_id])))
    return {person: f"{base_url.rstrip('/')}/mailbox/#key={token}" for person, token in tokens.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--your-name", default="Anh")
    parser.add_argument("--her-name", default="Em")
    parser.add_argument("--rotate", action="store_true")
    args = parser.parse_args()
    try:
        links = create_links(args.base_url, args.your_name, args.her_name, args.rotate)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print("Keep these private links. They are displayed only once:")
    for person, link in links.items():
        print(f"{person}: {link}")
