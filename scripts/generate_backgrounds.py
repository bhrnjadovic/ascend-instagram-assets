"""Generate brand-coloured geometric backgrounds for each slide type.

No external image-generation API is used for the test batch: backgrounds are built
entirely with Pillow (gradients + thin architectural line motifs), per the brand
decision recorded in 00_brand_assets/brand_rules.md. This keeps the pipeline free,
deterministic, and immune to AI-artefact issues (malformed hands, gibberish text).

If a future batch switches config.yaml's background_mode to "supplied" or "mixed",
swap this module for one that loads externally generated images instead — the
compositor (compose_slides.py) only cares that a same-size background image exists.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

Colour = tuple[int, int, int]


def hex_to_rgb(value: str) -> Colour:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def vertical_gradient(size: tuple[int, int], top: Colour, bottom: Colour) -> Image.Image:
    width, height = size
    base = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(height - 1, 1)
        colour = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=colour)
    return base


def draw_kicker_rule(draw: ImageDraw.ImageDraw, colour: Colour, y: int = 140, x0: int = 90, x1: int = 300) -> None:
    """Single thin editorial rule sitting in the top margin, above the headline and clear of the page number."""
    draw.line([(x0, y), (x1, y)], fill=colour, width=3)


def build_background(
    slide_type: str, colours: dict, size: tuple[int, int] = (1080, 1350), draw_kicker: bool = True
) -> Image.Image:
    navy = hex_to_rgb(colours["navy"])
    navy_mid = hex_to_rgb(colours["navy_mid"])
    gold = hex_to_rgb(colours["gold"])
    off_white = hex_to_rgb(colours["off_white"])

    if slide_type in ("cover", "cta"):
        base = vertical_gradient(size, navy_mid, navy)
        if draw_kicker:
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw_kicker_rule(draw, (*gold, 255))
            base = Image.alpha_composite(base.convert("RGBA"), overlay)
        return base.convert("RGB")

    if slide_type == "benefits":
        base = Image.new("RGB", size, navy)
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw_kicker_rule(draw, (*gold, 255))
        base = Image.alpha_composite(base.convert("RGBA"), overlay)
        return base.convert("RGB")

    # explanation, considerations -> off-white editorial panels
    gold_dark = hex_to_rgb(colours["gold_dark"])
    base = Image.new("RGB", size, off_white)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_kicker_rule(draw, (*gold_dark, 255))
    base = Image.alpha_composite(base.convert("RGBA"), overlay)
    return base.convert("RGB")


def generate_for_post(post_id: str, slug: str, slides: list[dict], colours: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for slide in slides:
        img = build_background(slide["slide_type"], colours)
        path = out_dir / f"{post_id}_slide-{slide['slide_number']:02d}_bg.png"
        img.save(path)
        paths.append(path)
    return paths
