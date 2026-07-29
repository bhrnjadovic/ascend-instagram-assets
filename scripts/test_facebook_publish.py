"""Standalone Facebook Page publishing test — posts one simple text message and confirms
the returned post ID. Run this before trusting instagram_publish.py's Facebook path in the
daily scheduler.

Usage:
    python scripts/test_facebook_publish.py
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

import facebook_publish

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(ROOT / ".env")

    if not facebook_publish.is_configured():
        raise SystemExit(
            "FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID not set in .env — nothing to test."
        )

    page_id = facebook_publish.env("FACEBOOK_PAGE_ID")
    token = facebook_publish.env("FACEBOOK_PAGE_ACCESS_TOKEN")

    message = (
        "Test post from the Ascend Lending Partners publishing pipeline — "
        "confirming the Facebook integration works before enabling the daily scheduler. "
        "Safe to delete."
    )

    print(f"Posting test message to Page {page_id}...")
    post_id = facebook_publish.publish_text_post(message, page_id, token)
    print(f"SUCCESS. Facebook post ID: {post_id}")
    print(f"View it at: https://www.facebook.com/{post_id}")


if __name__ == "__main__":
    main()
