#!/usr/bin/env python3
"""Export Instagram/Facebook session from your Mac browser profile (run on Mac)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fb_automation.session_transfer import export_session
from fb_automation.browser import get_active_profile


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export IG/FB session to a JSON file.")
    parser.add_argument("platform", choices=("instagram", "facebook"))
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file (default: ig_session.json or fb_session.json)",
    )
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()

    out = args.output or (
        "ig_session.json" if args.platform == "instagram" else "fb_session.json"
    )
    profile = args.profile or get_active_profile()
    path = await export_session(out, platform=args.platform, profile_name=profile)
    print(f"Exported profile '{profile}' → {path}")
    print(f"Copy to VM: scp {path} linux@YOUR_VM:~/FB-Insta-Messenger-Automation/")


if __name__ == "__main__":
    asyncio.run(main())
