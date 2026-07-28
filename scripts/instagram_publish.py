"""Publishes due posts from 05_social_scheduler/upload_manifest.csv to Instagram via the
Instagram API with Instagram Login (graph.instagram.com), Content Publishing endpoints.

Requires (add to .env, never paste into chat):
    INSTAGRAM_ACCESS_TOKEN   — long-lived Instagram User access token (starts "IGAA...")
    INSTAGRAM_BUSINESS_ID    — the Instagram account's numeric "id" field from
                               GET https://graph.instagram.com/v21.0/me?fields=id,username
                               (not the "user_id" field — verified these differ and only
                               "id" is confirmed to work as the {ig-user-id} path parameter)

Setup you need to complete yourself before this can run (all requires your own Meta login,
cannot be done on your behalf):
    1. Convert the Instagram account to a Professional (Business/Creator) account.
    2. Link it to a Facebook Page you manage.
    3. Create a Meta developer app at developers.facebook.com, add the Instagram product,
       use the "Instagram API with Instagram Login" flow (not Facebook Login for Business).
    4. Generate a long-lived Instagram User access token with instagram_business_basic and
       instagram_business_content_publish scopes.
    5. Find the numeric id: GET https://graph.instagram.com/v21.0/me?fields=id,username

Instagram's Graph API has no native "schedule for later" — calling the publish endpoint
posts immediately. This script provides the scheduling instead: it only publishes rows from
upload_manifest.csv whose scheduled_date is today or earlier and whose status is "pending".
Run it once a day (via Windows Task Scheduler, cron, or a Claude scheduled task) and it acts
as the scheduler.

IMPORTANT: images must be reachable by URL, not local file paths — the Graph API downloads
them from a public URL. This script assumes you've set PUBLIC_IMAGE_BASE_URL (e.g. hosted on
S3, Cloudflare R2, or any static host) mirroring 03_generated_posts/. It will NOT upload your
local files anywhere itself.

Usage:
    python scripts/instagram_publish.py --dry-run
    python scripts/instagram_publish.py --publish-due
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "05_social_scheduler" / "upload_manifest.csv"
GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.instagram.com/{GRAPH_API_VERSION}"


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set. Add it to ascend_instagram_library/.env")
    return value


def _image_url(local_path: str, base_url: str) -> str:
    rel = Path(local_path).relative_to(ROOT).as_posix()
    return f"{base_url.rstrip('/')}/{rel}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _create_item_container(image_url: str, ig_user_id: str, token: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={"image_url": image_url, "is_carousel_item": "true", "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _create_carousel_container(child_ids: list[str], caption: str, ig_user_id: str, token: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": token,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _publish_container(container_id: str, ig_user_id: str, token: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def publish_post(row: dict, ig_user_id: str, token: str, base_url: str) -> str:
    slide_keys = ["slide_1", "slide_2", "slide_3", "slide_4", "slide_5"]
    child_ids = []
    for key in slide_keys:
        url = _image_url(row[key], base_url)
        child_ids.append(_create_item_container(url, ig_user_id, token))
        time.sleep(1)  # be gentle between container creations

    caption = f"{row['caption']}\n\n{row['hashtags']}"
    container_id = _create_carousel_container(child_ids, caption, ig_user_id, token)
    time.sleep(2)  # containers need a moment to finish processing before publish
    media_id = _publish_container(container_id, ig_user_id, token)
    return media_id


def load_manifest() -> list[dict]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_manifest(rows: list[dict]) -> None:
    with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def due_rows(rows: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    return [r for r in rows if r["status"] == "pending" and r["scheduled_date"] <= today]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would publish, without calling the API")
    parser.add_argument("--publish-due", action="store_true", help="Actually publish all due, unpublished posts")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    rows = load_manifest()
    due = due_rows(rows)

    if not due:
        print("Nothing due today.")
        return

    if args.dry_run:
        print(f"{len(due)} post(s) would publish today:")
        for r in due:
            print(f"  {r['post_id']}  scheduled {r['scheduled_date']}")
        return

    if not args.publish_due:
        parser.error("Specify --dry-run or --publish-due")

    token = _env("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = _env("INSTAGRAM_BUSINESS_ID")
    base_url = _env("PUBLIC_IMAGE_BASE_URL")

    for row in due:
        try:
            media_id = publish_post(row, ig_user_id, token, base_url)
            row["status"] = f"posted:{media_id}"
            print(f"{row['post_id']}: published (media id {media_id})")
        except Exception as exc:  # noqa: BLE001
            row["status"] = f"error:{exc}"
            print(f"{row['post_id']}: FAILED — {exc}")
        save_manifest(rows)  # save after every post so a crash mid-run doesn't lose progress


if __name__ == "__main__":
    main()
