"""Facebook Page publishing via the standard Facebook Graph API (graph.facebook.com).

Separate integration from Instagram — different token type (Page access token, not the
Instagram User token), different auth flow (Facebook Login for Business via Graph API
Explorer, not Instagram Login), different host. See FACEBOOK_API_SETUP.md for how to get
the Page token.

Requires (add to .env, never paste into chat):
    FACEBOOK_PAGE_ID           — the Page's numeric ID
    FACEBOOK_PAGE_ACCESS_TOKEN — a Page access token with pages_manage_posts,
                                 pages_show_list, pages_read_engagement scopes

Supports four post shapes on /{page-id}/feed and /{page-id}/photos:
    - Text-only         publish_text_post()
    - Single image      publish_single_image_post()
    - Carousel (2+ imgs) publish_carousel_post()   (Facebook's own multi-photo post —
                                                     there's no swipeable carousel format
                                                     for Page feed posts via the API, this
                                                     is the closest equivalent)
    - Link post          publish_link_post()

publish() dispatches to the right one based on what you pass it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).resolve().parent.parent
GRAPH_API_VERSION = "v21.0"
FB_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set. Add it to ascend_instagram_library/.env")
    return value


def is_configured() -> bool:
    return bool(os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
                and os.environ.get("FACEBOOK_PAGE_ID", "").strip())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def publish_text_post(message: str, page_id: str, token: str) -> str:
    resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/feed",
        data={"message": message, "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def publish_single_image_post(image_url: str, message: str, page_id: str, token: str) -> str:
    """Single image goes straight to /photos published=true — no need for the
    unpublished-then-attach dance that carousels require."""
    resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/photos",
        data={"url": image_url, "caption": message, "published": "true", "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _upload_unpublished_photo(image_url: str, page_id: str, token: str) -> str:
    resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/photos",
        data={"url": image_url, "published": "false", "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _create_feed_post_with_media(photo_ids: list[str], message: str, page_id: str, token: str) -> str:
    data = {"message": message, "access_token": token}
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    resp = requests.post(f"{FB_GRAPH_BASE}/{page_id}/feed", data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]


def publish_carousel_post(image_urls: list[str], message: str, page_id: str, token: str) -> str:
    """2+ images as one multi-photo Page post. Uploads each unpublished, then bundles
    them into a single /feed post via attached_media."""
    photo_ids = []
    for url in image_urls:
        photo_ids.append(_upload_unpublished_photo(url, page_id, token))
        time.sleep(1)  # be gentle between uploads
    return _create_feed_post_with_media(photo_ids, message, page_id, token)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def publish_link_post(link_url: str, message: str, page_id: str, token: str) -> str:
    resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/feed",
        data={"message": message, "link": link_url, "access_token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def publish(
    page_id: str,
    token: str,
    message: str = "",
    image_urls: list[str] | None = None,
    link_url: str | None = None,
) -> str:
    """Dispatches to the right post type based on what's provided:
    2+ images -> carousel, 1 image -> single image, link -> link post, else -> text-only."""
    image_urls = image_urls or []
    if len(image_urls) >= 2:
        return publish_carousel_post(image_urls, message, page_id, token)
    if len(image_urls) == 1:
        return publish_single_image_post(image_urls[0], message, page_id, token)
    if link_url:
        return publish_link_post(link_url, message, page_id, token)
    return publish_text_post(message, page_id, token)
