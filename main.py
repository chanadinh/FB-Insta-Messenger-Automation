#!/usr/bin/env python3
"""Facebook Messenger Automation — send personalized messages to a list of contacts."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from fb_automation.browser import launch_browser, close_browser
from fb_automation.messenger import send_message, send_follow_up, delay_between_messages
from fb_automation.templates import render_message
from fb_automation.chatgen import generate_follow_ups
from fb_automation.logger import log_message

DEFAULT_CONFIG = {
    "message_template": "Hey {{first_name}}, just wanted to reach out!",
    "min_delay_seconds": 30,
    "max_delay_seconds": 90,
    "headless": False,
    "dry_run": False,
    "openai_api_key": "",
    "openai_model": "gpt-5.4",
    "follow_up_count": 3,
    "follow_up_delay_min": 5,
    "follow_up_delay_max": 15,
    "chat_tone": "friendly and casual",
}


def load_config(path: str) -> dict:
    config = dict(DEFAULT_CONFIG)
    p = Path(path)
    if p.exists():
        with p.open() as f:
            config.update(json.load(f))
    else:
        print(f"[WARN] Config file '{path}' not found, using defaults.")
    return config


def load_contacts(path: str) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] Contacts file '{path}' not found.")
        sys.exit(1)
    with p.open(newline="") as f:
        reader = csv.DictReader(f)
        contacts = list(reader)
    if not contacts:
        print("[ERROR] Contacts file is empty.")
        sys.exit(1)
    return contacts


async def run(config: dict, contacts: list[dict[str, str]]) -> None:
    template = config["message_template"]
    min_delay = config["min_delay_seconds"]
    max_delay = config["max_delay_seconds"]
    dry_run = config["dry_run"]
    headless = config["headless"]
    api_key = config.get("openai_api_key", "")
    openai_model = config.get("openai_model", "gpt-5.4")
    follow_up_count = config.get("follow_up_count", 3)
    fu_delay_min = config.get("follow_up_delay_min", 5)
    fu_delay_max = config.get("follow_up_delay_max", 15)
    chat_tone = config.get("chat_tone", "friendly and casual")

    total = len(contacts)
    sent = 0
    skipped = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"  Facebook Messenger Automation")
    print(f"  Contacts: {total}  |  Dry run: {dry_run}  |  Headless: {headless}")
    print(f"  Delay: {min_delay}-{max_delay}s between messages")
    print(f"{'='*60}\n")

    if not dry_run:
        context, page = await launch_browser(headless=headless)
    else:
        context = page = None

    try:
        for i, contact in enumerate(contacts, 1):
            profile_url = contact.get("profile_url", "").strip()
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()

            print(f"\n[{i}/{total}] Processing: {name} ({profile_url})")

            if not profile_url:
                print("  [SKIP] No profile URL provided.")
                log_message(contact, "skipped", "no profile_url")
                skipped += 1
                continue

            message = render_message(template, contact)

            if dry_run:
                print(f"  [DRY RUN] Would send: \"{message}\"")
                if api_key:
                    follow_ups = generate_follow_ups(
                        message, name, api_key,
                        model=openai_model,
                        num_messages=follow_up_count,
                        tone=chat_tone,
                    )
                    for j, fu in enumerate(follow_ups, 1):
                        print(f"  [DRY RUN] Follow-up {j}: \"{fu}\"")
                log_message(contact, "dry_run", message)
                sent += 1
                continue

            success = await send_message(page, profile_url, message)

            if success:
                log_message(contact, "sent", message)
                sent += 1

                if api_key:
                    print(f"  [AI] Generating {follow_up_count} follow-up messages...")
                    try:
                        follow_ups = generate_follow_ups(
                            message, name, api_key,
                            model=openai_model,
                            num_messages=follow_up_count,
                            tone=chat_tone,
                        )
                    except Exception as e:
                        print(f"  [AI ERROR] {e}")
                        follow_ups = []

                    for j, fu in enumerate(follow_ups, 1):
                        await delay_between_messages(fu_delay_min, fu_delay_max)
                        print(f"  [FOLLOW-UP {j}/{len(follow_ups)}] Sending: \"{fu}\"")
                        fu_ok = await send_follow_up(page, fu)
                        if fu_ok:
                            log_message(contact, "sent", f"[follow-up {j}] {fu}")
                        else:
                            log_message(contact, "failed", f"[follow-up {j}] {fu}")
            else:
                log_message(contact, "failed", message)
                failed += 1

            if i < total:
                await delay_between_messages(min_delay, max_delay)

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Stopping gracefully...")
    finally:
        if context:
            await close_browser(context)

    print(f"\n{'='*60}")
    print(f"  Results: {sent} sent, {skipped} skipped, {failed} failed")
    print(f"  Log saved to: message_log.csv")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send personalized Facebook messages to a list of contacts."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="Path to config file (default: config.json)",
    )
    parser.add_argument(
        "--contacts",
        default="contacts.csv",
        help="Path to contacts CSV file (default: contacts.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview messages without sending them",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    if args.dry_run:
        config["dry_run"] = True
    if args.headless:
        config["headless"] = True

    contacts = load_contacts(args.contacts)

    asyncio.run(run(config, contacts))


if __name__ == "__main__":
    main()
