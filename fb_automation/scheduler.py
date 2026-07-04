"""Scheduled reminder jobs — daily or recurring interval sends."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Callable, Any

from fb_automation.paths import data_path
from fb_automation.engine import AutomationEngine
from fb_automation.chatgen import generate_reminder_message
from fb_automation.templates import render_message

SCHEDULES_PATH = data_path("schedules.json")
TICK_SECONDS = 30

EventCallback = Callable[[dict], None]


def _default_store() -> dict:
    return {"jobs": []}


def load_schedules() -> dict:
    if SCHEDULES_PATH.exists():
        try:
            return json.loads(SCHEDULES_PATH.read_text())
        except (json.JSONDecodeError, TypeError):
            pass
    return _default_store()


def save_schedules(data: dict) -> None:
    SCHEDULES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def compute_next_run(job: dict, *, after: datetime | None = None) -> datetime:
    """Return the next run time for a job (local timezone)."""
    now = after or datetime.now()
    schedule_type = job.get("schedule_type", "daily")

    if schedule_type == "interval":
        hours = max(1, int(job.get("interval_hours", 1)))
        last = job.get("last_run")
        if last:
            base = datetime.fromisoformat(last)
            nxt = base + timedelta(hours=hours)
            return nxt if nxt > now else now
        return now + timedelta(hours=hours)

    hour = int(job.get("hour", 9))
    minute = int(job.get("minute", 0))
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def validate_job(job: dict) -> str | None:
    if not job.get("name", "").strip():
        return "Name is required"
    if job.get("schedule_type") not in ("daily", "interval"):
        return "schedule_type must be 'daily' or 'interval'"
    if job.get("schedule_type") == "interval":
        hours = job.get("interval_hours", 0)
        if not isinstance(hours, (int, float)) or hours < 1:
            return "interval_hours must be at least 1"
    platforms = job.get("platforms") or []
    if not platforms:
        return "Select at least one platform (facebook or instagram)"
    for p in platforms:
        if p not in ("facebook", "instagram"):
            return "platforms must be 'facebook' and/or 'instagram'"
    if not job.get("idea", "").strip():
        return "Message idea is required"
    idx = job.get("contact_index")
    if idx is None or not isinstance(idx, int) or idx < 0:
        return "contact_index is required"
    return None


def normalize_job(raw: dict, existing: dict | None = None) -> dict:
    base = existing or {}
    job = {
        "id": base.get("id") or str(uuid.uuid4()),
        "name": raw.get("name", base.get("name", "")).strip(),
        "enabled": bool(raw.get("enabled", base.get("enabled", True))),
        "schedule_type": raw.get("schedule_type", base.get("schedule_type", "daily")),
        "hour": int(raw.get("hour", base.get("hour", 9))),
        "minute": int(raw.get("minute", base.get("minute", 0))),
        "interval_hours": int(raw.get("interval_hours", base.get("interval_hours", 4))),
        "contact_index": int(raw.get("contact_index", base.get("contact_index", 0))),
        "platforms": list(raw.get("platforms", base.get("platforms", ["instagram"]))),
        "idea": raw.get("idea", base.get("idea", "")).strip(),
        "use_ai": bool(raw.get("use_ai", base.get("use_ai", True))),
        "profile_name": raw.get("profile_name", base.get("profile_name")) or None,
        "last_run": base.get("last_run"),
        "next_run": base.get("next_run"),
    }
    job["next_run"] = compute_next_run(job).isoformat(timespec="seconds")
    return job


class JobScheduler:
    def __init__(self, engine: AutomationEngine) -> None:
        self.engine = engine
        self._task: asyncio.Task | None = None
        self._callbacks: list[EventCallback] = []
        self._running_job_id: str | None = None

    def on_event(self, callback: EventCallback) -> None:
        self._callbacks.append(callback)

    def _emit(self, level: str, message: str, **extra: Any) -> None:
        payload = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "message": message,
            **extra,
        }
        for cb in self._callbacks:
            try:
                cb(payload)
            except Exception:
                pass

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def list_jobs(self) -> list[dict]:
        return load_schedules().get("jobs", [])

    def get_job(self, job_id: str) -> dict | None:
        for job in self.list_jobs():
            if job["id"] == job_id:
                return job
        return None

    def create_job(self, raw: dict) -> dict:
        job = normalize_job(raw)
        err = validate_job(job)
        if err:
            raise ValueError(err)
        data = load_schedules()
        data.setdefault("jobs", []).append(job)
        save_schedules(data)
        return job

    def update_job(self, job_id: str, raw: dict) -> dict:
        data = load_schedules()
        jobs = data.get("jobs", [])
        for i, existing in enumerate(jobs):
            if existing["id"] == job_id:
                job = normalize_job({**existing, **raw}, existing=existing)
                err = validate_job(job)
                if err:
                    raise ValueError(err)
                jobs[i] = job
                save_schedules(data)
                return job
        raise KeyError(f"Job '{job_id}' not found")

    def delete_job(self, job_id: str) -> None:
        data = load_schedules()
        jobs = [j for j in data.get("jobs", []) if j["id"] != job_id]
        if len(jobs) == len(data.get("jobs", [])):
            raise KeyError(f"Job '{job_id}' not found")
        data["jobs"] = jobs
        save_schedules(data)

    def toggle_job(self, job_id: str, enabled: bool) -> dict:
        return self.update_job(job_id, {"enabled": enabled})

    async def run_job_now(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found")
        return await self._execute_job(job, force=True)

    def _resolve_message(self, job: dict, contact: dict) -> str:
        idea = job["idea"]
        config = self.engine.load_config()
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or "them"
        if job.get("use_ai") and config.get("openai_api_key"):
            return generate_reminder_message(
                idea=idea,
                contact_name=name,
                api_key=config["openai_api_key"],
                model=config.get("openai_model", "gpt-5.4"),
                tone=config.get("chat_tone", "friendly and casual"),
            )
        return render_message(idea, contact)

    async def _execute_job(self, job: dict, *, force: bool = False) -> dict:
        if self._running_job_id and not force:
            self._emit("warn", f"Skipped '{job['name']}' — another scheduled job is running")
            return {"ok": False, "error": "busy"}

        if self.engine.is_busy():
            self._emit("warn", f"Skipped '{job['name']}' — browser automation is busy")
            return {"ok": False, "error": "engine_busy"}

        contacts = self.engine.load_contacts()
        idx = job["contact_index"]
        if idx >= len(contacts):
            self._emit("error", f"Job '{job['name']}' — contact index {idx} out of range")
            return {"ok": False, "error": "invalid_contact"}

        contact = contacts[idx]
        try:
            message = self._resolve_message(job, contact)
        except Exception as e:
            self._emit("error", f"Job '{job['name']}' — could not build message: {e}")
            return {"ok": False, "error": str(e)}

        self._running_job_id = job["id"]
        self._emit("info", f"[Schedule] Running '{job['name']}': \"{message[:60]}...\"" if len(message) > 60 else f"[Schedule] Running '{job['name']}': \"{message}\"")

        try:
            results = await self.engine.send_to_contact(
                contact,
                message,
                job["platforms"],
                profile_name=job.get("profile_name"),
                follow_ups=False,
            )
            now = datetime.now()
            job["last_run"] = now.isoformat(timespec="seconds")
            job["next_run"] = compute_next_run(job, after=now).isoformat(timespec="seconds")
            data = load_schedules()
            for i, j in enumerate(data.get("jobs", [])):
                if j["id"] == job["id"]:
                    data["jobs"][i] = job
                    break
            save_schedules(data)

            ok = any(results.values())
            if ok:
                self._emit("ok", f"[Schedule] '{job['name']}' sent successfully")
            else:
                self._emit("error", f"[Schedule] '{job['name']}' failed to send")
            return {"ok": ok, "results": results, "message": message}
        except Exception as e:
            self._emit("error", f"[Schedule] '{job['name']}' error: {e}")
            return {"ok": False, "error": str(e)}
        finally:
            self._running_job_id = None

    async def _loop(self) -> None:
        self._emit("info", "Schedule runner started")
        while True:
            try:
                await self._tick()
            except Exception as e:
                self._emit("error", f"Schedule tick error: {e}")
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self) -> None:
        now = datetime.now()
        for job in self.list_jobs():
            if not job.get("enabled"):
                continue
            nxt = job.get("next_run")
            if not nxt:
                job = self.update_job(job["id"], {})
                nxt = job["next_run"]
            if datetime.fromisoformat(nxt) <= now:
                await self._execute_job(job)
