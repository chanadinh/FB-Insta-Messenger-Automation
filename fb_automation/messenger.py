from __future__ import annotations

import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page

from fb_automation.paths import data_path

MESSENGER_URL = "https://www.facebook.com/messages/t/"
EmitFn = Callable[[str, str], None] | None


def _emit(emit: EmitFn, level: str, message: str) -> None:
    line = message if message.startswith("[FB]") else f"[FB] {message}"
    print(line)
    if emit:
        emit(level, line)


async def _save_debug(page: Page, label: str) -> Path | None:
    try:
        debug_dir = data_path("debug")
        debug_dir.mkdir(exist_ok=True)
        path = debug_dir / f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=str(path), full_page=True)
        return path
    except Exception:
        return None


async def _human_type(page: Page, selector: str, text: str) -> None:
    """Type text character-by-character with random delays to mimic human input."""
    element = await page.wait_for_selector(selector, timeout=15000)
    await element.click()
    for char in text:
        await page.keyboard.type(char, delay=random.randint(30, 120))
        if random.random() < 0.05:
            await page.wait_for_timeout(random.randint(200, 600))


async def _extract_user_id(profile_url: str, page: Page) -> str | None:
    """Try to resolve a profile URL to a numeric user ID for Messenger routing."""
    url = profile_url.strip().rstrip("/")
    parsed = urlparse(url)

    if "facebook.com" in parsed.netloc and parsed.path.startswith("/messages/t/"):
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 3:
            return parts[2]

    # If already numeric (e.g. https://facebook.com/profile.php?id=12345)
    if "profile.php" in parsed.path:
        user_id = parse_qs(parsed.query).get("id", [""])[0]
        if user_id:
            return user_id

    # Extract the vanity username from the URL
    username = parsed.path.rstrip("/").split("/")[-1] if parsed.netloc else url.split("/")[-1]
    if username:
        return username.split("?")[0]

    return None


def _messenger_url(profile_url: str, user_id: str) -> str:
    url = profile_url.strip()
    parsed = urlparse(url)
    if "facebook.com" in parsed.netloc and parsed.path.startswith("/messages/t/"):
        return url
    return f"{MESSENGER_URL}{user_id}"


async def _fb_needs_login(page: Page) -> bool:
    url = page.url.lower()
    if any(x in url for x in ("/login", "/checkpoint", "/recover")):
        return True
    for sel in (
        'form[action*="login"]',
        'input[name="email"]',
        'input[name="pass"]',
        'button[name="login"]',
    ):
        try:
            if await page.query_selector(sel):
                return True
        except Exception:
            pass
    return False


async def _dismiss_fb_dialogs(page: Page) -> None:
    selectors = [
        'div[role="button"]:has-text("Not Now")',
        'button:has-text("Not Now")',
        'div[role="button"]:has-text("Không phải bây giờ")',
        'button:has-text("Không phải bây giờ")',
        'div[aria-label="Close"]',
        'div[aria-label="Đóng"]',
        'button:has-text("Allow all cookies")',
        'button:has-text("Accept all")',
    ]
    for sel in selectors:
        try:
            btn = await page.wait_for_selector(sel, timeout=1200)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(600)
        except Exception:
            pass


async def _find_message_input(page: Page, timeout: int = 10000):
    input_selectors = [
        'div[aria-label="Message"][role="textbox"]',
        'div[aria-label*="Message"][role="textbox"]',
        'div[aria-label="Aa"][role="textbox"]',
        'div[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[contenteditable="true"][aria-label]',
        'p[contenteditable="true"]',
        'p.xat24cr.xdj266r',
    ]

    for selector in input_selectors:
        try:
            input_box = await page.wait_for_selector(selector, timeout=timeout)
            if input_box and await input_box.is_visible():
                return input_box
        except Exception:
            continue
    return None


async def _type_and_send_current_thread(page: Page, message: str, emit: EmitFn = None) -> bool:
    await _dismiss_fb_dialogs(page)
    input_box = await _find_message_input(page)

    if not input_box:
        _emit(emit, "error", f"Could not find Messenger input box (url={page.url}).")
        shot = await _save_debug(page, "fb_no_input")
        if shot:
            _emit(emit, "info", f"Debug screenshot saved: {shot}")
        return False

    try:
        await input_box.click()
        await page.wait_for_timeout(random.randint(500, 1000))
        await page.keyboard.insert_text(message)
        await page.wait_for_timeout(random.randint(800, 1500))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1500)

        for sel in (
            'div[aria-label="Press Enter to send"]',
            'div[aria-label="Send"]',
            'div[aria-label*="Send"]',
            'div[role="button"]:has-text("Send")',
            'button:has-text("Send")',
            'div[aria-label="Gửi"]',
        ):
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    break
            except Exception:
                continue

        await page.wait_for_timeout(random.randint(2000, 3000))
        _emit(emit, "ok", "Message sent.")
        return True
    except Exception as e:
        _emit(emit, "error", f"Failed to type/send message: {e}")
        await _save_debug(page, "fb_send_failed")
        return False


async def send_message(page: Page, profile_url: str, message: str, emit: EmitFn = None) -> bool:
    """Navigate to a Messenger conversation and send a message.

    Returns True if the message was sent successfully.
    """
    user_id = await _extract_user_id(profile_url, page)
    if not user_id:
        _emit(emit, "error", f"Could not extract user ID from: {profile_url}")
        return False

    messenger_url = _messenger_url(profile_url, user_id)
    _emit(emit, "info", f"Opening conversation: {messenger_url}")

    try:
        await page.goto(messenger_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(random.randint(3000, 5000))
    except Exception as e:
        _emit(emit, "error", f"Failed to navigate to conversation: {e}")
        return False

    if await _fb_needs_login(page):
        _emit(emit, "error", "Not logged in on Facebook or Facebook showed a checkpoint.")
        await _save_debug(page, "fb_login_required")
        return False

    return await _type_and_send_current_thread(page, message, emit)


async def send_follow_up(page: Page, message: str, emit: EmitFn = None) -> bool:
    """Send a follow-up message in the currently open conversation."""
    return await _type_and_send_current_thread(page, message, emit)


async def delay_between_messages(min_sec: int, max_sec: int) -> None:
    """Sleep for a random duration between min_sec and max_sec."""
    wait = random.uniform(min_sec, max_sec)
    print(f"  [WAIT] Sleeping {wait:.0f}s before next message...")
    await asyncio.sleep(wait)


async def collect_fb_replies(
    page: Page,
    profile_url: str,
    sent_messages: list[str] | None = None,
    emit: EmitFn = None,
) -> list[str]:
    """Open a Messenger conversation and return recent visible reply candidates."""
    user_id = await _extract_user_id(profile_url, page)
    if not user_id:
        _emit(emit, "error", f"Could not extract user ID from: {profile_url}")
        return []

    messenger_url = _messenger_url(profile_url, user_id)
    _emit(emit, "info", f"Collecting replies from: {messenger_url}")

    try:
        await page.goto(messenger_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2500, 4000))
    except Exception as e:
        _emit(emit, "error", f"Failed to navigate to conversation: {e}")
        return []

    if await _fb_needs_login(page):
        _emit(emit, "error", "Not logged in on Facebook or Facebook showed a checkpoint.")
        await _save_debug(page, "fb_login_required")
        return []

    sent_norm = {_normalize_message_text(msg) for msg in sent_messages or [] if msg}
    ignored = {
        "",
        "message",
        "send",
        "sent",
        "search",
        "more",
        "active now",
        "view profile",
        "messenger",
    }
    texts = await page.evaluate(
        """() => Array.from(document.querySelectorAll('[role="main"] div[dir="auto"], [role="main"] span[dir="auto"], div[aria-label*="Messages"] div[dir="auto"], div[aria-label*="Messages"] span[dir="auto"]'))
          .filter((el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
          })
          .map((el) => el.innerText || el.textContent || '')"""
    )

    replies: list[str] = []
    seen: set[str] = set()
    for raw in texts[-80:]:
        text = " ".join(str(raw).split())
        norm = _normalize_message_text(text)
        if len(text) < 2 or len(text) > 1000:
            continue
        if norm in ignored or norm in sent_norm:
            continue
        if any(norm and norm in sent for sent in sent_norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        replies.append(text)
    return replies[-20:]


def _normalize_message_text(text: str) -> str:
    cleaned = text
    for prefix in ("[IG]", "[FB]"):
        cleaned = cleaned.replace(prefix, "")
    if "] " in cleaned and "[follow-up" in cleaned:
        cleaned = cleaned.split("] ", 1)[1]
    return " ".join(cleaned.lower().split())
