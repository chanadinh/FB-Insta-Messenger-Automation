#!/usr/bin/env python3
"""Import session JSON into the VM browser profile (run on Linux VM)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fb_automation.session_transfer import import_session


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import IG/FB session JSON into local profile.")
    parser.add_argument("file", help="Session JSON from export_session.py")
    parser.add_argument("platform", choices=("instagram", "facebook"))
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    result = await import_session(
        args.file,
        platform=args.platform,
        profile_name=args.profile,
    )
    if result["ok"]:
        print(f"OK — {args.platform} session active in profile '{result['profile']}'.")
        print(f"Imported {result['cookies_imported']} cookies, {result['origins_imported']} origins.")
    else:
        print("Import finished but login check FAILED.")
        print("Export again from Mac while logged into Instagram, or use vm_setup_login.sh --remote.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
