"""Single entry point for the Ascend Instagram content pipeline.

Examples:
    python scripts/run_batch.py --test
    python scripts/run_batch.py --post ALP-001
    python scripts/run_batch.py --start ALP-001 --end ALP-003
    python scripts/run_batch.py --all --confirm-paid-run
    python scripts/run_batch.py --resume
    python scripts/run_batch.py --dry-run --all

Concurrency, retries and cost estimation only matter once config.yaml's
background_mode is switched to "supplied" or "mixed" (an external image API is
involved). In the default "generated" mode everything runs locally with Pillow,
so there is nothing to pay for and --confirm-paid-run is not required.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

import build_content_library
import compose_slides
import quality_check

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
LIBRARY_PATH = ROOT / "01_content" / "carousel_library.json"

TEST_BATCH_IDS = ["ALP-001", "ALP-002", "ALP-003"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "scripts" / "run_batch.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("run_batch")


def load_library() -> list[dict]:
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def select_posts(library: list[dict], args: argparse.Namespace) -> list[dict]:
    if args.test:
        return [p for p in library if p["post_id"] in TEST_BATCH_IDS]
    if args.post:
        return [p for p in library if p["post_id"] == args.post]
    if args.start and args.end:
        ids = sorted(p["post_id"] for p in library)
        in_range = [i for i in ids if args.start <= i <= args.end]
        return [p for p in library if p["post_id"] in in_range]
    if args.all:
        return library
    raise SystemExit("Specify one of --test, --post, --start/--end, --all, or --resume")


def already_approved(post_id: str) -> bool:
    approved_dir = ROOT / CONFIG["output"]["qa_dir"] / "approved" / post_id
    return approved_dir.exists() and any(approved_dir.glob("*.png"))


# Per-image, gpt-image-2, sourced from OpenAI's published pricing (developers.openai.com/api/docs/pricing).
IMAGE_PRICING = {
    ("gpt-image-2", "low", "1024x1536"): 0.005,
    ("gpt-image-2", "medium", "1024x1536"): 0.041,
    ("gpt-image-2", "high", "1024x1536"): 0.165,
    ("gpt-image-2", "low", "1024x1024"): 0.006,
    ("gpt-image-2", "medium", "1024x1024"): 0.053,
    ("gpt-image-2", "high", "1024x1024"): 0.211,
}


def estimate_cost(posts: list[dict]) -> None:
    if CONFIG["background_mode"] == "generated":
        slide_count = sum(len(p["slides"]) for p in posts)
        log.info(f"Cost estimate: {slide_count} slides across {len(posts)} post(s) — $0.00 (Pillow-only, no API calls)")
        return

    # Only the cover slide (1 per post) hits the paid API; slides 2-5 stay Pillow-only.
    # Anything already in the background cache costs nothing to re-render.
    cache_dir = ROOT / CONFIG["output"]["posts_dir"] / "_bg_cache"
    to_generate = [p for p in posts if not (cache_dir / f"{p['post_id']}_cover_bg.png").exists()]
    cached_count = len(posts) - len(to_generate)

    model = CONFIG["image"]["model"]
    quality = CONFIG["image"]["quality"]
    size = CONFIG["image"].get("size", "1024x1536")
    per_image = IMAGE_PRICING.get((model, quality, size), 0.05)
    cost = len(to_generate) * per_image

    log.info(
        f"Cost estimate: {len(to_generate)} new cover image(s) to generate "
        f"({cached_count} already cached, free) x ~${per_image:.3f} = ~${cost:.2f} "
        f"[{model}, {quality}, {size}]"
    )


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run the fixed 3-post test batch")
    parser.add_argument("--post", help="Single post_id, e.g. ALP-001")
    parser.add_argument("--start", help="Start of an inclusive post_id range")
    parser.add_argument("--end", help="End of an inclusive post_id range")
    parser.add_argument("--all", action="store_true", help="Every post in the library")
    parser.add_argument("--resume", action="store_true", help="Re-run only posts not yet approved")
    parser.add_argument("--dry-run", action="store_true", help="Log what would run without writing files")
    parser.add_argument("--confirm-paid-run", action="store_true", help="Required to proceed when background_mode is not 'generated'")
    args = parser.parse_args()

    library = load_library()

    if args.resume:
        posts = [p for p in library if not already_approved(p["post_id"])]
        log.info(f"Resuming: {len(posts)} post(s) not yet approved")
    else:
        posts = select_posts(library, args)

    if not posts:
        log.info("Nothing to do.")
        return

    log.info(f"Selected posts: {[p['post_id'] for p in posts]}")
    estimate_cost(posts)

    if CONFIG["background_mode"] != "generated" and not args.confirm_paid_run:
        raise SystemExit(
            f"background_mode is '{CONFIG['background_mode']}' (uses a paid image API). "
            "Re-run with --confirm-paid-run to proceed."
        )

    if args.dry_run:
        for p in posts:
            log.info(f"[DRY RUN] Would render {p['post_id']} ({len(p['slides'])} slides)")
        return

    build_content_library.main()

    for post in posts:
        written = compose_slides.render_post(post)
        log.info(f"{post['post_id']}: wrote {len(written)} files")

    rows = quality_check.run_qa(posts)
    quality_check.write_report(rows)
    quality_check.sort_into_folders(rows)
    approved = sum(1 for r in rows if r["overall_status"] == "APPROVED")
    log.info(f"QA complete: {approved}/{len(rows)} slides approved")


if __name__ == "__main__":
    main()
