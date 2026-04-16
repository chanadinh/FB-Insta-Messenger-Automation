from __future__ import annotations

import json
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page

COOKIES_PATH = Path("cookies.json")
FACEBOOK_URL = "https://www.facebook.com"
FACEBOOK_LOGIN = f"{FACEBOOK_URL}/login"
INSTAGRAM_URL = "https://www.instagram.com"
INSTAGRAM_LOGIN = f"{INSTAGRAM_URL}/accounts/login/"
PROFILES_PATH = Path("profiles.json")

_pw_instance = None

_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
]
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


class CookieAuthError(Exception):
    """Raised when the saved session is invalid or missing."""


# ── Profile management ─────────────────────────────────────────

def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def get_profile_dir(profile_name: str) -> Path:
    return Path(f"browser_profile_{_slug(profile_name)}")


def load_profiles() -> dict:
    if PROFILES_PATH.exists():
        try:
            return json.loads(PROFILES_PATH.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    default = {"profiles": ["Main"], "active": "Main"}
    save_profiles(default)
    return default


def save_profiles(data: dict) -> None:
    PROFILES_PATH.write_text(json.dumps(data, indent=2))


def get_active_profile() -> str:
    return load_profiles().get("active", "Main")


# ── Login checks ───────────────────────────────────────────────

async def _is_fb_logged_in(page: Page) -> bool:
    try:
        await page.goto(FACEBOOK_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        login_form = await page.query_selector('form[action*="login"]')
        return login_form is None
    except Exception:
        return False


async def _is_ig_logged_in(page: Page) -> bool:
    try:
        await page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        login_link = await page.query_selector('a[href*="/accounts/login"]')
        login_form = await page.query_selector('form[id="loginForm"]')
        login_btn = await page.query_selector('button:has-text("Log in")')
        return login_link is None and login_form is None and login_btn is None
    except Exception:
        return False


# ── Helpers ────────────────────────────────────────────────────

async def _import_cookies_if_needed(context: BrowserContext, profile_dir: Path) -> None:
    marker = profile_dir / ".cookies_imported"
    if marker.exists() or not COOKIES_PATH.exists():
        return
    try:
        cookies = json.loads(COOKIES_PATH.read_text())
        if cookies:
            await context.add_cookies(cookies)
            marker.write_text("done")
    except (json.JSONDecodeError, KeyError):
        pass


def _clear_profile_locks(profile_dir: Path) -> None:
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock = profile_dir / name
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


async def _open_persistent_context(headless: bool, profile_name: str | None = None) -> BrowserContext:
    global _pw_instance
    _pw_instance = await async_playwright().start()

    if profile_name is None:
        profile_name = get_active_profile()
    profile_dir = get_profile_dir(profile_name)
    profile_dir.mkdir(exist_ok=True)
    _clear_profile_locks(profile_dir)

    context = await _pw_instance.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        args=_BROWSER_ARGS,
        viewport={"width": 1280, "height": 800},
        user_agent=_USER_AGENT,
        locale="en-US",
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    await _import_cookies_if_needed(context, profile_dir)
    return context


# ── Public API ─────────────────────────────────────────────────

async def check_session_status(profile_name: str | None = None) -> dict:
    if profile_name is None:
        profile_name = get_active_profile()
    profile_dir = get_profile_dir(profile_name)
    if not profile_dir.exists() or not any(profile_dir.iterdir()):
        return {
            "fb": False,
            "ig": False,
            "reason": f"No browser profile for '{profile_name}'. Use Setup Login.",
        }
    return {
        "fb": True,
        "ig": True,
        "reason": f"Profile '{profile_name}' exists — sessions should be active.",
    }


async def launch_browser(
    headless: bool = True,
    need_fb: bool = True,
    need_ig: bool = False,
    profile_name: str | None = None,
) -> tuple[BrowserContext, Page]:
    """Launch Chromium with the named persistent profile."""
    if profile_name is None:
        profile_name = get_active_profile()
    profile_dir = get_profile_dir(profile_name)

    if not profile_dir.exists() or not any(profile_dir.iterdir()):
        raise CookieAuthError(
            f"No browser profile for '{profile_name}'. Use 'Setup Login' first."
        )

    context = await _open_persistent_context(headless, profile_name)
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def setup_login(platform: str = "facebook", profile_name: str | None = None) -> None:
    """Open a visible browser for one-time manual login on the given profile."""
    context = await _open_persistent_context(headless=False, profile_name=profile_name)
    page = context.pages[0] if context.pages else await context.new_page()

    if platform == "instagram":
        already = await _is_ig_logged_in(page)
        if already:
            await context.close()
            return
        await page.goto(INSTAGRAM_LOGIN, wait_until="domcontentloaded")
        while True:
            await page.wait_for_timeout(3000)
            url = page.url
            if "/accounts/login" not in url and "/challenge" not in url:
                form = await page.query_selector('form[id="loginForm"]')
                if form is None:
                    break
    else:
        already = await _is_fb_logged_in(page)
        if already:
            await context.close()
            return
        await page.goto(FACEBOOK_LOGIN, wait_until="domcontentloaded")
        while True:
            await page.wait_for_timeout(3000)
            url = page.url
            if "login" not in url and "checkpoint" not in url:
                form = await page.query_selector('form[action*="login"]')
                if form is None:
                    break

    await page.wait_for_timeout(2000)
    await context.close()


async def close_browser(context: BrowserContext) -> None:
    await context.close()
