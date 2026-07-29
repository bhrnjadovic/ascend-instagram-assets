"""One-time (or occasional) fix for the Facebook Page token expiring too fast.

Root cause: a Page access token derived from a short-lived User token inherits that
short (~1-2 hour) expiry. Exchanging the User token for a long-lived one FIRST, then
deriving the Page token from that, produces a Page token that's long-lived (Meta
generally treats these as non-expiring barring a password change or revoked access).

Requires (add to .env yourself, never paste into chat):
    FACEBOOK_APP_ID       — from developers.facebook.com -> your app -> Settings -> Basic
    FACEBOOK_APP_SECRET   — same page
    FACEBOOK_USER_TOKEN   — a FRESH short-lived User token from Graph API Explorer
                            (same steps as FACEBOOK_API_SETUP.md: select the app, Get
                            User Access Token, check pages_show_list/pages_manage_posts/
                            pages_read_engagement/business_management). This one is only
                            needed transiently to run this exchange -- feel free to
                            remove it from .env afterward.

What this does:
    1. Exchanges FACEBOOK_USER_TOKEN for a long-lived User token (~60 days)
    2. Calls /me/accounts with that long-lived token to get the Page's own access
       token -- which, derived this way, is effectively non-expiring
    3. Writes FACEBOOK_PAGE_ACCESS_TOKEN and FACEBOOK_PAGE_ID into .env automatically

Usage:
    python scripts/refresh_facebook_token.py
"""

from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
GRAPH_API_VERSION = "v21.0"


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set. Add it to ascend_instagram_library/.env")
    return value


def write_env_var(name: str, value: str) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[i] = f"{name}={value}"
            found = True
            break
    if not found:
        lines.append(f"{name}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def exchange_for_long_lived_user_token(app_id: str, app_secret: str, short_lived_token: str) -> str:
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_page_token(long_lived_user_token: str) -> tuple[str, str, str]:
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/accounts",
        params={"fields": "id,name,access_token", "access_token": long_lived_user_token},
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json().get("data", [])
    if not pages:
        raise SystemExit("No pages returned from /me/accounts — check the token's permissions.")
    page = pages[0]
    return page["id"], page["name"], page["access_token"]


def main() -> None:
    load_dotenv(ENV_PATH)
    app_id = env("FACEBOOK_APP_ID")
    app_secret = env("FACEBOOK_APP_SECRET")
    user_token = env("FACEBOOK_USER_TOKEN")

    print("Exchanging for a long-lived User token...")
    long_lived = exchange_for_long_lived_user_token(app_id, app_secret, user_token)

    print("Fetching the Page token derived from it...")
    page_id, page_name, page_token = get_page_token(long_lived)
    print(f"Page: {page_name} ({page_id})")

    write_env_var("FACEBOOK_PAGE_ID", page_id)
    write_env_var("FACEBOOK_PAGE_ACCESS_TOKEN", page_token)
    print("Wrote FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN to .env.")
    print("This Page token should not expire on the short ~2hr cycle the previous one did.")


if __name__ == "__main__":
    main()
