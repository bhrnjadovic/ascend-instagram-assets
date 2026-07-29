"""Compose final Instagram slide PNGs: background + headline/body/bullets + logo + footer.

Usage:
    python scripts/compose_slides.py --post ALP-001
    python scripts/compose_slides.py --all
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

from generate_backgrounds import build_background, draw_kicker_rule, hex_to_rgb
from icons import paste_icon

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
LIBRARY = json.loads((ROOT / "01_content" / "carousel_library.json").read_text(encoding="utf-8"))

CANVAS = (CONFIG["canvas"]["width"], CONFIG["canvas"]["height"])
MARGIN = CONFIG["canvas"]["margin"]
FOOTER_H = CONFIG["canvas"]["footer_height"]
COLOURS = CONFIG["colours"]
FONTS_DIR = ROOT / CONFIG["fonts"]["dir"]
LOGO_PATH = ROOT / CONFIG["logo"]["path"]
LOGO_MAX_W = CONFIG["logo"]["max_width_px"]
LOGO_PATH_LIGHT = ROOT / CONFIG["logo"]["path_light"]
LOGO_MAX_W_LIGHT = CONFIG["logo"]["max_width_px_light"]


def font(name_key: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / CONFIG["fonts"][name_key]), size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    xy: tuple[int, int],
    max_width: int,
    fill: tuple,
    line_spacing: float = 1.35,
    align: str = "left",
) -> int:
    """Draws wrapped text, returns the y-coordinate after the last line."""
    x, y = xy
    lines = wrap_text(draw, text, fnt, max_width)
    ascent, descent = fnt.getmetrics()
    line_height = int((ascent + descent) * line_spacing)
    for line in lines:
        line_x = x
        if align == "center":
            w = draw.textlength(line, font=fnt)
            line_x = x + (max_width - w) / 2
        draw.text((line_x, y), line, font=fnt, fill=fill)
        y += line_height
    return y


def text_block_height(
    draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int, line_spacing: float = 1.35
) -> int:
    """Height a draw_multiline() call would take, without actually drawing — used to
    vertically centre a text block before committing to a y position."""
    if not text:
        return 0
    lines = wrap_text(draw, text, fnt, max_width)
    ascent, descent = fnt.getmetrics()
    return len(lines) * int((ascent + descent) * line_spacing)


def paste_logo(canvas: Image.Image, on_dark: bool) -> None:
    path, max_w = (LOGO_PATH, LOGO_MAX_W) if on_dark else (LOGO_PATH_LIGHT, LOGO_MAX_W_LIGHT)
    logo = Image.open(path).convert("RGBA")
    ratio = max_w / logo.width
    logo = logo.resize((max_w, int(logo.height * ratio)))
    x = (CANVAS[0] - logo.width) // 2
    y = CANVAS[1] - FOOTER_H + 10
    canvas.paste(logo, (x, y), logo)


def draw_footer(draw: ImageDraw.ImageDraw, slide_number: int, total: int, on_dark: bool) -> None:
    text_colour = hex_to_rgb(COLOURS["off_white"]) if on_dark else hex_to_rgb(COLOURS["charcoal"])
    small = font("body", 26)
    website = "ascendlendingpartners.com.au"
    y = CANVAS[1] - 46
    w = draw.textlength(website, font=small)
    draw.text(((CANVAS[0] - w) / 2, y), website, font=small, fill=text_colour)

    page_label = f"{slide_number}/{total}"
    page_font = font("body_semibold", 28)
    gold = hex_to_rgb(COLOURS["gold"])
    draw.text((CANVAS[0] - MARGIN - draw.textlength(page_label, font=page_font), MARGIN - 10), page_label, font=page_font, fill=gold)


def _cover_fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resizes to fully cover `size` (may overflow one axis), then centre-crops to it."""
    target_w, target_h = size
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(src_w * scale) + 1, int(src_h * scale) + 1
    img = img.resize((new_w, new_h))
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def build_photo_scrim(
    size: tuple[int, int],
    colour: tuple[int, int, int],
    top_alpha: int = 200,
    mid_alpha: int = 60,
    bottom_alpha: int = 215,
    text_zone_end: int = 480,
    mid_y: int = 760,
) -> Image.Image:
    """Vertical navy scrim over a full-bleed photo. Three zones: held flat and strong
    through the headline/subheadline text (0 to text_zone_end), fading down to let the
    photo read clearly in the middle, then rising again behind the logo/footer. A simple
    two-point fade left the subheadline dipping in legibility wherever it crossed a
    bright part of the photo — holding the top alpha flat through the full text zone
    fixes that regardless of what's in any given photo."""
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        if y <= text_zone_end:
            alpha = top_alpha
        elif y <= mid_y:
            t = (y - text_zone_end) / max(mid_y - text_zone_end, 1)
            alpha = int(top_alpha + (mid_alpha - top_alpha) * t)
        else:
            t = (y - mid_y) / max(height - mid_y - 1, 1)
            alpha = int(mid_alpha + (bottom_alpha - mid_alpha) * t)
        draw.line([(0, y), (width, y)], fill=(*colour, alpha))
    return overlay


def build_cover_photo_background(post: dict, slide: dict) -> Image.Image:
    """Full-bleed AI photo with a light off-white scrim gradient (navy text on top),
    rather than a dark navy scrim with white text. A dark scrim made photo covers read
    almost as dark-navy as the flat covers, defeating the point of alternating them —
    the light scrim gives the grid genuine light/dark contrast between the two styles."""
    from image_api import get_cover_background  # deferred: avoids requiring requests/network unless used

    off_white = hex_to_rgb(COLOURS["off_white"])
    gold_dark = hex_to_rgb(COLOURS["gold_dark"])

    bg_path = get_cover_background(post["post_id"], slide["image_prompt"])
    photo = _cover_fit(Image.open(bg_path).convert("RGB"), CANVAS)
    canvas = photo.convert("RGBA")
    canvas = Image.alpha_composite(canvas, build_photo_scrim(CANVAS, off_white))

    draw = ImageDraw.Draw(canvas)
    draw_kicker_rule(draw, (*gold_dark, 255))
    return canvas.convert("RGB")


def render_slide(post: dict, slide: dict, out_path: Path) -> None:
    use_photo_cover = (
        slide["slide_type"] == "cover"
        and CONFIG["background_mode"] in ("mixed", "supplied")
        and post.get("cover_has_photo", True)
    )
    is_flat_cover = slide["slide_type"] == "cover" and not use_photo_cover
    # Photo covers get the light/navy-text treatment (see build_cover_photo_background);
    # flat covers and every other slide type keep their existing dark/light logic.
    on_dark = slide["slide_type"] in ("cta", "benefits") or is_flat_cover

    if use_photo_cover:
        bg = build_cover_photo_background(post, slide)
    else:
        bg = build_background(slide["slide_type"], COLOURS, CANVAS, draw_kicker=not is_flat_cover)
    canvas = bg.convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    text_colour = hex_to_rgb(COLOURS["off_white"]) if on_dark else hex_to_rgb(COLOURS["navy"])
    body_colour = hex_to_rgb(COLOURS["light_grey"]) if on_dark else hex_to_rgb(COLOURS["charcoal"])
    gold = hex_to_rgb(COLOURS["gold"])
    content_width = CANVAS[0] - 2 * MARGIN

    if is_flat_cover:
        # Larger, vertically + horizontally centred headline/subheadline — distinct
        # rhythm from the photo covers, per feedback that left-aligned/top-anchored
        # text felt cramped with no photo to fill the rest of the frame.
        headline = slide.get("headline", "")
        subheadline = slide.get("subheadline", "")
        h_font = font("heading_bold", 92)
        s_font = font("body", 40)
        gap = 26

        h_height = text_block_height(draw, headline, h_font, content_width)
        s_height = text_block_height(draw, subheadline, s_font, content_width)
        total_height = h_height + (gap + s_height if subheadline else 0)

        top_bound = MARGIN + 60
        bottom_bound = CANVAS[1] - FOOTER_H - 60
        start_y = top_bound + max(0, (bottom_bound - top_bound - total_height) // 2)

        rule_w = 220
        rule_y = start_y - 46
        draw.line(
            [(CANVAS[0] // 2 - rule_w // 2, rule_y), (CANVAS[0] // 2 + rule_w // 2, rule_y)],
            fill=(*gold, 255), width=3,
        )

        y = draw_multiline(draw, headline, h_font, (MARGIN, start_y), content_width, text_colour, align="center")
        if subheadline:
            draw_multiline(draw, subheadline, s_font, (MARGIN, y + gap), content_width, gold, align="center")

        paste_logo(canvas, on_dark)
        draw_footer(draw, slide["slide_number"], len(post["slides"]), on_dark)
        canvas.convert("RGB").save(out_path, "PNG")
        return

    y = MARGIN + 70
    heading_font = font("heading_bold", 64) if slide["slide_type"] in ("cover",) else font("heading", 50)
    body_font = font("body", 34)
    bullet_font = font("body_medium", 34)

    headline = slide.get("headline", "")
    if headline:
        y = draw_multiline(draw, headline, heading_font, (MARGIN, y), content_width, text_colour, align="left")
        y += 20

    subheadline = slide.get("subheadline", "")
    if subheadline:
        y = draw_multiline(draw, subheadline, font("body", 36), (MARGIN, y), content_width, gold if on_dark else hex_to_rgb(COLOURS["gold_dark"]))
        y += 20

    body = slide.get("body", "")
    if body:
        y = draw_multiline(draw, body, body_font, (MARGIN, y + 10), content_width, body_colour)

    bullets = slide.get("bullet_points", [])
    bullet_icons = slide.get("bullet_icons", [])
    if bullets:
        icon_colour = gold if on_dark else hex_to_rgb(COLOURS["gold_dark"])
        bullet_text_x = MARGIN + 90
        bullet_max_width = CANVAS[0] - MARGIN - bullet_text_x
        ascent, descent = bullet_font.getmetrics()
        bullet_line_height = int((ascent + descent) * 1.25)
        by = 480
        for i, point in enumerate(bullets):
            if bullet_icons:
                paste_icon(canvas, bullet_icons[i], (MARGIN, by + 10), 52, icon_colour)
            lines = wrap_text(draw, point, bullet_font, bullet_max_width)
            text_y = by - 8
            for line in lines:
                draw.text((bullet_text_x, text_y), line, font=bullet_font, fill=body_colour)
                text_y += bullet_line_height
            extra_lines = max(0, len(lines) - 1)
            by += 130 + extra_lines * bullet_line_height
        bullets_bottom = by - 130 + bullet_line_height
        if bullets_bottom > CANVAS[1] - FOOTER_H - 40:
            print(f"WARNING: {out_path.name}: bullet text may overlap footer (bottom={bullets_bottom}px)")

    cta = slide.get("cta", "")
    if cta:
        cta_font = font("heading", 38)
        cy = CANVAS[1] - FOOTER_H - 220
        draw_multiline(draw, cta.upper(), cta_font, (MARGIN, cy), content_width, gold, align="left")

    if slide["slide_type"] == "cta":
        disclaimer = post.get("image_disclaimer", "")
        if disclaimer:
            disc_font = font("body_light", 22)
            dy = CANVAS[1] - FOOTER_H - 40
            draw_multiline(draw, disclaimer, disc_font, (MARGIN, dy), content_width, hex_to_rgb(COLOURS["steel"]))

    paste_logo(canvas, on_dark)
    draw_footer(draw, slide["slide_number"], len(post["slides"]), on_dark)

    canvas.convert("RGB").save(out_path, "PNG")


def render_post(post: dict) -> list[Path]:
    out_dir = ROOT / CONFIG["output"]["posts_dir"] / f"{post['post_id']}_{post['slug']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for slide in post["slides"]:
        path = out_dir / f"{post['post_id']}_slide-{slide['slide_number']:02d}.png"
        render_slide(post, slide, path)
        written.append(path)

    (out_dir / "caption.txt").write_text(post["caption"], encoding="utf-8")
    (out_dir / "post.json").write_text(json.dumps(post, indent=2), encoding="utf-8")

    preview = build_preview_sheet(written)
    preview_path = out_dir / "preview.jpg"
    preview.save(preview_path, "JPEG", quality=88)
    written.append(preview_path)

    return written


def build_preview_sheet(slide_paths: list[Path]) -> Image.Image:
    """Review-only contact sheet. Never a substitute for the individual PNGs."""
    thumb_w = 300
    imgs = [Image.open(p) for p in slide_paths]
    thumb_h = int(thumb_w * CANVAS[1] / CANVAS[0])
    thumbs = [im.resize((thumb_w, thumb_h)) for im in imgs]
    sheet = Image.new("RGB", (thumb_w * len(thumbs), thumb_h), (255, 255, 255))
    for i, t in enumerate(thumbs):
        sheet.paste(t, (i * thumb_w, 0))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", help="Single post_id, e.g. ALP-001")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.post:
        posts = [p for p in LIBRARY if p["post_id"] == args.post]
    elif args.all:
        posts = LIBRARY
    else:
        parser.error("Specify --post ALP-001 or --all")

    for post in posts:
        written = render_post(post)
        print(f"{post['post_id']}: wrote {len(written)} files to {written[0].parent}")


if __name__ == "__main__":
    main()
