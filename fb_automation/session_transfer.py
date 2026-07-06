"""Export / import Playwright storage state between machines (Mac → Linux VM)."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.async_api import async_playwright

from fb_automation.browser import (
    get_profile_dir,
    get_active_profile,
    _clear_profile_locks,
    _BROWSER_ARGS,
    _USER_AGENT,
    _is_ig_logged_in,
    _is_fb_logged_in,
    INSTAGRAM_URL,
    FACEBOOK_URL,
)

_PLATFORM_URL = {
    "instagram": INSTAGRAM_URL,
    "facebook": FACEBOOK_URL,
}


async def export_session(
    out_path: str | Path,
    *,
    platform: str = "instagram",
    profile_name: str | None = None,
) -> Path:
    """Save cookies + localStorage from the local browser profile to a JSON file."""
    profile_name = profile_name or get_active_profile()
    profile_dir = get_profile_dir(profile_name)
    if not profile_dir.exists():
        raise FileNotFoundError(f"No profile directory: {profile_dir}")

    out = Path(out_path)
    _clear_profile_locks(profile_dir)

    pw = await async_playwright().start()
    try:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            args=_BROWSER_ARGS,
            viewport={"width": 1280, "height": 800},
            user_agent=_USER_AGENT,
            locale="en-US",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(_PLATFORM_URL[platform], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await context.storage_state(path=str(out))
        await context.close()
    finally:
        await pw.stop()

    return out


async def import_session(
    in_path: str | Path,
    *,
    platform: str = "instagram",
    profile_name: str | None = None,
) -> dict:
    """Load storage state JSON into the VM browser profile and verify login."""
    profile_name = profile_name or get_active_profile()
    profile_dir = get_profile_dir(profile_name)
    profile_dir.mkdir(parents=True, exist_ok=True)
    _clear_profile_locks(profile_dir)

    state = json.loads(Path(in_path).read_text())
    cookies = state.get("cookies") or []
    origins = state.get("origins") or []

    pw = await async_playwright().start()
    try:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            args=_BROWSER_ARGS,
            viewport={"width": 1280, "height": 800},
            user_agent=_USER_AGENT,
            locale="en-US",
        )
        if cookies:
            await context.add_cookies(cookies)

        page = context.pages[0] if context.pages else await context.new_page()
        for entry in origins:
            origin = entry.get("origin", "")
            items = entry.get("localStorage") or []
            if not origin or not items:
                continue
            try:
                await page.goto(origin, wait_until="domcontentloaded", timeout=30000)
                for item in items:
                    name, value = item.get("name", ""), item.get("value", "")
                    if name:
                        await page.evaluate(
                            "([n, v]) => localStorage.setItem(n, v)",
                            [name, value],
                        )
            except Exception:
                continue

        if platform == "instagram":
            ok = await _is_ig_logged_in(page)
        else:
            ok = await _is_fb_logged_in(page)

        await context.close()
    finally:
        await pw.stop()

    return {
        "ok": ok,
        "platform": platform,
        "profile": profile_name,
        "cookies_imported": len(cookies),
        "origins_imported": len(origins),
    }
