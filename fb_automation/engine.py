"""Controllable automation engine — wraps the send loop so the server can start/stop it."""

from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

from fb_automation.browser import launch_browser, close_browser, CookieAuthError, get_active_profile
from fb_automation.messenger import send_message, send_follow_up, delay_between_messages
from fb_automation.instagram import send_ig_message, send_ig_follow_up
from fb_automation.templates import render_message
from fb_automation.chatgen import generate_follow_ups
from fb_automation.logger import log_message
from fb_automation.paths import data_path

CONFIG_PATH = data_path("config.json")
CONTACTS_PATH = data_path("contacts.csv")
CONTACTS_FIELDS = ["first_name", "last_name", "fb_url", "ig_url", "custom_field"]

DEFAULT_CONFIG = {
    "message_template": "Hey {{first_name}}, just wanted to reach out!",
    "min_delay_seconds": 30,
    "max_delay_seconds": 90,
    "headless": True,
    "dry_run": False,
    "openai_api_key": "",
    "openai_model": "gpt-5.4",
    "follow_up_count": 3,
    "follow_up_delay_min": 5,
    "follow_up_delay_max": 15,
    "chat_tone": "friendly and casual",
}


class Status(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class EngineState:
    status: Status = Status.IDLE
    current_contact: str = ""
    progress: int = 0
    total: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    error: str = ""
    logs: list[dict] = field(default_factory=list)


LogCallback = Callable[[dict], None]


class AutomationEngine:
    def __init__(self) -> None:
        self.state = EngineState()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._log_callbacks: list[LogCallback] = []
        self._busy_lock = asyncio.Lock()

    def is_busy(self) -> bool:
        return self._busy_lock.locked()

    def on_log(self, callback: LogCallback) -> None:
        self._log_callbacks.append(callback)

    def _emit(self, level: str, message: str) -> None:
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "message": message,
        }
        self.state.logs.append(entry)
        if len(self.state.logs) > 500:
            self.state.logs = self.state.logs[-500:]
        for cb in self._log_callbacks:
            try:
                cb(entry)
            except Exception:
                pass

    # ── Config / Contacts helpers ──────────────────────────────

    @staticmethod
    def load_config() -> dict:
        config = dict(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open() as f:
                config.update(json.load(f))
        return config

    @staticmethod
    def save_config(config: dict) -> None:
        with CONFIG_PATH.open("w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_contacts() -> list[dict[str, str]]:
        if not CONTACTS_PATH.exists():
            return []
        with CONTACTS_PATH.open(newline="") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def save_contacts(contacts: list[dict[str, str]]) -> None:
        if not contacts:
            CONTACTS_PATH.write_text(",".join(CONTACTS_FIELDS) + "\n")
            return
        fieldnames = CONTACTS_FIELDS
        with CONTACTS_PATH.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(contacts)

    # ── Control ────────────────────────────────────────────────

    async def start(self, contacts: list[dict[str, str]] | None = None) -> None:
        if self.is_busy():
            raise RuntimeError("Automation is already running")

        self._stop_event.clear()
        self.state = EngineState(status=Status.RUNNING)

        if contacts is None:
            contacts = self.load_contacts()
        if not contacts:
            self.state.status = Status.ERROR
            self.state.error = "No contacts loaded"
            self._emit("error", "No contacts to process")
            return

        self._task = asyncio.create_task(self._run(contacts))

    async def _run(self, contacts: list[dict[str, str]]) -> None:
        await self._busy_lock.acquire()
        try:
            await self._run_locked(contacts)
        finally:
            self._busy_lock.release()

    async def stop(self) -> None:
        if self.state.status != Status.RUNNING:
            return
        self.state.status = Status.STOPPING
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=30)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def send_to_contact(
        self,
        contact: dict[str, str],
        message: str,
        platforms: list[str],
        *,
        profile_name: str | None = None,
        headless: bool | None = None,
        dry_run: bool | None = None,
        follow_ups: bool = False,
    ) -> dict[str, bool]:
        """Send a one-off message on selected platforms. Returns {platform: success}."""
        if self.is_busy():
            raise RuntimeError("Browser automation is busy")

        config = self.load_config()
        if headless is None:
            headless = config.get("headless", True)
        if dry_run is None:
            dry_run = config.get("dry_run", False)

        fb_url = contact.get("fb_url", "").strip()
        ig_url = contact.get("ig_url", "").strip()
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        profile = profile_name or get_active_profile()

        want_fb = "facebook" in platforms and bool(fb_url)
        want_ig = "instagram" in platforms and bool(ig_url)
        if not want_fb and not want_ig:
            self._emit("warn", f"No URLs for selected platforms ({name})")
            return {}

        api_key = config.get("openai_api_key", "")
        openai_model = config.get("openai_model", "gpt-5.4")
        follow_up_count = config.get("follow_up_count", 3) if follow_ups else 0
        fu_delay_min = config.get("follow_up_delay_min", 5)
        fu_delay_max = config.get("follow_up_delay_max", 15)
        chat_tone = config.get("chat_tone", "friendly and casual")

        results: dict[str, bool] = {}

        async with self._busy_lock:
            self._stop_event.clear()
            prev_status = self.state.status
            self.state.status = Status.RUNNING
            context = None
            try:
                if dry_run:
                    if want_fb:
                        self._emit("info", f"[DRY RUN] [FB] Would send to {name}: \"{message}\"")
                        log_message({**contact, "profile_url": fb_url}, "dry_run", message)
                        results["facebook"] = True
                    if want_ig:
                        self._emit("info", f"[DRY RUN] [IG] Would send to {name}: \"{message}\"")
                        log_message({**contact, "profile_url": ig_url}, "dry_run", message)
                        results["instagram"] = True
                    return results

                self._emit("info", f"Sending reminder to {name}...")
                context, _ = await launch_browser(
                    headless=headless,
                    need_fb=want_fb,
                    need_ig=want_ig,
                    profile_name=profile,
                )

                tasks = []
                platforms_order: list[str] = []
                if want_fb:
                    platforms_order.append("facebook")
                    tasks.append(self._send_on_platform(
                        context, contact, name, fb_url, message,
                        "facebook", api_key, openai_model,
                        follow_up_count, fu_delay_min, fu_delay_max, chat_tone,
                    ))
                if want_ig:
                    platforms_order.append("instagram")
                    tasks.append(self._send_on_platform(
                        context, contact, name, ig_url, message,
                        "instagram", api_key, openai_model,
                        follow_up_count, fu_delay_min, fu_delay_max, chat_tone,
                    ))
                outcomes = await asyncio.gather(*tasks)
                for platform, ok in zip(platforms_order, outcomes):
                    results[platform] = ok
            finally:
                if context:
                    await close_browser(context)
                self.state.status = prev_status if prev_status != Status.RUNNING else Status.IDLE

        return results

    def get_state(self) -> dict:
        return {
            "status": self.state.status.value,
            "current_contact": self.state.current_contact,
            "progress": self.state.progress,
            "total": self.state.total,
            "sent": self.state.sent,
            "failed": self.state.failed,
            "skipped": self.state.skipped,
            "error": self.state.error,
        }

    # ── Main loop (parallel) ─────────────────────────────────────

    async def _run_locked(self, contacts: list[dict[str, str]]) -> None:
        config = self.load_config()
        template = config["message_template"]
        dry_run = config["dry_run"]
        headless = config.get("headless", True)
        api_key = config.get("openai_api_key", "")
        openai_model = config.get("openai_model", "gpt-5.4")
        follow_up_count = config.get("follow_up_count", 3)
        fu_delay_min = config.get("follow_up_delay_min", 5)
        fu_delay_max = config.get("follow_up_delay_max", 15)
        chat_tone = config.get("chat_tone", "friendly and casual")

        self.state.total = len(contacts)
        self._emit("info", f"Starting parallel automation for {self.state.total} contacts")
        self._emit("info", "Mode: 2 tabs per contact (Facebook + Instagram)")

        context = None
        try:
            if not dry_run:
                profile = get_active_profile()
                self._emit("info", f"Launching browser with profile '{profile}'...")
                context, _initial_page = await launch_browser(
                    headless=headless, need_fb=True, need_ig=True,
                    profile_name=profile,
                )
                self._emit("info", f"Browser ready [{profile}] — opening tabs per contact")
            else:
                context = None

            tasks = []
            for i, contact in enumerate(contacts, 1):
                tasks.append(self._process_contact(
                    i, contact, context, template, dry_run,
                    api_key, openai_model, follow_up_count,
                    fu_delay_min, fu_delay_max, chat_tone,
                ))

            await asyncio.gather(*tasks)

        except CookieAuthError as e:
            self.state.error = str(e)
            self._emit("error", f"Auth failed: {e}")
        except Exception as e:
            self.state.error = str(e)
            self._emit("error", f"Unexpected error: {e}")
        finally:
            if context:
                await close_browser(context)
            if self.state.status != Status.ERROR:
                self.state.status = Status.IDLE
            self.state.current_contact = ""
            self._emit("info",
                f"Finished — {self.state.sent} sent, "
                f"{self.state.skipped} skipped, {self.state.failed} failed"
            )

    async def _process_contact(
        self,
        index: int,
        contact: dict[str, str],
        context,
        template: str,
        dry_run: bool,
        api_key: str,
        openai_model: str,
        follow_up_count: int,
        fu_delay_min: int,
        fu_delay_max: int,
        chat_tone: str,
    ) -> None:
        """Open a tab for each platform that has a URL, run simultaneously."""
        if self._stop_event.is_set():
            return

        fb_url = contact.get("fb_url", "").strip()
        ig_url = contact.get("ig_url", "").strip()
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()

        self._emit("info", f"[{index}/{self.state.total}] Processing: {name}")

        if not fb_url and not ig_url:
            self._emit("warn", f"Skipped {name} — no URLs")
            log_message(contact, "skipped", "no fb_url or ig_url")
            self.state.skipped += 1
            self.state.progress += 1
            return

        message = render_message(template, contact)

        if dry_run:
            platforms = []
            if fb_url:
                platforms.append("FB")
            if ig_url:
                platforms.append("IG")
            self._emit("info", f"[DRY RUN] [{'+'.join(platforms)}] Would send to {name}: \"{message}\"")
            log_message(contact, "dry_run", message)
            self.state.sent += 1
            self.state.progress += 1
            return

        tasks = []
        if fb_url:
            tasks.append(self._send_on_platform(
                context, contact, name, fb_url, message,
                "facebook", api_key, openai_model,
                follow_up_count, fu_delay_min, fu_delay_max, chat_tone,
            ))
        if ig_url:
            tasks.append(self._send_on_platform(
                context, contact, name, ig_url, message,
                "instagram", api_key, openai_model,
                follow_up_count, fu_delay_min, fu_delay_max, chat_tone,
            ))

        await asyncio.gather(*tasks)
        self.state.progress += 1

    async def _send_on_platform(
        self,
        context,
        contact: dict[str, str],
        name: str,
        profile_url: str,
        message: str,
        platform: str,
        api_key: str,
        openai_model: str,
        follow_up_count: int,
        fu_delay_min: int,
        fu_delay_max: int,
        chat_tone: str,
    ) -> bool:
        """Send message + follow-ups on a single platform in its own tab."""
        tag = "IG" if platform == "instagram" else "FB"
        page = await context.new_page()
        success = False

        try:
            self._emit("info", f"[{tag}] Sending to {name}...")

            emit = lambda level, msg: self._emit(level, msg)

            if platform == "instagram":
                success = await send_ig_message(page, profile_url, message, emit=emit)
            else:
                success = await send_message(page, profile_url, message)

            if success:
                log_message(contact, "sent", f"[{tag}] {message}")
                self.state.sent += 1
                self._emit("ok", f"[{tag}] Message sent to {name}")

                if api_key and follow_up_count > 0:
                    self._emit("info", f"[{tag}] Generating {follow_up_count} follow-ups for {name}...")
                    try:
                        follow_ups = generate_follow_ups(
                            message, name, api_key,
                            model=openai_model,
                            num_messages=follow_up_count,
                            tone=chat_tone,
                        )
                    except Exception as e:
                        self._emit("error", f"[{tag}] AI follow-up failed for {name}: {e}")
                        follow_ups = []

                    for j, fu in enumerate(follow_ups, 1):
                        if self._stop_event.is_set():
                            break
                        await delay_between_messages(fu_delay_min, fu_delay_max)
                        self._emit("info", f"[{tag}] Follow-up {j}/{len(follow_ups)} to {name}")
                        if platform == "instagram":
                            fu_ok = await send_ig_follow_up(page, fu, emit=emit)
                        else:
                            fu_ok = await send_follow_up(page, fu)
                        status = "sent" if fu_ok else "failed"
                        log_message(contact, status, f"[{tag}] [follow-up {j}] {fu}")
            else:
                log_message(contact, "failed", f"[{tag}] {message}")
                self.state.failed += 1
                self._emit("error", f"[{tag}] Failed to send to {name}")

        except Exception as e:
            self.state.failed += 1
            self._emit("error", f"[{tag}] Error with {name}: {e}")
        finally:
            await page.close()
        return success
