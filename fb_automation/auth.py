"""Dashboard access tokens and HttpOnly browser sessions."""

import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Mapping

from fb_automation.paths import data_path

COOKIE_NAME = "dashboard_session"
SESSION_SECONDS = 43200


def get_auth_token() -> str:
    configured = os.environ.get("APP_AUTH_TOKEN", "").strip()
    if configured:
        return configured
    path = data_path(".dashboard_token")
    if not path.exists():
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_urlsafe(32))
    token = path.read_text().strip()
    if not token:
        raise RuntimeError("Dashboard token file is empty; set APP_AUTH_TOKEN")
    return token


def valid_token(candidate: str) -> bool:
    return hmac.compare_digest(candidate.encode(), get_auth_token().encode())


def session_value() -> str:
    issued = str(int(time.time()))
    signature = hmac.new(get_auth_token().encode(), f"dashboard-session-v1:{issued}".encode(), hashlib.sha256).hexdigest()
    return f"{issued}.{signature}"


def authenticated(headers: Mapping[str, str], cookies: Mapping[str, str]) -> bool:
    bearer = headers.get("authorization", "")
    if bearer.startswith("Bearer ") and valid_token(bearer[7:]):
        return True
    cookie = cookies.get(COOKIE_NAME, "")
    try:
        issued, signature = cookie.split(".", 1)
        age = time.time() - int(issued)
    except (ValueError, TypeError):
        return False
    expected = hmac.new(get_auth_token().encode(), f"dashboard-session-v1:{issued}".encode(), hashlib.sha256).hexdigest()
    return 0 <= age <= SESSION_SECONDS and hmac.compare_digest(signature.encode(), expected.encode())
