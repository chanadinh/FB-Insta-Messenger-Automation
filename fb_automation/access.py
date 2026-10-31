"""Private dashboard links for two people. Run this module to create or revoke them.

Opening a link once stores a cookie in that browser; nobody signs in to anything.
Anyone without a link (or the dashboard password) is turned away.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

MAX_PEOPLE = 2
COOKIE_NAME = "dashboard_access"
COOKIE_MAX_AGE = 365 * 24 * 3600

router = APIRouter(tags=["access"])


@contextmanager
def database():
    path = Path(os.environ.get("APP_DATA_DIR", ".")) / "dashboard_access.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with private permissions before SQLite opens it.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("CREATE TABLE IF NOT EXISTS people (name TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE)")
        yield db
        db.commit()
    finally:
        db.close()


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def person_for(token: str | None) -> str | None:
    if not token:
        return None
    with database() as db:
        row = db.execute("SELECT name FROM people WHERE token_hash = ?", (digest(token),)).fetchone()
    return row["name"] if row else None


def links_exist() -> bool:
    with database() as db:
        return bool(db.execute("SELECT COUNT(*) FROM people").fetchone()[0])


def create_links(base_url: str, names: list[str], rotate: bool = False) -> dict[str, str]:
    names = [name.strip() for name in names if name.strip()]
    if not names or len(names) > MAX_PEOPLE or len(set(names)) != len(names):
        raise ValueError(f"Give 1 to {MAX_PEOPLE} different names.")
    tokens = {name: secrets.token_urlsafe(32) for name in names}
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM people").fetchone()[0] and not rotate:
            raise ValueError("Links already exist. Use --rotate to replace them; old links stop working.")
        db.execute("DELETE FROM people")
        for name, token in tokens.items():
            db.execute("INSERT INTO people (name, token_hash) VALUES (?, ?)", (name, digest(token)))
    return {name: f"{base_url.rstrip('/')}/access#key={token}" for name, token in tokens.items()}


def revoke(name: str) -> bool:
    with database() as db:
        return bool(db.execute("DELETE FROM people WHERE name = ?", (name,)).rowcount)


class Claim(BaseModel):
    key: str = Field(min_length=1, max_length=200)


CLAIM_PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Dashboard</title>
<style>body{font-family:system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;
background:#fdf6f4;color:#3b2a2a}p{max-width:22rem;text-align:center;padding:0 16px}</style></head>
<body><p id="msg">Đang mở…</p><script>
const key = new URLSearchParams(location.hash.slice(1)).get('key');
history.replaceState(null, '', location.pathname);
const msg = document.getElementById('msg');
if (!key) msg.textContent = 'Mở đúng liên kết riêng của mình để vào nhé.';
else fetch('/api/access/claim', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({key}), credentials: 'same-origin'})
  .then(r => r.ok ? location.replace('/anniversary/') : (msg.textContent = 'Liên kết này không còn dùng được.'))
  .catch(() => { msg.textContent = 'Không kết nối được, thử lại sau nhé.'; });
</script></body></html>"""


@router.get("/access", include_in_schema=False)
def claim_page():
    return HTMLResponse(CLAIM_PAGE, headers={"Cache-Control": "no-store"})


@router.post("/api/access/claim")
def claim(body: Claim, request: Request, response: Response):
    name = person_for(body.key)
    if not name:
        raise HTTPException(403, "Invalid or revoked link")
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        COOKIE_NAME, body.key, max_age=COOKIE_MAX_AGE,
        httponly=True, secure=https, samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "name": name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--names", nargs="+", default=["Anh", "Em"], help=f"Up to {MAX_PEOPLE} people")
    parser.add_argument("--rotate", action="store_true", help="Replace existing links")
    parser.add_argument("--revoke", metavar="NAME", help="Remove one person's link")
    args = parser.parse_args()
    if args.revoke:
        if not revoke(args.revoke):
            parser.exit(1, f"No link for '{args.revoke}'.\n")
        print(f"Revoked the link for '{args.revoke}'.")
        raise SystemExit
    try:
        links = create_links(args.base_url, args.names, args.rotate)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    print("Send each person their own link. They are displayed only once:")
    for name, link in links.items():
        print(f"{name}: {link}")
