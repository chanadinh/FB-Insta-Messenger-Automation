"""Instagram DM automation — send messages via Instagram web."""

from __future__ import annotations

import asyncio
import random
from playwright.async_api import Page

INSTAGRAM_URL = "https://www.instagram.com"
NEW_DM_URL = f"{INSTAGRAM_URL}/direct/new/"


def _is_direct_thread_url(url: str) -> bool:
    """Check if the URL is an Instagram direct thread URL like /direct/t/ID/."""
    return "instagram.com/direct/t/" in url


def _extract_username(profile_url: str) -> str | None:
    """Extract the Instagram username from a profile URL or bare username."""
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


async def _dismiss_ig_dialogs(page: Page) -> None:
    """Dismiss common Instagram popups (notifications, etc.)."""
    dismiss_selectors = [
        'button:has-text("Not Now")',
        'button:has-text("Không phải bây giờ")',
        '[role="dialog"] button:has-text("Not Now")',
        'button:has-text("Lúc khác")',
    ]
    for sel in dismiss_selectors:
        try:
            btn = await page.wait_for_selector(sel, timeout=2000)
            if btn:
                await btn.click()
                await page.wait_for_timeout(800)
        except Exception:
            pass


async def send_ig_message(page: Page, profile_url: str, message: str) -> bool:
    """Send an Instagram DM.

    Accepts two URL formats:
      - Direct thread:  https://www.instagram.com/direct/t/104247194311070/
      - Profile / username:  https://www.instagram.com/username  (falls back to search)
    """
    url = profile_url.strip()

    # ── Fast path: direct thread URL → navigate straight to inbox ──
    if _is_direct_thread_url(url):
        print(f"  [IG NAV] Opening inbox: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 3000))
        except Exception as e:
            print(f"  [IG ERROR] Failed to open inbox: {e}")
            return False
        await _dismiss_ig_dialogs(page)
        return await _type_and_send(page, message)

    # ── Fallback: search by username via /direct/new/ ──────────
    username = _extract_username(url)
    if not username:
        print(f"  [IG ERROR] Could not extract username from: {url}")
        return False

    print(f"  [IG NAV] Searching for @{username} via compose screen")

    try:
        await page.goto(NEW_DM_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(2000, 3000))
    except Exception as e:
        print(f"  [IG ERROR] Failed to open DM compose: {e}")
        return False

    await _dismiss_ig_dialogs(page)

    search_box = None
    for sel in [
        'input[placeholder="Search..."]',
        'input[placeholder="Tìm kiếm..."]',
        'input[name="queryBox"]',
        'input[type="text"][autocomplete]',
    ]:
        try:
            search_box = await page.wait_for_selector(sel, timeout=5000)
            if search_box:
                break
        except Exception:
            continue

    if not search_box:
        print("  [IG ERROR] Could not find the 'To' search input.")
        return False

    try:
        await search_box.click()
        await page.wait_for_timeout(500)
        await search_box.fill(username)
        await page.wait_for_timeout(random.randint(2000, 3000))
    except Exception as e:
        print(f"  [IG ERROR] Failed to search for user: {e}")
        return False

    user_result = None
    for sel in [
        f'span:has-text("{username}")',
        '[role="listbox"] [role="option"]',
        'div[role="dialog"] div[role="button"]',
        f'button:has-text("{username}")',
    ]:
        try:
            user_result = await page.wait_for_selector(sel, timeout=5000)
            if user_result:
                break
        except Exception:
            continue

    if not user_result:
        print(f"  [IG ERROR] User @{username} not found in search results.")
        return False

    try:
        await user_result.click()
        await page.wait_for_timeout(random.randint(1000, 2000))
    except Exception as e:
        print(f"  [IG ERROR] Failed to select user: {e}")
        return False

    chat_btn = None
    for sel in [
        'div[role="button"]:has-text("Chat")',
        'button:has-text("Chat")',
        'div[role="button"]:has-text("Next")',
        'button:has-text("Next")',
        'div[role="button"]:has-text("Nhắn tin")',
        'button:has-text("Nhắn tin")',
        'div[role="button"]:has-text("Tiếp")',
        'button:has-text("Tiếp")',
    ]:
        try:
            chat_btn = await page.wait_for_selector(sel, timeout=5000)
            if chat_btn:
                break
        except Exception:
            continue

    if not chat_btn:
        print("  [IG ERROR] Could not find Chat/Next button.")
        return False

    try:
        await chat_btn.click()
        await page.wait_for_timeout(random.randint(2000, 3000))
    except Exception as e:
        print(f"  [IG ERROR] Failed to click Chat/Next: {e}")
        return False

    await _dismiss_ig_dialogs(page)
    return await _type_and_send(page, message)


async def _type_and_send(page: Page, message: str) -> bool:
    """Find the message input, type, and press Enter."""
    input_box = None
    input_selectors = [
        'textarea[placeholder*="Message"]',
        'textarea[placeholder*="message"]',
        'textarea[placeholder*="Nhắn tin"]',
        'div[role="textbox"][contenteditable="true"]',
        'div[aria-label="Message"][role="textbox"]',
        'textarea[aria-label="Message"]',
        'p.xat24cr',
    ]
    for sel in input_selectors:
        try:
            input_box = await page.wait_for_selector(sel, timeout=8000)
            if input_box:
                break
        except Exception:
            continue

    if not input_box:
        print("  [IG ERROR] Could not find message input box.")
        return False

    try:
        await input_box.click()
        await page.wait_for_timeout(random.randint(400, 800))

        for char in message:
            await page.keyboard.type(char, delay=random.randint(30, 100))
            if random.random() < 0.03:
                await page.wait_for_timeout(random.randint(200, 500))

        await page.wait_for_timeout(random.randint(800, 1500))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(random.randint(2000, 4000))

        print("  [IG OK] Message sent.")
        return True

    except Exception as e:
        print(f"  [IG ERROR] Failed to type/send message: {e}")
        return False


async def send_ig_follow_up(page: Page, message: str) -> bool:
    """Send a follow-up in the currently open Instagram DM thread."""
    return await _type_and_send(page, message)
