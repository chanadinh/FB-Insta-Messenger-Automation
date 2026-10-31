#!/usr/bin/env python3
"""FastAPI backend for the Facebook Messenger Automation dashboard."""

from __future__ import annotations

import asyncio
import base64
import csv
import json
import os
import secrets
from contextlib import asynccontextmanager, suppress
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from fb_automation import access
from fb_automation.letters import router as letters_router
from fb_automation.mailbox import router as mailbox_router
from fb_automation.engine import AutomationEngine, Status
from fb_automation.browser import load_profiles, save_profiles, get_active_profile
from fb_automation.logger import LOG_PATH, REPLIES_PATH, load_replies, update_reply_status
from fb_automation.scheduler import JobScheduler, list_timezones, get_reminder_timezone_name
from fb_automation.paths import data_path
from fb_automation.gallery import image_metadata, thumbnail_path
from fb_automation.love_words import LoveWordsService

engine = AutomationEngine()
scheduler = JobScheduler(engine)
love_words = LoveWordsService(engine)

STATIC_DIR = Path(__file__).parent / "static"
GALLERY_DIR = data_path("gallery")
GALLERY_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_GALLERY_IMAGE_BYTES = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.on_event(_on_schedule_event)
    await scheduler.start()
    love_task = asyncio.create_task(love_words.run())
    try:
        yield
    finally:
        love_task.cancel()
        with suppress(asyncio.CancelledError):
            await love_task
        await scheduler.stop()


class DashboardAuth:
    """Guard every route except the token-protected mailbox and the link claim page.

    A browser gets in with a private access link (fb_automation.access, stored as
    a cookie) or, when DASHBOARD_PASSWORD is set, with HTTP Basic credentials.
    Both are resent automatically on fetch and WebSocket requests. The guard is
    on once a password or a link exists, or when REQUIRE_DASHBOARD_AUTH is set,
    so a published deployment with neither stays closed.
    """

    PUBLIC_PREFIXES = ("/mailbox", "/api/mailbox", "/access", "/api/access")
    DENIED_PAGE = (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Dashboard</title><p style='font-family:system-ui,sans-serif;text-align:center;margin-top:30vh;padding:0 16px'>"
        "Mở liên kết riêng của mình để vào nhé.<br>Open your private link to continue.</p>"
    ).encode()

    def __init__(self, app, username: str = "admin", password: str = "", required: bool = False) -> None:
        self.app = app
        self.expected = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode() if password else None
        self.required = required

    def _authorized(self, scope) -> bool:
        path = scope.get("path", "")
        if any(path == prefix or path.startswith(prefix + "/") for prefix in self.PUBLIC_PREFIXES):
            return True
        headers = dict(scope.get("headers") or [])
        cookies = SimpleCookie(headers.get(b"cookie", b"").decode("latin-1"))
        token = cookies[access.COOKIE_NAME].value if access.COOKIE_NAME in cookies else None
        if access.person_for(token):
            return True
        if self.expected:
            header = headers.get(b"authorization", b"").decode("latin-1")
            return secrets.compare_digest(header, self.expected)
        return not self.required and not access.links_exist()

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or self._authorized(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if self.expected:
            status, body = 401, b"Authentication required"
            headers = [
                (b"www-authenticate", b'Basic realm="dashboard", charset="UTF-8"'),
                (b"content-type", b"text/plain; charset=utf-8"),
            ]
        else:
            status, body = 403, self.DENIED_PAGE
            headers = [(b"content-type", b"text/html; charset=utf-8")]
        await send({"type": "http.response.start", "status": status, "headers": headers + [(b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})


app = FastAPI(title="FB Automation Dashboard", lifespan=lifespan)
app.add_middleware(
    DashboardAuth,
    username=os.environ.get("DASHBOARD_USER", "admin"),
    password=os.environ.get("DASHBOARD_PASSWORD", ""),
    required=os.environ.get("REQUIRE_DASHBOARD_AUTH", "").lower() in ("1", "true", "yes"),
)
app.include_router(access.router)
app.include_router(letters_router)
app.include_router(mailbox_router)
app.include_router(love_words.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "DASHBOARD_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket manager ─────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.remove(ws)

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


ws_manager = ConnectionManager()


def _on_log(entry: dict) -> None:
    """Push log entries and state to all connected WebSocket clients."""
    asyncio.ensure_future(ws_manager.broadcast({
        "type": "log",
        "entry": entry,
        "state": engine.get_state(),
    }))


engine.on_log(_on_log)


def _on_schedule_event(entry: dict) -> None:
    """Push scheduler log lines to WebSocket clients."""
    asyncio.ensure_future(ws_manager.broadcast({
        "type": "schedule_log",
        "entry": entry,
    }))


# ── Pydantic models ───────────────────────────────────────────

class ContactModel(BaseModel):
    first_name: str = ""
    last_name: str = ""
    fb_url: str = ""
    ig_url: str = ""
    custom_field: str = ""


class ConfigUpdate(BaseModel):
    message_template: str | None = None
    min_delay_seconds: int | None = Field(default=None, ge=0, le=86400)
    max_delay_seconds: int | None = Field(default=None, ge=0, le=86400)
    max_concurrent_contacts: int | None = Field(default=None, ge=1, le=10)
    headless: bool | None = None
    dry_run: bool | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    follow_up_count: int | None = Field(default=None, ge=0, le=20)
    follow_up_delay_min: int | None = Field(default=None, ge=0, le=86400)
    follow_up_delay_max: int | None = Field(default=None, ge=0, le=86400)
    chat_tone: str | None = None


class ProfileCreate(BaseModel):
    name: str


class ProfileSetActive(BaseModel):
    name: str


class StartRequest(BaseModel):
    contact_indices: list[int] | None = None


class AnniversarySendRequest(BaseModel):
    contact_index: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=2000)
    profile_name: str | None = None
    dry_run: bool | None = None


class ReplyCollectRequest(BaseModel):
    contact_indices: list[int] | None = None
    platforms: list[str] = Field(default_factory=lambda: ["facebook", "instagram"])
    profile_name: str | None = None


class ReplySendRequest(BaseModel):
    message: str
    profile_name: str | None = None


class ScheduleCreate(BaseModel):
    name: str
    enabled: bool = True
    schedule_type: str = "daily"  # daily | interval | once
    hour: int = Field(default=9, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    interval_hours: int = Field(default=4, ge=1, le=168)
    run_at: str | None = None
    contact_index: int = Field(ge=0)
    platforms: list[str] = Field(default_factory=lambda: ["instagram"])
    idea: str
    use_ai: bool = True
    profile_name: str | None = None
    timezone: str | None = None
    sleep_enabled: bool = False
    sleep_start_hour: int = Field(default=22, ge=0, le=23)
    sleep_end_hour: int = Field(default=7, ge=0, le=23)


class ScheduleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    schedule_type: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    run_at: str | None = None
    contact_index: int | None = Field(default=None, ge=0)
    platforms: list[str] | None = None
    idea: str | None = None
    use_ai: bool | None = None
    profile_name: str | None = None
    timezone: str | None = None
    sleep_enabled: bool | None = None
    sleep_start_hour: int | None = Field(default=None, ge=0, le=23)
    sleep_end_hour: int | None = Field(default=None, ge=0, le=23)


class ScheduleToggle(BaseModel):
    enabled: bool


# ── API routes ─────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse(STATIC_DIR / "service-worker.js", media_type="application/javascript")


@app.get("/api/status")
async def get_status():
    profile = get_active_profile()
    session = await engine.check_session(profile)
    return {**engine.get_state(), "session": session, "active_profile": profile}


def _masked_config(config: dict) -> dict:
    config = dict(config)
    if config.get("openai_api_key"):
        key = config["openai_api_key"]
        config["openai_api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    return config


@app.get("/api/config")
async def get_config():
    return _masked_config(engine.load_config())


@app.put("/api/config")
async def update_config(update: ConfigUpdate):
    config = engine.load_config()
    changes = update.model_dump(exclude_none=True)
    config.update(changes)
    if config["min_delay_seconds"] > config["max_delay_seconds"]:
        return {"ok": False, "error": "Minimum contact delay cannot exceed maximum delay"}
    if config["follow_up_delay_min"] > config["follow_up_delay_max"]:
        return {"ok": False, "error": "Minimum follow-up delay cannot exceed maximum delay"}
    engine.save_config(config)
    return {"ok": True, "config": _masked_config(config)}


@app.get("/api/contacts")
async def get_contacts():
    return engine.load_contacts()


@app.post("/api/contacts")
async def add_contact(contact: ContactModel):
    contacts = engine.load_contacts()
    contacts.append(contact.model_dump())
    engine.save_contacts(contacts)
    return {"ok": True, "total": len(contacts)}


@app.put("/api/contacts/{idx}")
async def update_contact(idx: int, contact: ContactModel):
    contacts = engine.load_contacts()
    if idx < 0 or idx >= len(contacts):
        return {"ok": False, "error": "Index out of range"}
    contacts[idx] = contact.model_dump()
    engine.save_contacts(contacts)
    return {"ok": True}


@app.delete("/api/contacts/{idx}")
async def delete_contact(idx: int):
    contacts = engine.load_contacts()
    if idx < 0 or idx >= len(contacts):
        return {"ok": False, "error": "Index out of range"}
    removed = contacts.pop(idx)
    engine.save_contacts(contacts)
    scheduler.contact_deleted(idx)
    return {"ok": True, "removed": removed}


@app.post("/api/start")
async def start_automation(body: StartRequest = StartRequest()):
    if engine.state.status == Status.RUNNING:
        return {"ok": False, "error": "Already running"}
    try:
        contacts = None
        if body.contact_indices is not None:
            all_contacts = engine.load_contacts()
            contacts = [all_contacts[i] for i in body.contact_indices if 0 <= i < len(all_contacts)]
            if not contacts:
                return {"ok": False, "error": "No valid contacts selected"}
        await engine.start(contacts=contacts)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/stop")
async def stop_automation():
    await engine.stop()
    return {"ok": True}


@app.post("/api/anniversary/send")
async def send_anniversary(body: AnniversarySendRequest):
    contacts = engine.load_contacts()
    if body.contact_index >= len(contacts):
        return {"ok": False, "error": "Contact index out of range"}
    if not contacts[body.contact_index].get("ig_url", "").strip():
        return {"ok": False, "error": "Selected contact does not have an Instagram URL"}
    try:
        results = await engine.send_to_contact(
            contacts[body.contact_index],
            body.message.strip(),
            ["instagram"],
            profile_name=body.profile_name,
            dry_run=body.dry_run,
        )
        return {"ok": bool(results.get("instagram")), "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/gallery")
async def list_gallery():
    images = []
    for path in sorted(GALLERY_DIR.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_TYPES.values():
            images.append(image_metadata(path))
    return images


@app.get("/api/gallery/thumbnail/{name}")
def gallery_thumbnail(name: str):
    source = (GALLERY_DIR / name).resolve()
    if source.parent != GALLERY_DIR.resolve() or not source.is_file() or source.suffix.lower() not in ALLOWED_IMAGE_TYPES.values():
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        preview = thumbnail_path(source)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(status_code=422, detail="Could not preview this photo") from error
    return FileResponse(preview, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/gallery")
async def upload_gallery_image(file: UploadFile = File(...)):
    extension = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not extension:
        return {"ok": False, "error": "Only JPG, PNG, WEBP, and GIF images are supported"}
    content = await file.read(MAX_GALLERY_IMAGE_BYTES + 1)
    if len(content) > MAX_GALLERY_IMAGE_BYTES:
        return {"ok": False, "error": "Images must be 10 MB or smaller"}
    safe_stem = Path(file.filename or "memory").stem[:80] or "memory"
    destination = GALLERY_DIR / f"{safe_stem}-{os.urandom(6).hex()}{extension}"
    destination.write_bytes(content)
    return {"ok": True, "image": image_metadata(destination)}


_setup_running = False


class SetupLoginRequest(BaseModel):
    platform: str = "facebook"


@app.post("/api/setup-login")
async def do_setup_login(body: SetupLoginRequest = SetupLoginRequest()):
    """Open a visible browser for one-time manual login.

    Accepts {"platform": "facebook"} or {"platform": "instagram"}.
    The persistent profile saves everything (cookies, localStorage, IndexedDB)
    so subsequent automation runs skip the password step entirely.
    """
    global _setup_running
    if _setup_running:
        return {"ok": False, "error": "Setup login is already in progress"}
    if engine.is_busy():
        return {"ok": False, "error": "Stop the automation first"}
    if body.platform not in ("facebook", "instagram"):
        return {"ok": False, "error": "platform must be 'facebook' or 'instagram'"}
    _setup_running = True
    try:
        profile = get_active_profile()
        await engine.setup_login(body.platform, profile)
        label = "Facebook" if body.platform == "facebook" else "Instagram"
        return {"ok": True, "message": f"{label} login saved for profile '{profile}'!"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        _setup_running = False


# ── Profiles ───────────────────────────────────────────────────

@app.get("/api/profiles")
async def get_profiles():
    return load_profiles()


@app.post("/api/profiles")
async def create_profile(body: ProfileCreate):
    data = load_profiles()
    name = body.name.strip()
    if not name:
        return {"ok": False, "error": "Profile name is required"}
    if name in data["profiles"]:
        return {"ok": False, "error": f"Profile '{name}' already exists"}
    data["profiles"].append(name)
    save_profiles(data)
    return {"ok": True, "profiles": data["profiles"]}


@app.put("/api/profiles/active")
async def set_active_profile(body: ProfileSetActive):
    data = load_profiles()
    name = body.name.strip()
    if name not in data["profiles"]:
        return {"ok": False, "error": f"Profile '{name}' not found"}
    data["active"] = name
    save_profiles(data)
    return {"ok": True, "active": name}


@app.delete("/api/profiles/{name}")
async def delete_profile(name: str):
    data = load_profiles()
    if name not in data["profiles"]:
        return {"ok": False, "error": f"Profile '{name}' not found"}
    if len(data["profiles"]) <= 1:
        return {"ok": False, "error": "Cannot delete the last profile"}
    data["profiles"].remove(name)
    if data["active"] == name:
        data["active"] = data["profiles"][0]
    save_profiles(data)
    return {"ok": True, "profiles": data["profiles"], "active": data["active"]}


@app.get("/api/logs")
async def get_logs():
    return engine.state.logs


@app.get("/api/message-log")
async def get_message_log():
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


@app.get("/api/replies")
async def get_replies():
    return load_replies()


@app.post("/api/replies/collect")
async def collect_replies(body: ReplyCollectRequest = ReplyCollectRequest()):
    if engine.is_busy():
        return {"ok": False, "error": "Browser automation is busy"}
    try:
        contacts = None
        if body.contact_indices is not None:
            all_contacts = engine.load_contacts()
            contacts = [all_contacts[i] for i in body.contact_indices if 0 <= i < len(all_contacts)]
            if not contacts:
                return {"ok": False, "error": "No valid contacts selected"}
        platforms = [p for p in body.platforms if p in ("facebook", "instagram")]
        if not platforms:
            return {"ok": False, "error": "Select at least one platform"}
        return await engine.collect_replies(contacts, platforms, profile_name=body.profile_name)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/replies/{idx}/send")
async def send_reply(idx: int, body: ReplySendRequest):
    if engine.is_busy():
        return {"ok": False, "error": "Browser automation is busy"}
    replies = load_replies()
    if idx < 0 or idx >= len(replies):
        return {"ok": False, "error": "Reply index out of range"}
    message = body.message.strip()
    if not message:
        return {"ok": False, "error": "Reply message is required"}
    try:
        result = await engine.send_reply_to_thread(replies[idx], message, profile_name=body.profile_name)
        status = "sent" if result.get("ok") else "failed"
        row = update_reply_status(idx, message, status)
        return {**result, "reply": row}
    except Exception as e:
        try:
            row = update_reply_status(idx, message, "failed")
        except Exception:
            row = replies[idx]
        return {"ok": False, "error": str(e), "reply": row}


# ── Scheduled reminders ───────────────────────────────────────

@app.get("/api/timezones")
async def get_timezones():
    current = get_reminder_timezone_name()
    zones = list_timezones()
    if current not in zones:
        zones = [current, *zones]
    return {"current": current, "timezones": zones}


@app.get("/api/schedules")
async def list_schedules():
    return scheduler.list_jobs()


@app.post("/api/schedules")
async def create_schedule(body: ScheduleCreate):
    try:
        job = scheduler.create_job(body.model_dump())
        return {"ok": True, "job": job}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.put("/api/schedules/{job_id}")
async def update_schedule(job_id: str, body: ScheduleUpdate):
    try:
        job = scheduler.update_job(job_id, body.model_dump(exclude_none=True))
        return {"ok": True, "job": job}
    except KeyError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.delete("/api/schedules/{job_id}")
async def delete_schedule(job_id: str):
    try:
        scheduler.delete_job(job_id)
        return {"ok": True}
    except KeyError as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/schedules/{job_id}/toggle")
async def toggle_schedule(job_id: str, body: ScheduleToggle):
    try:
        job = scheduler.toggle_job(job_id, body.enabled)
        return {"ok": True, "job": job}
    except KeyError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/schedules/{job_id}/run")
async def run_schedule_now(job_id: str):
    try:
        result = await scheduler.run_job_now(job_id)
        return {"ok": result.get("ok", False), **result}
    except KeyError as e:
        return {"ok": False, "error": str(e)}


# ── WebSocket ──────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        await ws.send_json({"type": "init", "state": engine.get_state(), "logs": engine.state.logs})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Static files (must be last) ────────────────────────────────

app.mount("/mailbox", StaticFiles(directory=str(Path(__file__).parent / "dashboard" / "dist"), html=True, check_dir=False), name="mailbox")
app.mount("/anniversary", StaticFiles(directory=str(Path(__file__).parent / "dashboard" / "dist"), html=True, check_dir=False), name="anniversary")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/gallery", StaticFiles(directory=str(GALLERY_DIR)), name="gallery")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
