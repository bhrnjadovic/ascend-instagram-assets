"""Publishes due posts from 05_social_scheduler/upload_manifest.csv to Instagram (via the
Instagram API with Instagram Login, graph.instagram.com) and, if configured, to a linked
Facebook Page (via the standard Facebook Graph API, graph.facebook.com) — as two entirely
separate integrations. Instagram's Content Publishing API has no cross-post-to-Facebook
option, so each platform needs its own credentials and its own API calls.

Requires (add to .env, never paste into chat):
    INSTAGRAM_ACCESS_TOKEN   — long-lived Instagram User access token (starts "IGAA...")
    INSTAGRAM_BUSINESS_ID    — the Instagram account's numeric "id" field from
                               GET https://graph.instagram.com/v21.0/me?fields=id,username
                               (not the "user_id" field — verified these differ and only
                               "id" is confirmed to work as the {ig-user-id} path parameter)
    FACEBOOK_PAGE_ACCESS_TOKEN — a Page access token (NOT the Instagram token above — this
                               comes from a separate Facebook Login for Business consent,
                               see 05_social_scheduler/FACEBOOK_API_SETUP.md)
    FACEBOOK_PAGE_ID         — the Page's numeric ID

Facebook posting is entirely optional: if FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID
aren't set, the script just publishes to Instagram and logs that Facebook was skipped.

Setup you need to complete yourself before Instagram can run (all requires your own Meta
login, cannot be done on your behalf):
    1. Convert the Instagram account to a Professional (Business/Creator) account.
    2. Link it to a Facebook Page you manage.
    3. Create a Meta developer app at developers.facebook.com, add the Instagram product,
       use the "Instagram API with Instagram Login" flow (not Facebook Login for Business).
    4. Generate a long-lived Instagram User access token with instagram_business_basic and
       instagram_business_content_publish scopes.
    5. Find the numeric id: GET https://graph.instagram.com/v21.0/me?fields=id,username

Neither platform's API has native "schedule for later" — calling the publish endpoint
posts immediately. This script provides the scheduling instead: it only publishes rows from
upload_manifest.csv whose scheduled_date is today or earlier and whose ig_status/fb_status
is still "pending". Run it once a day (Windows Task Scheduler, cron, or similar) and it acts
as the scheduler for both platforms independently — if Instagram succeeds but Facebook fails
(or vice versa), only the failed platform is retried on the next run.

IMPORTANT: images must be reachable by URL, not local file paths — both Graph APIs download
them from a public URL. This script assumes you've set PUBLIC_IMAGE_BASE_URL (e.g. hosted on
GitHub, S3, Cloudflare R2, or any static host) mirroring 03_generated_posts/. It will NOT
upload your local files anywhere itself.

Usage:
    python scripts/instagram_publish.py --dry-run
    python scripts/instagram_publish.py --publish-due
"""

from __future__ import annotations

import argparse
import csv
import json
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


ENV_PATH = ROOT / ".env"


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set. Add it to ascend_instagram_library/.env")
    return value


def _write_env_var(name: str, value: str) -> None:
    """Rewrites a single KEY=... line in .env, leaving every other line untouched."""
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def refresh_token(current_token: str) -> tuple[str, int]:
    """Exchanges a still-valid long-lived token for a fresh one, good for another ~60 days.

    Meta allows refreshing any token that's at least 24 hours old and not yet expired —
    calling this on every daily run keeps the token perpetually valid with no manual
    regeneration ever needed, as long as the script actually runs at least once every
    ~60 days (it's scheduled daily, so this holds by construction).
    """
    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload["access_token"], payload.get("expires_in", 0)


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


# --- Facebook Page publishing (separate API, separate token, separate auth flow) ---
FB_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _fb_upload_unpublished_photo(image_url: str, page_id: str, token: str) -> str:
    resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/photos",
        data={"url": image_url, "published": "false", "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _fb_create_feed_post(photo_ids: list[str], message: str, page_id: str, token: str) -> str:
    data = {"message": message, "access_token": token}
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})

    resp = requests.post(f"{FB_GRAPH_BASE}/{page_id}/feed", data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]


def publish_facebook_post(row: dict, page_id: str, token: str, base_url: str) -> str:
    """Facebook has no native swipeable carousel for Page feed posts — attached_media
    produces its own standard multi-photo post instead, which is the closest equivalent
    the Graph API offers. Same 5 images and caption as the Instagram version."""
    slide_keys = ["slide_1", "slide_2", "slide_3", "slide_4", "slide_5"]
    photo_ids = []
    for key in slide_keys:
        url = _image_url(row[key], base_url)
        photo_ids.append(_fb_upload_unpublished_photo(url, page_id, token))
        time.sleep(1)

    message = f"{row['caption']}\n\n{row['hashtags']}"
    post_id = _fb_create_feed_post(photo_ids, message, page_id, token)
    return post_id


def load_manifest() -> list[dict]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_manifest(rows: list[dict]) -> None:
    with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def due_rows(rows: list[dict]) -> list[dict]:
    """A row is due if its date has arrived and at least one platform still needs posting —
    so if Instagram succeeded but Facebook failed last run, only Facebook gets retried."""
    today = date.today().isoformat()
    return [
        r for r in rows
        if r["scheduled_date"] <= today and (r["ig_status"] == "pending" or r["fb_status"] == "pending")
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would publish, without calling the API")
    parser.add_argument("--publish-due", action="store_true", help="Actually publish all due, unpublished posts")
    parser.add_argument("--skip-refresh", action="store_true", help="Skip the automatic token refresh (debugging only)")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)

    # Refresh unconditionally, before anything else, on every single run — including
    # dry-run and days with nothing due — so the token never lapses even during idle
    # stretches. This is what makes the ~60-day expiry a non-issue for a daily-scheduled job.
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    if not args.skip_refresh:
        try:
            new_token, expires_in = refresh_token(token)
            _write_env_var("INSTAGRAM_ACCESS_TOKEN", new_token)
            token = new_token
            days_left = expires_in // 86400
            print(f"Token refreshed — valid for another ~{days_left} days.")
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: token refresh failed ({exc}) — continuing with existing token, "
                  f"which may be close to expiry. Check .env / re-generate manually if this repeats.")

    rows = load_manifest()
    due = due_rows(rows)

    if not due:
        print("Nothing due today.")
        return

    if args.dry_run:
        fb_set = bool(os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip())
        print(f"{len(due)} post(s) would be attempted today:")
        for r in due:
            todo = []
            if r["ig_status"] == "pending":
                todo.append("instagram")
            if r["fb_status"] == "pending":
                todo.append("facebook" if fb_set else "facebook (skipped, not configured)")
            print(f"  {r['post_id']}  scheduled {r['scheduled_date']}  -> {', '.join(todo)}")
        return

    if not args.publish_due:
        parser.error("Specify --dry-run or --publish-due")

    ig_user_id = _env("INSTAGRAM_BUSINESS_ID")
    base_url = _env("PUBLIC_IMAGE_BASE_URL")

    fb_token = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    fb_page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip()
    fb_configured = bool(fb_token and fb_page_id)
    if not fb_configured:
        print("Facebook not configured (FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID unset) — Instagram only.")

    for row in due:
        if row["ig_status"] == "pending":
            try:
                media_id = publish_post(row, ig_user_id, token, base_url)
                row["ig_status"] = f"posted:{media_id}"
                print(f"{row['post_id']}: Instagram published (media id {media_id})")
            except Exception as exc:  # noqa: BLE001
                row["ig_status"] = f"error:{exc}"
                print(f"{row['post_id']}: Instagram FAILED — {exc}")
            save_manifest(rows)  # save after every step so a crash mid-run doesn't lose progress

        if fb_configured and row["fb_status"] == "pending":
            try:
                post_id = publish_facebook_post(row, fb_page_id, fb_token, base_url)
                row["fb_status"] = f"posted:{post_id}"
                print(f"{row['post_id']}: Facebook published (post id {post_id})")
            except Exception as exc:  # noqa: BLE001
                row["fb_status"] = f"error:{exc}"
                print(f"{row['post_id']}: Facebook FAILED — {exc}")
            save_manifest(rows)


if __name__ == "__main__":
    main()
