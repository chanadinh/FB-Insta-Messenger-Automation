#!/usr/bin/env python3
"""FastAPI backend for the Facebook Messenger Automation dashboard."""

from __future__ import annotations

import asyncio
import csv
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fb_automation.engine import AutomationEngine, Status
from fb_automation.browser import (
    check_session_status, setup_login,
    load_profiles, save_profiles, get_active_profile,
)
from fb_automation.logger import LOG_PATH, REPLIES_PATH
from fb_automation.scheduler import JobScheduler

engine = AutomationEngine()
scheduler = JobScheduler(engine)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.on_event(_on_schedule_event)
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(title="FB Automation Dashboard", lifespan=lifespan)


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
    min_delay_seconds: int | None = None
    max_delay_seconds: int | None = None
    headless: bool | None = None
    dry_run: bool | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    follow_up_count: int | None = None
    follow_up_delay_min: int | None = None
    follow_up_delay_max: int | None = None
    chat_tone: str | None = None


class ProfileCreate(BaseModel):
    name: str


class ProfileSetActive(BaseModel):
    name: str


class StartRequest(BaseModel):
    contact_indices: list[int] | None = None


class ReplyCollectRequest(BaseModel):
    contact_indices: list[int] | None = None
    platforms: list[str] = Field(default_factory=lambda: ["facebook", "instagram"])
    profile_name: str | None = None


class ScheduleCreate(BaseModel):
    name: str
    enabled: bool = True
    schedule_type: str = "daily"  # daily | interval
    hour: int = Field(default=9, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    interval_hours: int = Field(default=4, ge=1, le=168)
    contact_index: int = Field(ge=0)
    platforms: list[str] = Field(default_factory=lambda: ["instagram"])
    idea: str
    use_ai: bool = True
    profile_name: str | None = None


class ScheduleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    schedule_type: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    contact_index: int | None = Field(default=None, ge=0)
    platforms: list[str] | None = None
    idea: str | None = None
    use_ai: bool | None = None
    profile_name: str | None = None


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
    session = await check_session_status(profile)
    return {**engine.get_state(), "session": session, "active_profile": profile}


@app.get("/api/config")
async def get_config():
    config = engine.load_config()
    if config.get("openai_api_key"):
        key = config["openai_api_key"]
        config["openai_api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    return config


@app.put("/api/config")
async def update_config(update: ConfigUpdate):
    config = engine.load_config()
    changes = update.model_dump(exclude_none=True)
    config.update(changes)
    engine.save_config(config)
    return {"ok": True, "config": config}


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
    if engine.state.status == Status.RUNNING:
        return {"ok": False, "error": "Stop the automation first"}
    if body.platform not in ("facebook", "instagram"):
        return {"ok": False, "error": "platform must be 'facebook' or 'instagram'"}
    _setup_running = True
    try:
        profile = get_active_profile()
        await setup_login(platform=body.platform, profile_name=profile)
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
    if not REPLIES_PATH.exists():
        return []
    with REPLIES_PATH.open(newline="") as f:
        return list(csv.DictReader(f))


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


# ── Scheduled reminders ───────────────────────────────────────

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

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
