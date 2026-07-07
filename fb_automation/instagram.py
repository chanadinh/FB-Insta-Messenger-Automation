"""Instagram DM automation — send messages via Instagram web."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.async_api import Page

from fb_automation.paths import data_path

INSTAGRAM_URL = "https://www.instagram.com"
NEW_DM_URL = f"{INSTAGRAM_URL}/direct/new/"

EmitFn = Callable[[str, str], None] | None


def _emit(emit: EmitFn, level: str, message: str) -> None:
    line = message if message.startswith("[IG]") else f"[IG] {message}"
    print(line)
    if emit:
        emit(level, line)


def _is_direct_thread_url(url: str) -> bool:
    return "instagram.com/direct/t/" in url


def _extract_username(profile_url: str) -> str | None:
    url = profile_url.strip().rstrip("/")

    if "instagram.com" in url:
        parts = url.split("instagram.com/")
        if len(parts) > 1:
            username = parts[1].split("/")[0].split("?")[0]
            if username and username not in ("direct", "accounts", "explore", "p"):
                return username
        return None

    if not url.startswith("http") and "/" not in url:
        return url

    return None


async def _save_debug(page: Page, label: str) -> Path | None:
    try:
        debug_dir = data_path("debug")
        debug_dir.mkdir(exist_ok=True)
        path = debug_dir / f"{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await page.screenshot(path=str(path), full_page=True)
        return path
    except Exception:
        return None


async def _ig_needs_login(page: Page) -> bool:
    url = page.url.lower()
    if any(x in url for x in ("/accounts/login", "/challenge", "/consent")):
        return True
    for sel in (
        'form[id="loginForm"]',
        'input[name="username"]',
        'button:has-text("Log in")',
        'button:has-text("Log In")',
    ):
        try:
            if await page.query_selector(sel):
                return True
        except Exception:
            pass
    return False


async def _wait_for_inbox(page: Page, emit: EmitFn) -> bool:
    """Wait for Instagram DM UI to hydrate (especially in headless)."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    await page.wait_for_timeout(random.randint(2500, 4000))

    if await _ig_needs_login(page):
        _emit(emit, "error", "Not logged in — Instagram showed the login page. "
              "Log in on your Mac (Setup), then copy browser_profile_main/ to the server again.")
        await _save_debug(page, "ig_login_required")
        return False

    # Thread or compose UI
    for sel in (
        'div[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="Message"]',
        'textarea[placeholder*="Nhắn tin"]',
        'div[aria-label*="Message"]',
        'div[aria-label*="Nhắn tin"]',
        '[data-pagelet="IGDInboxThread"]',
    ):
        try:
            await page.wait_for_selector(sel, timeout=12000)
            return True
        except Exception:
            continue

    _emit(emit, "warn", f"Inbox UI slow or missing (url={page.url}). Will retry finding input…")
    return True


async def _dismiss_ig_dialogs(page: Page) -> None:
    dismiss_selectors = [
        'button:has-text("Not Now")',
        'button:has-text("Không phải bây giờ")',
        '[role="dialog"] button:has-text("Not Now")',
        'button:has-text("Lúc khác")',
        'button:has-text("Turn on")',
    ]
    for sel in dismiss_selectors:
        try:
            btn = await page.wait_for_selector(sel, timeout=1500)
            if btn:
                await btn.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass


async def send_ig_message(
    page: Page,
    profile_url: str,
    message: str,
    emit: EmitFn = None,
) -> bool:
    url = profile_url.strip()

    if _is_direct_thread_url(url):
        _emit(emit, "info", f"Opening inbox: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            _emit(emit, "error", f"Failed to open inbox: {e}")
            return False
        if not await _wait_for_inbox(page, emit):
            return False
        await _dismiss_ig_dialogs(page)
        return await _type_and_send(page, message, emit)

    username = _extract_username(url)
    if not username:
        _emit(emit, "error", f"Could not extract username from: {url}")
        return False

    _emit(emit, "info", f"Searching for @{username} via compose screen")
    try:
        await page.goto(NEW_DM_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(random.randint(2000, 3000))
    except Exception as e:
        _emit(emit, "error", f"Failed to open DM compose: {e}")
        return False

    if await _ig_needs_login(page):
        _emit(emit, "error", "Not logged in on Instagram.")
        await _save_debug(page, "ig_login_required")
        return False

    await _dismiss_ig_dialogs(page)

    search_box = None
    for sel in (
        'input[placeholder="Search..."]',
        'input[placeholder="Tìm kiếm..."]',
        'input[name="queryBox"]',
        'input[type="text"][autocomplete]',
    ):
        try:
            search_box = await page.wait_for_selector(sel, timeout=8000)
            if search_box:
                break
        except Exception:
            continue

    if not search_box:
        _emit(emit, "error", "Could not find the 'To' search input.")
        await _save_debug(page, "ig_no_search")
        return False

    try:
        await search_box.click()
        await page.wait_for_timeout(500)
        await search_box.fill(username)
        await page.wait_for_timeout(random.randint(2000, 3000))
    except Exception as e:
        _emit(emit, "error", f"Failed to search for user: {e}")
        return False

    user_result = None
    for sel in (
        f'span:has-text("{username}")',
        '[role="listbox"] [role="option"]',
        'div[role="dialog"] div[role="button"]',
        f'button:has-text("{username}")',
    ):
        try:
            user_result = await page.wait_for_selector(sel, timeout=8000)
            if user_result:
                break
        except Exception:
            continue

    if not user_result:
        _emit(emit, "error", f"User @{username} not found in search results.")
        await _save_debug(page, "ig_user_not_found")
        return False

    try:
        await user_result.click()
        await page.wait_for_timeout(random.randint(1000, 2000))
    except Exception as e:
        _emit(emit, "error", f"Failed to select user: {e}")
        return False

    chat_btn = None
    for sel in (
        'div[role="button"]:has-text("Chat")',
        'button:has-text("Chat")',
        'div[role="button"]:has-text("Next")',
        'button:has-text("Next")',
        'div[role="button"]:has-text("Nhắn tin")',
        'button:has-text("Nhắn tin")',
        'div[role="button"]:has-text("Tiếp")',
        'button:has-text("Tiếp")',
    ):
        try:
            chat_btn = await page.wait_for_selector(sel, timeout=8000)
            if chat_btn:
                break
        except Exception:
            continue

    if not chat_btn:
        _emit(emit, "error", "Could not find Chat/Next button.")
        await _save_debug(page, "ig_no_chat_btn")
        return False

    try:
        await chat_btn.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
    except Exception as e:
        _emit(emit, "error", f"Failed to click Chat/Next: {e}")
        return False

    await _dismiss_ig_dialogs(page)
    return await _type_and_send(page, message, emit)


async def _type_and_send(page: Page, message: str, emit: EmitFn = None) -> bool:
    input_box = None
    input_selectors = [
        'div[role="textbox"][contenteditable="true"]',
        'div[aria-label="Message"][role="textbox"]',
        'div[aria-label*="Message"][contenteditable="true"]',
        'div[aria-label*="Nhắn tin"][contenteditable="true"]',
        'textarea[placeholder*="Message"]',
        'textarea[placeholder*="message"]',
        'textarea[placeholder*="Nhắn tin"]',
        'textarea[aria-label="Message"]',
        'p[contenteditable="true"]',
    ]
    for sel in input_selectors:
        try:
            input_box = await page.wait_for_selector(sel, timeout=15000)
            if input_box:
                break
        except Exception:
            continue

    if not input_box:
        _emit(emit, "error", f"Could not find message input (url={page.url}). "
              "Session may be expired or Instagram UI changed.")
        shot = await _save_debug(page, "ig_no_input")
        if shot:
            _emit(emit, "info", f"Debug screenshot saved: {shot}")
        return False

    try:
        await input_box.click()
        await page.wait_for_timeout(random.randint(400, 800))

        tag = await input_box.evaluate("el => el.tagName.toLowerCase()")
        if tag == "textarea":
            await input_box.fill(message)
        else:
            # contenteditable — insert_text works better than per-char typing in headless
            await page.keyboard.insert_text(message)

        await page.wait_for_timeout(random.randint(800, 1500))

        sent = False
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1500)

        # Some IG builds ignore Enter in headless — click Send
        for sel in (
            'div[role="button"]:has-text("Send")',
            'button:has-text("Send")',
            'div[role="button"]:has-text("Gửi")',
            'button:has-text("Gửi")',
        ):
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    sent = True
                    break
            except Exception:
                continue

        if not sent:
            sent = True  # Enter was pressed; assume sent if no explicit Send button

        await page.wait_for_timeout(random.randint(2000, 3000))
        _emit(emit, "ok", "Message sent.")
        return True

    except Exception as e:
        _emit(emit, "error", f"Failed to type/send message: {e}")
        await _save_debug(page, "ig_send_failed")
        return False


async def send_ig_follow_up(page: Page, message: str, emit: EmitFn = None) -> bool:
    return await _type_and_send(page, message, emit)


async def collect_ig_replies(
    page: Page,
    profile_url: str,
    sent_messages: list[str] | None = None,
    emit: EmitFn = None,
) -> list[str]:
    """Open an Instagram DM thread and return recent visible reply candidates."""
    url = profile_url.strip()
    if not _is_direct_thread_url(url):
        _emit(emit, "warn", "Reply collection needs an Instagram direct thread URL.")
        return []

    _emit(emit, "info", f"Collecting replies from: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        _emit(emit, "error", f"Failed to open inbox for reply collection: {e}")
        return []

    if not await _wait_for_inbox(page, emit):
        return []
    await _dismiss_ig_dialogs(page)
    await page.wait_for_timeout(random.randint(1500, 2500))

    return await _collect_visible_thread_text(page, sent_messages or [])


async def _collect_visible_thread_text(page: Page, sent_messages: list[str]) -> list[str]:
    sent_norm = {_normalize_message_text(msg) for msg in sent_messages if msg}
    ignored = {
        "",
        "message",
        "send",
        "sent",
        "reels",
        "search",
        "more",
        "active now",
        "view profile",
    }
    texts = await page.evaluate(
        """() => Array.from(document.querySelectorAll('main div[dir="auto"], main span[dir="auto"], [role="main"] div[dir="auto"], [role="main"] span[dir="auto"]'))
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
