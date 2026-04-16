from __future__ import annotations

import asyncio
import random
from playwright.async_api import Page

MESSENGER_URL = "https://www.facebook.com/messages/t/"


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
    url = profile_url.rstrip("/")

    # If already numeric (e.g. https://facebook.com/profile.php?id=12345)
    if "profile.php" in url:
        parts = url.split("id=")
        if len(parts) > 1:
            return parts[1].split("&")[0]

    # Extract the vanity username from the URL
    username = url.split("/")[-1]
    if username:
        return username

    return None


async def send_message(page: Page, profile_url: str, message: str) -> bool:
    """Navigate to a Messenger conversation and send a message.

    Returns True if the message was sent successfully.
    """
    user_id = await _extract_user_id(profile_url, page)
    if not user_id:
        print(f"  [ERROR] Could not extract user ID from: {profile_url}")
        return False

    messenger_url = f"{MESSENGER_URL}{user_id}"
    print(f"  [NAV] Opening conversation: {messenger_url}")

    try:
        await page.goto(messenger_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(3000, 5000))
    except Exception as e:
        print(f"  [ERROR] Failed to navigate to conversation: {e}")
        return False

    # Locate the message input box — Facebook uses contenteditable divs
    input_selectors = [
        'div[aria-label="Message"][role="textbox"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[aria-label="Aa"][role="textbox"]',
        'p.xat24cr.xdj266r',
    ]

    input_box = None
    for selector in input_selectors:
        try:
            input_box = await page.wait_for_selector(selector, timeout=8000)
            if input_box:
                break
        except Exception:
            continue

    if not input_box:
        print("  [ERROR] Could not find message input box.")
        return False

    try:
        await input_box.click()
        await page.wait_for_timeout(random.randint(500, 1000))

        for char in message:
            await page.keyboard.type(char, delay=random.randint(30, 100))
            if random.random() < 0.03:
                await page.wait_for_timeout(random.randint(200, 500))

        await page.wait_for_timeout(random.randint(800, 1500))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(random.randint(2000, 4000))

        print("  [OK] Message sent.")
        return True

    except Exception as e:
        print(f"  [ERROR] Failed to type/send message: {e}")
        return False


async def send_follow_up(page: Page, message: str) -> bool:
    """Send a follow-up message in the currently open conversation."""
    input_selectors = [
        'div[aria-label="Message"][role="textbox"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[aria-label="Aa"][role="textbox"]',
        'p.xat24cr.xdj266r',
    ]

    input_box = None
    for selector in input_selectors:
        try:
            input_box = await page.wait_for_selector(selector, timeout=8000)
            if input_box:
                break
        except Exception:
            continue

    if not input_box:
        print("  [ERROR] Could not find message input box for follow-up.")
        return False

    try:
        await input_box.click()
        await page.wait_for_timeout(random.randint(500, 1000))

        for char in message:
            await page.keyboard.type(char, delay=random.randint(30, 100))
            if random.random() < 0.03:
                await page.wait_for_timeout(random.randint(200, 500))

        await page.wait_for_timeout(random.randint(800, 1500))
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(random.randint(2000, 4000))

        print("  [OK] Follow-up sent.")
        return True

    except Exception as e:
        print(f"  [ERROR] Failed to send follow-up: {e}")
        return False


async def delay_between_messages(min_sec: int, max_sec: int) -> None:
    """Sleep for a random duration between min_sec and max_sec."""
    wait = random.uniform(min_sec, max_sec)
    print(f"  [WAIT] Sleeping {wait:.0f}s before next message...")
    await asyncio.sleep(wait)
