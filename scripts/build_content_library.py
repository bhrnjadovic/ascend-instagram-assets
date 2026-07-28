"""Validate carousel_library.json and export CSV companion files.

Usage:
    python scripts/build_content_library.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from models import Carousel

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "01_content"
LIBRARY_JSON = CONTENT_DIR / "carousel_library.json"


def load_carousels() -> list[Carousel]:
    raw = json.loads(LIBRARY_JSON.read_text(encoding="utf-8"))
    carousels: list[Carousel] = []
    errors: list[str] = []
    for record in raw:
        try:
            carousels.append(Carousel.model_validate(record))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{record.get('post_id', '?')}: {exc}")
    if errors:
        for err in errors:
            print(f"VALIDATION ERROR: {err}", file=sys.stderr)
        raise SystemExit(1)
    return carousels


def write_library_csv(carousels: list[Carousel]) -> None:
    path = CONTENT_DIR / "carousel_library.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "post_id", "slug", "topic", "category", "primary_finance_product",
            "audience", "awareness_stage", "objective", "website_source",
            "suggested_filename", "image_disclaimer",
        ])
        for c in carousels:
            writer.writerow([
                c.post_id, c.slug, c.topic, c.category, c.primary_finance_product,
                "; ".join(c.audience), c.awareness_stage, c.objective, c.website_source,
                c.suggested_filename, c.image_disclaimer,
            ])
    print(f"Wrote {path}")


def write_captions_csv(carousels: list[Carousel]) -> None:
    path = CONTENT_DIR / "captions.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["post_id", "caption", "short_caption"])
        for c in carousels:
            writer.writerow([c.post_id, c.caption, c.short_caption])
    print(f"Wrote {path}")


def write_hashtags_csv(carousels: list[Carousel]) -> None:
    path = CONTENT_DIR / "hashtags.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["post_id", "hashtags"])
        for c in carousels:
            writer.writerow([c.post_id, " ".join(c.hashtags)])
    print(f"Wrote {path}")


def write_slide_prompts(carousels: list[Carousel]) -> None:
    prompts_dir = ROOT / "02_prompts" / "individual_slide_prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for c in carousels:
        for s in c.slides:
            fname = f"{c.post_id}_slide-{s.slide_number:02d}.txt"
            (prompts_dir / fname).write_text(s.image_prompt, encoding="utf-8")
    print(f"Wrote per-slide prompts to {prompts_dir}")


def main() -> None:
    carousels = load_carousels()
    print(f"Validated {len(carousels)} carousel(s): {[c.post_id for c in carousels]}")
    write_library_csv(carousels)
    write_captions_csv(carousels)
    write_hashtags_csv(carousels)
    write_slide_prompts(carousels)


if __name__ == "__main__":
    main()
