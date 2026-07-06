#!/usr/bin/env python3
"""One-time Instagram/Facebook login from the terminal."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fb_automation.browser import setup_login, get_active_profile, check_session_status


async def main() -> None:
    parser = argparse.ArgumentParser(description="Save IG/FB login into the local browser profile.")
    parser.add_argument("platform", choices=("instagram", "facebook"))
    parser.add_argument("--profile", default=None, help="Profile name (default: active from profiles.json)")
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Expose Chrome DevTools port — log in from your Mac via SSH tunnel (for VMs)",
    )
    parser.add_argument("--port", type=int, default=9222, help="Remote debugging port (default: 9222)")
    args = parser.parse_args()

    profile = args.profile or get_active_profile()
    print(f"Opening browser for {args.platform} (profile: {profile})…")

    await setup_login(
        platform=args.platform,
        profile_name=profile,
        debug_port=args.port if args.remote else None,
    )

    status = await check_session_status(profile)
    session_key = "ig" if args.platform == "instagram" else "fb"
    if status.get(session_key):
        print(f"Login saved — {args.platform} session verified.")
    else:
        print(f"Login may have failed: {status.get('reason', 'unknown')}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
