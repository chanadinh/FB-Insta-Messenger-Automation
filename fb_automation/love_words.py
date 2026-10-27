"""Local, bilingual keepsakes from one explicitly configured Instagram chat."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

SYNC_INTERVAL = 300


class LoveWordsError(RuntimeError):
    pass


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def normalize_thread(url: str) -> str:
    parsed = urlsplit(url.strip())
    match = re.fullmatch(r"/direct/t/(\d{1,50})/?", parsed.path)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() not in ("instagram.com", "www.instagram.com") or not match:
        raise LoveWordsError("thread_required")
    return f"https://www.instagram.com/direct/t/{match[1]}/"


ENGLISH = re.compile(
    r"\b(?:i\s+love\s+(?:you|u)|love\s+(?:you|u)|luv\s+(?:you|u)|ily|ilysm|loveu|luvu|missu|"
    r"(?:i\s+)?miss\s+(?:you|u)|my\s+(?:love|darling|sweetheart)|"
    r"i\s+adore\s+(?:you|u)|(?:you|u)\s+mean\s+(?:the\s+world|everything)\s+to\s+me|"
    r"(?:you|u)\s+make\s+me\s+happy|(?:you\s+are|u\s+r)\s+my\s+(?:world|everything|love)|"
    r"can[’']?t\s+wait\s+to\s+(?:see|hold|kiss)\s+(?:you|u))\b"
)
VIETNAMESE = re.compile(
    r"\b(?:(?:anh|em|minh|to|tui)\s+(?:rat\s+)?(?:yeu|i+u+|thuong|nho)\s+(?:anh|em|ban|cau|be|vk|ck|u)|"
    r"(?:yeu|i+u+|thuong|nho)\s+(?:anh|em|cau|be|vo|chong|vk|ck|u)(?:\s+nhieu)?|"
    r"(?:vo|chong|be|tinh)\s+(?:yeu|i+u+)|minh\s+yeu\s+nhau|vk|ck|i+u+)\b"
)
NEGATION = re.compile(r"\b(?:don[’']?t|do\s+not|never|not|khong|khum|hong|hok|ko|k|chua|chang|het|dung)\b")


def detect_love(text: str) -> str | None:
    normalized = normalize_text(text)
    found = []
    for language, pattern in (("en", ENGLISH), ("vi", VIETNAMESE)):
        for match in pattern.finditer(normalized):
            # Negation within this clause or match prevents "I don't love you"
            # and "anh không yêu em" from becoming keepsakes.
            clause = re.split(r"[.!?,;\n]", normalized[:match.start()])[-1]
            context = " ".join(clause.split()[-4:]) + " " + match.group()
            if not NEGATION.search(context):
                found.append(language)
                break
    return "mixed" if len(found) == 2 else found[0] if found else None


@contextmanager
def database():
    path = Path(os.environ.get("APP_DATA_DIR", ".")) / "love_words.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS love_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                thread_url TEXT NOT NULL DEFAULT '',
                profile_name TEXT NOT NULL DEFAULT '',
                auto_sync INTEGER NOT NULL DEFAULT 0,
                last_checked TEXT,
                last_error TEXT
            );
            INSERT OR IGNORE INTO love_settings (id) VALUES (1);
            CREATE TABLE IF NOT EXISTS love_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_url TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                body TEXT NOT NULL,
                language TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                hidden INTEGER NOT NULL DEFAULT 0
            );
        """)
        yield db
        db.commit()
    finally:
        db.close()


def snapshot() -> dict:
    with database() as db:
        settings = dict(db.execute("SELECT * FROM love_settings WHERE id = 1").fetchone())
        settings.pop("id")
        settings["auto_sync"] = bool(settings["auto_sync"])
        settings["interval_seconds"] = SYNC_INTERVAL
        notes = db.execute(
            "SELECT id, body, language, saved_at FROM love_words "
            "WHERE thread_url = ? AND profile_name = ? AND hidden = 0 ORDER BY id DESC LIMIT 200",
            (settings["thread_url"], settings["profile_name"]),
        ).fetchall()
    return {"settings": settings, "notes": [dict(note) for note in notes]}


def save_matches(settings: dict, texts: list[str]) -> int:
    added = 0
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        for raw in texts:
            body = unicodedata.normalize("NFC", raw).strip()
            if not 2 <= len(body) <= 2000:
                continue
            language = detect_love(body)
            if not language:
                continue
            # Preserve distinct accents; fold case/whitespace for repeated scans.
            normalized = " ".join(body.casefold().split())
            identity = f"{settings['profile_name']}\n{settings['thread_url']}\n{normalized}"
            fingerprint = hashlib.sha256(identity.encode()).hexdigest()
            result = db.execute(
                "INSERT OR IGNORE INTO love_words (thread_url, profile_name, fingerprint, body, language, saved_at) VALUES (?, ?, ?, ?, ?, ?)",
                (settings["thread_url"], settings["profile_name"], fingerprint, body, language, now),
            )
            added += result.rowcount
    return added


class LoveSettings(BaseModel):
    thread_url: str = Field(max_length=500)
    auto_sync: bool = False


class LoveWordsService:
    def __init__(self, engine):
        self.engine = engine
        self.lock = asyncio.Lock()
        self.wake = asyncio.Event()
        self.router = APIRouter(prefix="/api/love-words", tags=["love words"])
        self.router.add_api_route("", self.get, methods=["GET"])
        self.router.add_api_route("/settings", self.configure, methods=["PUT"])
        self.router.add_api_route("/sync", self.sync_endpoint, methods=["POST"])
        self.router.add_api_route("/{note_id}", self.hide, methods=["DELETE"])

    def get(self, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {**snapshot(), "syncing": self.lock.locked()}

    async def configure(self, body: LoveSettings):
        from fb_automation.browser import get_active_profile

        try:
            thread = normalize_thread(body.thread_url)
        except (LoveWordsError, ValueError) as error:
            raise HTTPException(422, detail={"code": "thread_required"}) from error
        if self.lock.locked():
            raise HTTPException(409, detail={"code": "busy"})
        profile = get_active_profile()
        with database() as db:
            db.execute(
                "UPDATE love_settings SET last_checked = CASE WHEN thread_url = ? AND profile_name = ? THEN last_checked END, "
                "thread_url = ?, profile_name = ?, auto_sync = ?, last_error = NULL WHERE id = 1",
                (thread, profile, thread, profile, int(body.auto_sync)),
            )
        self.wake.set()
        return snapshot()

    async def sync(self):
        from fb_automation.browser import CookieAuthError

        if self.lock.locked() or self.engine.is_busy():
            raise LoveWordsError("busy")
        async with self.lock:
            settings = snapshot()["settings"]
            if not settings["thread_url"]:
                raise LoveWordsError("thread_required")
            try:
                texts = await self.engine.collect_love_words(settings["thread_url"], profile_name=settings["profile_name"])
                added = save_matches(settings, texts)
                with database() as db:
                    db.execute("UPDATE love_settings SET last_checked = ?, last_error = NULL WHERE id = 1", (datetime.now(timezone.utc).isoformat(),))
                return {"ok": True, "added": added, "scanned": len(texts), **snapshot()}
            except Exception as error:
                code = "login_required" if isinstance(error, CookieAuthError) else str(error) if isinstance(error, LoveWordsError) else "sync_failed"
                with database() as db:
                    db.execute("UPDATE love_settings SET last_error = ? WHERE id = 1", (code,))
                raise LoveWordsError(code) from error

    async def sync_endpoint(self):
        try:
            return await self.sync()
        except LoveWordsError as error:
            code = str(error)
            raise HTTPException(409 if code == "busy" else 422 if code == "thread_required" else 502, detail={"code": code}) from error

    def hide(self, note_id: int):
        settings = snapshot()["settings"]
        with database() as db:
            result = db.execute(
                "UPDATE love_words SET hidden = 1 WHERE id = ? AND thread_url = ? AND profile_name = ? AND hidden = 0",
                (note_id, settings["thread_url"], settings["profile_name"]),
            )
            if not result.rowcount:
                raise HTTPException(404, detail={"code": "not_found"})
        return {"ok": True}

    async def run(self):
        while True:
            self.wake.clear()
            settings = snapshot()["settings"]
            if settings["auto_sync"] and settings["thread_url"]:
                try:
                    await self.sync()
                except LoveWordsError:
                    pass  # The last error is available in the dashboard.
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=SYNC_INTERVAL)
            except asyncio.TimeoutError:
                pass
