"""Builds a posting calendar across the full content library.

Interleaves categories round-robin (rather than posting all 26 Scenario-Based posts
back to back, say) so the feed reads as a natural mix, then assigns weekday dates
starting from --start-date.

Usage:
    python scripts/build_schedule.py --start-date 2026-08-03 --posts-per-day 1
    python scripts/build_schedule.py --start-date 2026-08-03 --posts-per-day 2 --days-of-week mon,tue,wed,thu,fri
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = ROOT / "01_content" / "carousel_library.json"
OUT_DIR = ROOT / "05_social_scheduler"

DOW_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def interleave_by_category(posts: list[dict]) -> list[dict]:
    """Round-robin across categories so consecutive posts rarely share a category."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        buckets[p["category"]].append(p)
    # Stable order: categories with more posts get visited more often, largest first
    # so the tail of the schedule isn't dominated by a single leftover category.
    order = sorted(buckets.keys(), key=lambda c: -len(buckets[c]))
    queues = [buckets[c] for c in order]

    result = []
    while any(queues):
        for q in queues:
            if q:
                result.append(q.pop(0))
    return result


def next_posting_dates(start: date, posting_days: set[int], posts_per_day: int, count: int) -> list[tuple[date, int]]:
    """Returns (date, slot_index) pairs, slot_index distinguishing multiple same-day posts."""
    dates = []
    d = start
    while len(dates) < count:
        if d.weekday() in posting_days:
            for slot in range(posts_per_day):
                dates.append((d, slot))
                if len(dates) == count:
                    break
        d += timedelta(days=1)
    return dates


def slot_times(posts_per_day: int, day_start: str, day_end: str) -> list[str]:
    """Evenly spreads N posting times across the working window, e.g. 4 posts between
    08:00-19:00 -> 08:00, 12:40, 17:20 ... rather than stacking every post at one timestamp."""
    start_h, start_m = map(int, day_start.split(":"))
    end_h, end_m = map(int, day_end.split(":"))
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    if posts_per_day == 1:
        return [day_start]
    step = (end_min - start_min) / (posts_per_day - 1)
    times = []
    for i in range(posts_per_day):
        total = round(start_min + i * step)
        times.append(f"{total // 60:02d}:{total % 60:02d}")
    return times


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--posts-per-day", type=int, default=1)
    parser.add_argument("--days-of-week", default="mon,tue,wed,thu,fri", help="Comma-separated: mon,tue,wed,thu,fri,sat,sun")
    parser.add_argument("--post-time", default="09:00", help="HH:MM — used only when --posts-per-day 1")
    parser.add_argument("--day-start", default="08:00", help="HH:MM — first slot when --posts-per-day > 1")
    parser.add_argument("--day-end", default="19:00", help="HH:MM — last slot when --posts-per-day > 1")
    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    posting_days = {DOW_MAP[d.strip().lower()] for d in args.days_of_week.split(",")}
    times = slot_times(args.posts_per_day, args.day_start, args.day_end) if args.posts_per_day > 1 else [args.post_time]

    library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    ordered = interleave_by_category(library)
    dates = next_posting_dates(start, posting_days, args.posts_per_day, len(ordered))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    schedule_rows = []
    manifest_rows = []
    for post, (d, slot) in zip(ordered, dates):
        post_dir = ROOT / "03_generated_posts" / f"{post['post_id']}_{post['slug']}"
        slide_paths = [str(post_dir / f"{post['post_id']}_slide-{n:02d}.png") for n in range(1, 6)]

        schedule_rows.append({
            "scheduled_date": d.isoformat(),
            "day_of_week": DOW_NAMES[d.weekday()],
            "scheduled_time": times[slot],
            "post_id": post["post_id"],
            "topic": post["topic"],
            "category": post["category"],
            "folder": str(post_dir.relative_to(ROOT)),
            "status": "pending",
        })

        hashtags_line = " ".join(post["hashtags"])
        full_caption = f"{post['caption']}\n\n{hashtags_line}"

        manifest_rows.append({
            "post_id": post["post_id"],
            "scheduled_date": d.isoformat(),
            "scheduled_time": times[slot],
            "slide_1": slide_paths[0], "slide_2": slide_paths[1], "slide_3": slide_paths[2],
            "slide_4": slide_paths[3], "slide_5": slide_paths[4],
            "caption": post["caption"],
            "hashtags": hashtags_line,
            "full_caption": full_caption,
            "status": "pending",
        })

        # Ready-to-paste file living right next to the slide images — no CSV needed.
        (post_dir / "caption_full.txt").write_text(full_caption, encoding="utf-8")

    with (OUT_DIR / "posting_schedule.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(schedule_rows[0].keys()))
        writer.writeheader()
        writer.writerows(schedule_rows)

    with (OUT_DIR / "upload_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    span_days = (dates[-1][0] - dates[0][0]).days
    print(f"Scheduled {len(ordered)} posts from {dates[0][0]} to {dates[-1][0]} ({span_days} days, ~{span_days/30:.1f} months)")
    print(f"Cadence: {args.posts_per_day}/day on {args.days_of_week}, times: {', '.join(times)}")
    print(f"Wrote {OUT_DIR / 'posting_schedule.csv'}")
    print(f"Wrote {OUT_DIR / 'upload_manifest.csv'}")


if __name__ == "__main__":
    main()
