#!/usr/bin/env python3
"""One-time Instagram/Facebook login from the terminal (for Linux VMs with xvfb-run)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from repo root: python scripts/setup_login_cli.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fb_automation.browser import setup_login, get_active_profile


async def main() -> None:
    parser = argparse.ArgumentParser(description="Save IG/FB login into the local browser profile.")
    parser.add_argument("platform", choices=("instagram", "facebook"))
    parser.add_argument("--profile", default=None, help="Profile name (default: active from profiles.json)")
    args = parser.parse_args()

    profile = args.profile or get_active_profile()
    print(f"Opening browser for {args.platform} (profile: {profile})…")
    print("Complete login in the browser window; it will close automatically when done.")
    await setup_login(platform=args.platform, profile_name=profile)
    print("Login saved.")


if __name__ == "__main__":
    asyncio.run(main())
