"""Automated QA over generated slide PNGs. Writes 04_quality_control/qa_report.csv
and copies passing slides into 04_quality_control/approved/<post_id>/, failing
slides into 04_quality_control/rejected/<post_id>/.

Usage:
    python scripts/quality_check.py --all
    python scripts/quality_check.py --post ALP-001
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from PIL import Image

from models import BANNED_PHRASES

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = json.loads((ROOT / "01_content" / "carousel_library.json").read_text(encoding="utf-8"))
POSTS_DIR = ROOT / "03_generated_posts"
QA_DIR = ROOT / "04_quality_control"
EXPECTED_SIZE = (1080, 1350)
REQUIRED_FILES = ["caption.txt", "post.json", "preview.jpg"]


def check_dimensions(path: Path) -> tuple[bool, str]:
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            if img.size != EXPECTED_SIZE:
                return False, f"Wrong size {img.size}, expected {EXPECTED_SIZE}"
            if img.format != "PNG":
                return False, f"Wrong format {img.format}, expected PNG"
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, f"Corrupted or unreadable image: {exc}"


def check_footer_present(path: Path) -> tuple[bool, str]:
    """Heuristic: the footer band (bottom 140px) must not be a flat, untouched background."""
    with Image.open(path) as img:
        width, height = img.size
        footer = img.crop((0, height - 140, width, height)).convert("L")
        extrema = footer.getextrema()
        if extrema[1] - extrema[0] < 15:
            return False, "Footer band shows no logo/text variation (possible render failure)"
    return True, ""


def check_text_compliance(carousel: dict) -> tuple[bool, str]:
    haystack = " ".join(
        [carousel.get("caption", ""), carousel.get("short_caption", "")]
        + [
            " ".join([s.get("headline", ""), s.get("subheadline", ""), s.get("body", ""), s.get("cta", "")] + s.get("bullet_points", []))
            for s in carousel["slides"]
        ]
    ).lower()
    for phrase in BANNED_PHRASES:
        if phrase in haystack:
            return False, f"Banned phrase present: '{phrase}'"
    return True, ""


def check_disclaimer(carousel: dict) -> tuple[bool, str]:
    if not carousel.get("image_disclaimer", "").strip():
        return False, "Missing image_disclaimer"
    cta_slides = [s for s in carousel["slides"] if s["slide_type"] == "cta"]
    if not cta_slides:
        return False, "No CTA slide found"
    return True, ""


def check_slide_count(post_dir: Path, carousel: dict) -> tuple[bool, str]:
    expected = len(carousel["slides"])
    found = sorted(post_dir.glob(f"{carousel['post_id']}_slide-*.png"))
    if len(found) != expected:
        return False, f"Expected {expected} slide PNGs, found {len(found)}"
    return True, ""


def check_no_duplicates(post_dir: Path, carousel: dict) -> tuple[bool, str]:
    hashes = {}
    for slide in carousel["slides"]:
        path = post_dir / f"{carousel['post_id']}_slide-{slide['slide_number']:02d}.png"
        if not path.exists():
            continue
        with open(path, "rb") as f:
            h = hash(f.read())
        if h in hashes:
            return False, f"Slide {slide['slide_number']} duplicates slide {hashes[h]}"
        hashes[h] = slide["slide_number"]
    return True, ""


def run_qa(carousels: list[dict]) -> list[dict]:
    rows = []
    for carousel in carousels:
        post_dir = POSTS_DIR / f"{carousel['post_id']}_{carousel['slug']}"
        slide_count_pass, slide_count_msg = check_slide_count(post_dir, carousel)
        dup_pass, dup_msg = check_no_duplicates(post_dir, carousel)
        text_pass, text_msg = check_text_compliance(carousel)
        disclaimer_pass, disclaimer_msg = check_disclaimer(carousel)

        missing_support = [f for f in REQUIRED_FILES if not (post_dir / f).exists()]

        for slide in carousel["slides"]:
            filename = f"{carousel['post_id']}_slide-{slide['slide_number']:02d}.png"
            path = post_dir / filename
            reasons = []

            if not path.exists():
                rows.append({
                    "post_id": carousel["post_id"], "slide_number": slide["slide_number"],
                    "filename": filename, "dimensions_pass": False, "text_pass": text_pass,
                    "branding_pass": False, "compliance_pass": disclaimer_pass and text_pass,
                    "visual_pass": False, "overall_status": "REJECTED",
                    "rejection_reason": "File not found", "regeneration_count": 0,
                })
                continue

            dim_pass, dim_msg = check_dimensions(path)
            branding_pass, branding_msg = check_footer_present(path) if dim_pass else (False, "Skipped (bad dimensions)")
            if not dim_pass:
                reasons.append(dim_msg)
            if not branding_pass:
                reasons.append(branding_msg)
            if not slide_count_pass:
                reasons.append(slide_count_msg)
            if not dup_pass:
                reasons.append(dup_msg)
            if not text_pass:
                reasons.append(text_msg)
            if not disclaimer_pass and slide["slide_type"] == "cta":
                reasons.append(disclaimer_msg)
            if missing_support:
                reasons.append(f"Missing supporting file(s): {', '.join(missing_support)}")

            compliance_pass = text_pass and (disclaimer_pass if slide["slide_type"] == "cta" else True)
            visual_pass = dim_pass
            overall_pass = dim_pass and branding_pass and slide_count_pass and dup_pass and compliance_pass and not missing_support

            rows.append({
                "post_id": carousel["post_id"], "slide_number": slide["slide_number"],
                "filename": filename, "dimensions_pass": dim_pass, "text_pass": text_pass,
                "branding_pass": branding_pass, "compliance_pass": compliance_pass,
                "visual_pass": visual_pass,
                "overall_status": "APPROVED" if overall_pass else "REJECTED",
                "rejection_reason": "; ".join(reasons), "regeneration_count": 0,
            })
    return rows


def sort_into_folders(rows: list[dict]) -> None:
    for status, subdir in (("APPROVED", "approved"), ("REJECTED", "rejected")):
        for row in rows:
            if row["overall_status"] != status:
                continue
            post_id = row["post_id"]
            carousel = next(c for c in LIBRARY if c["post_id"] == post_id)
            src = POSTS_DIR / f"{post_id}_{carousel['slug']}" / row["filename"]
            if not src.exists():
                continue
            dest_dir = QA_DIR / subdir / post_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / row["filename"])


def write_report(rows: list[dict]) -> None:
    path = QA_DIR / "qa_report.csv"
    fieldnames = [
        "post_id", "slide_number", "filename", "dimensions_pass", "text_pass",
        "branding_pass", "compliance_pass", "visual_pass", "overall_status",
        "rejection_reason", "regeneration_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    carousels = [c for c in LIBRARY if c["post_id"] == args.post] if args.post else LIBRARY
    rows = run_qa(carousels)
    write_report(rows)
    sort_into_folders(rows)

    approved = sum(1 for r in rows if r["overall_status"] == "APPROVED")
    rejected = sum(1 for r in rows if r["overall_status"] == "REJECTED")
    print(f"{approved} approved, {rejected} rejected out of {len(rows)} slides")


if __name__ == "__main__":
    main()
