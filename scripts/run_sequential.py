"""Driver that processes each pending post one at a time and writes a run_state.json
checkpoint after every successfully approved post.

Usage:
    python scripts/run_sequential.py --confirm-paid-run

Picks up exactly where the project left off by checking 04_quality_control/approved/
for posts already done, then processes the remainder sequentially.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
STATE_PATH = ROOT / "run_state.json"
LIBRARY_PATH = ROOT / "01_content" / "carousel_library.json"

IMAGE_PRICING = {
    ("gpt-image-2", "low",    "1024x1536"): 0.005,
    ("gpt-image-2", "medium", "1024x1536"): 0.041,
    ("gpt-image-2", "high",   "1024x1536"): 0.165,
    ("gpt-image-2", "low",    "1024x1024"): 0.006,
    ("gpt-image-2", "medium", "1024x1024"): 0.053,
    ("gpt-image-2", "high",   "1024x1024"): 0.211,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "scripts" / "run_sequential.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("run_sequential")


def already_approved(post_id: str) -> bool:
    approved_dir = ROOT / CONFIG["output"]["qa_dir"] / "approved" / post_id
    return approved_dir.exists() and any(approved_dir.glob("*.png"))


def per_image_cost() -> float:
    model   = CONFIG["image"]["model"]
    quality = CONFIG["image"]["quality"]
    size    = CONFIG["image"].get("size", "1024x1536")
    return IMAGE_PRICING.get((model, quality, size), 0.05)


def update_checkpoint(state: dict, post: dict, cost_incurred: float) -> None:
    """Update run_state.json after a post is successfully approved.

    Counts POSTS, not slides — a previous version of this function incremented
    posts_fully_generated_and_approved by the per-post slide count (up to 5), which
    inflated the counter roughly 5x over a long run. Always re-derive counts from the
    real library/approved-folder sizes rather than accumulating a running total, so a
    bug here can't silently drift the checkpoint away from ground truth again.
    """
    all_posts = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    all_ids = sorted(p["post_id"] for p in all_posts)
    post_id = post["post_id"]

    approved_now = sum(1 for i in all_ids if already_approved(i))

    state["total_posts_in_library"] = len(all_ids)
    state["last_completed_post_id"] = post_id
    state["posts_fully_generated_and_approved"] = approved_now
    state["posts_content_written_but_not_yet_rendered"] = len(all_ids) - approved_now

    remaining_ids = [i for i in all_ids if i > post_id and not already_approved(i)]
    if remaining_ids:
        state["next_post_id_to_generate"]  = remaining_ids[0]
        state["next_post_id_range_pending"] = f"{remaining_ids[0]} to {remaining_ids[-1]}"
    else:
        state["next_post_id_to_generate"]  = "DONE"
        state["next_post_id_range_pending"] = "NONE"

    spend = state.setdefault("spend_tracking", {})
    spend["images_generated_so_far"] = spend.get("images_generated_so_far", 0) + 1
    spend["actual_spend_so_far_usd"] = round(
        spend.get("actual_spend_so_far_usd", 0.0) + cost_incurred, 4
    )
    remaining_bal = spend.get("user_openai_balance_topped_up_usd", 10.0) - spend["actual_spend_so_far_usd"]
    spend["estimated_remaining_balance_usd"] = round(remaining_bal, 4)

    import datetime
    state["checkpoint_timestamp_utc"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Checkpoint saved: {post_id} done — {state['posts_fully_generated_and_approved']} posts approved total")


def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-paid-run", action="store_true",
                        help="Required when background_mode is not 'generated'")
    args = parser.parse_args()

    if CONFIG["background_mode"] != "generated" and not args.confirm_paid_run:
        raise SystemExit(
            f"background_mode is '{CONFIG['background_mode']}' (uses a paid image API). "
            "Re-run with --confirm-paid-run to proceed."
        )

    # Import pipeline modules (sys.path already includes scripts/ when run from there)
    import build_content_library
    import compose_slides
    import quality_check

    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    pending = [p for p in library if not already_approved(p["post_id"])]
    state   = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    if not pending:
        log.info("Nothing to do — all posts already approved.")
        return

    log.info(f"Pending posts ({len(pending)}): {[p['post_id'] for p in pending]}")

    # Estimate cost
    cache_dir   = ROOT / CONFIG["output"]["posts_dir"] / "_bg_cache"
    to_generate = [p for p in pending if not (cache_dir / f"{p['post_id']}_cover_bg.png").exists()]
    cost_est    = len(to_generate) * per_image_cost()
    log.info(
        f"Cost estimate: {len(to_generate)} new cover image(s) x ~${per_image_cost():.3f} = ~${cost_est:.2f} "
        f"({len(pending) - len(to_generate)} already cached = free)"
    )

    # Validate library + regenerate CSVs once up front
    build_content_library.main()

    successes = 0
    failures  = []

    for post in pending:
        post_id = post["post_id"]
        log.info(f"--- Starting {post_id} ({post.get('topic', '')}) ---")
        try:
            written = compose_slides.render_post(post)
            log.info(f"{post_id}: rendered {len(written)} file(s)")

            rows = quality_check.run_qa([post])
            quality_check.sort_into_folders(rows)

            approved_slides = [r for r in rows if r["overall_status"] == "APPROVED"]
            rejected_slides = [r for r in rows if r["overall_status"] == "REJECTED"]

            log.info(f"{post_id}: QA — {len(approved_slides)} approved, {len(rejected_slides)} rejected")

            if rejected_slides:
                reasons = list({r["rejection_reason"] for r in rejected_slides if r["rejection_reason"]})
                log.warning(f"{post_id}: has rejected slide(s): {reasons}")

            # Count as fully done if ALL slides passed
            all_passed = len(rejected_slides) == 0
            if all_passed:
                # Cover image cost only applies if not already cached
                was_cached = (cache_dir / f"{post_id}_cover_bg.png").exists() and \
                    not any(p["post_id"] == post_id for p in to_generate)
                cost_this_post = 0.0 if was_cached else per_image_cost()
                update_checkpoint(state, post, cost_this_post)
                successes += 1

                # write_report overwrites the whole file, so re-run QA across every post
                # approved so far (cheap — no API calls, just local file checks) to keep
                # qa_report.csv cumulative rather than clobbered down to one post's rows.
                approved_so_far = [p for p in library if already_approved(p["post_id"])]
                quality_check.write_report(quality_check.run_qa(approved_so_far))
            else:
                log.error(f"{post_id}: FAILED QA — not checkpointed as complete")
                failures.append(post_id)

        except Exception as exc:
            log.exception(f"{post_id}: EXCEPTION during render — skipping: {exc}")
            failures.append(post_id)

        time.sleep(0.5)  # brief pause between posts to be courteous to the API

    log.info(f"=== Run complete: {successes}/{len(pending)} posts approved ===")
    if failures:
        log.warning(f"Failed/rejected posts: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
