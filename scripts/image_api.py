"""Calls an external image-generation API for photographic slide backgrounds.

Only used when config.yaml's background_mode is "mixed" or "supplied". In "mixed" mode
(the current setting), only the cover slide gets an AI-generated photographic background;
every other slide keeps the free, deterministic Pillow-generated panels from
generate_backgrounds.py. Results are cached to disk so re-runs never re-bill an image
that's already been fetched.

Every request is logged (model, prompt, timestamp, response id) to image_api.log.
The API key is read from the IMAGE_API_KEY environment variable (see .env) and is
never written to a log, printed, or embedded in any output file.
"""

from __future__ import annotations

import json
import logging
import os
import time
from base64 import b64decode
from pathlib import Path

import requests
import yaml
from tenacity import retry, stop_after_attempt, wait_exponential

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
CACHE_DIR = ROOT / "03_generated_posts" / "_bg_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"

log = logging.getLogger("image_api")
if not log.handlers:
    handler = logging.FileHandler(ROOT / "scripts" / "image_api.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


class ImageAPIError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("IMAGE_API_KEY", "").strip()
    if not key:
        raise ImageAPIError("IMAGE_API_KEY is not set. Add it to ascend_instagram_library/.env")
    return key


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
def _request_image(prompt: str, size: str, quality: str) -> tuple[bytes, str]:
    model = CONFIG["image"]["model"] or "gpt-image-2"
    response = requests.post(
        OPENAI_IMAGES_URL,
        headers={"Authorization": f"Bearer {_api_key()}"},
        json={"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1},
        timeout=90,
    )
    if response.status_code != 200:
        # Never include headers (would contain the Authorization value) in the raised error.
        raise ImageAPIError(f"OpenAI image API returned {response.status_code}: {response.text[:500]}")

    payload = response.json()
    image_bytes = b64decode(payload["data"][0]["b64_json"])
    response_id = payload.get("created", "unknown")

    log.info(json.dumps({
        "model": model,
        "size": size,
        "quality": quality,
        "prompt": prompt[:200],
        "response_id": str(response_id),
        "timestamp": time.time(),
    }))
    return image_bytes, str(response_id)


def get_cover_background(post_id: str, prompt: str, size: str | None = None, quality: str | None = None) -> Path:
    """Returns the path to a cached (or freshly generated) cover background for post_id.

    Never re-calls the API if a cached file already exists for this post_id — safe to
    call repeatedly across --resume runs without incurring repeat charges.
    """
    cache_path = CACHE_DIR / f"{post_id}_cover_bg.png"
    if cache_path.exists():
        return cache_path

    size = size or CONFIG["image"].get("size", "1024x1536")
    quality = quality or CONFIG["image"]["quality"]
    image_bytes, _response_id = _request_image(prompt, size, quality)
    cache_path.write_bytes(image_bytes)
    return cache_path
