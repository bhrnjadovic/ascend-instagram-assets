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
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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


def draw_footer(draw: ImageDraw.ImageDraw, slide_number: int, total: int, on_dark: bool, show_website: bool = True) -> None:
    if show_website:
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
    text_zone_end: int = 545,
    text_fade_end: int = 610,
) -> Image.Image:
    """Scrim over a full-bleed photo, tightened to only where text actually sits —
    strong behind the headline/subheadline (0 to text_zone_end), fading to fully
    transparent by text_fade_end and staying that way for the rest of the frame. No
    tint at all on the bottom half — the photo shows through completely there, and
    the footer website text is dropped on this layout since it would sit directly on
    an untinted photo with no guaranteed contrast (see render_slide's show_website)."""
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        if y <= text_zone_end:
            alpha = top_alpha
        elif y <= text_fade_end:
            t = (y - text_zone_end) / max(text_fade_end - text_zone_end, 1)
            alpha = int(top_alpha * (1 - t))
        else:
            alpha = 0
        draw.line([(0, y), (width, y)], fill=(*colour, alpha))
    return overlay


def _layout_lines(
    draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, xy: tuple[int, int],
    max_width: int, line_spacing: float,
) -> tuple[list[tuple[float, int, str]], int]:
    x, y = xy
    ascent, descent = fnt.getmetrics()
    line_height = int((ascent + descent) * line_spacing)
    placed = []
    for line in wrap_text(draw, text, fnt, max_width):
        placed.append((x, y, line))
        y += line_height
    return placed, y


def draw_embossed_text(
    canvas: Image.Image,
    text: str,
    fnt: ImageFont.FreeTypeFont,
    xy: tuple[int, int],
    max_width: int,
    fill: tuple[int, int, int],
    line_spacing: float = 1.35,
    bevel: bool = True,
    glow_alpha: int = 150,
) -> int:
    """Draws text straight onto the photo with an embossed/lifted look instead of a
    tinted band: a wide soft dark glow for legibility on any photo, a tight drop shadow
    underneath, and (when bevel=True) a light top edge + slightly shaded lower face so
    the letters read as raised. Returns the y after the last line."""
    draw = ImageDraw.Draw(canvas)
    placed, end_y = _layout_lines(draw, text, fnt, xy, max_width, line_spacing)
    if not placed:
        return end_y

    mask = Image.new("L", canvas.size, 0)
    mdraw = ImageDraw.Draw(mask)
    for x, y, line in placed:
        mdraw.text((x, y), line, font=fnt, fill=255)

    def _layer(colour: tuple[int, int, int], alpha_mask: Image.Image) -> Image.Image:
        layer = Image.new("RGBA", canvas.size, (*colour, 0))
        layer.putalpha(alpha_mask)
        return layer

    shadow_rgb = (6, 12, 22)
    size = fnt.size

    # 1. Wide soft glow — gives contrast on light photos without a visible band.
    glow = mask.filter(ImageFilter.GaussianBlur(max(10, size // 4)))
    glow = glow.point(lambda v: min(255, int(v * glow_alpha / 255 * 1.6)))
    canvas.alpha_composite(_layer(shadow_rgb, glow))

    # 2. Tight drop shadow, offset down-right.
    off = max(2, size // 28)
    drop = ImageChops.offset(mask, off, off + 1).filter(ImageFilter.GaussianBlur(max(1.5, size / 40)))
    drop = drop.point(lambda v: int(v * 0.85))
    canvas.alpha_composite(_layer(shadow_rgb, drop))

    # 3. Letter face: vertical light-to-slightly-shaded gradient per line.
    face = Image.new("RGBA", canvas.size, (*fill, 0))
    if bevel:
        ascent, descent = fnt.getmetrics()
        fdraw = ImageDraw.Draw(face)
        dark = tuple(int(c * 0.80) for c in fill)
        for _x, y, _line in placed:
            top, bottom = y, y + ascent + descent
            for yy in range(top, bottom):
                t = (yy - top) / max(bottom - top - 1, 1)
                t = max(0.0, (t - 0.35) / 0.65)  # top 35% stays full brightness
                c = tuple(int(fill[i] + (dark[i] - fill[i]) * t) for i in range(3))
                fdraw.line([(0, yy), (canvas.size[0], yy)], fill=(*c, 0))
    face.putalpha(mask)
    canvas.alpha_composite(face)

    if bevel:
        # 4. Bevel: bright hairline on upper edges, darker hairline on lower edges.
        up = ImageChops.offset(mask, 0, 2)
        top_edge = ImageChops.subtract(mask, up).filter(ImageFilter.GaussianBlur(0.6))
        canvas.alpha_composite(_layer((255, 255, 255), top_edge.point(lambda v: int(v * 0.75))))
        down = ImageChops.offset(mask, 0, -2)
        bottom_edge = ImageChops.subtract(mask, down).filter(ImageFilter.GaussianBlur(0.6))
        canvas.alpha_composite(_layer((70, 74, 82), bottom_edge.point(lambda v: int(v * 0.55))))

    return end_y


def build_cover_photo_background(post: dict, slide: dict) -> Image.Image:
    """Full-bleed AI photo with NO tinted band over it. Legibility now comes from the
    embossed text treatment (glow + drop shadow + bevel) drawn in render_slide, so the
    photo shows through across the whole frame."""
    from image_api import get_cover_background  # deferred: avoids requiring requests/network unless used

    gold = hex_to_rgb(COLOURS["gold"])

    bg_path = get_cover_background(post["post_id"], slide["image_prompt"])
    photo = _cover_fit(Image.open(bg_path).convert("RGB"), CANVAS)
    canvas = photo.convert("RGBA")

    # Kicker rule with a faint shadow so it holds on light photos too.
    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    draw_kicker_rule(ImageDraw.Draw(shadow), (6, 12, 22, 200), y=142, x0=91, x1=301)
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(2)))
    draw_kicker_rule(ImageDraw.Draw(canvas), (*gold, 255))
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

        if slide["slide_number"] != 1:
            paste_logo(canvas, on_dark)
        draw_footer(draw, slide["slide_number"], len(post["slides"]), on_dark)
        canvas.convert("RGB").save(out_path, "PNG")
        return

    y = MARGIN + 70
    heading_font = font("heading_bold", 74 if use_photo_cover else 64) if slide["slide_type"] in ("cover",) else font("heading", 50)
    body_font = font("body", 34)
    bullet_font = font("body_medium", 34)

    headline = slide.get("headline", "")
    subheadline = slide.get("subheadline", "")
    if use_photo_cover:
        # Embossed off-white headline + gold subheadline straight on the photo.
        if headline:
            y = draw_embossed_text(canvas, headline, heading_font, (MARGIN, y), content_width,
                                   hex_to_rgb(COLOURS["off_white"]), line_spacing=1.22)
            y += 34
        if subheadline:
            y = draw_embossed_text(canvas, subheadline, font("body_medium", 36), (MARGIN, y), content_width,
                                   hex_to_rgb(COLOURS["gold_light"]), bevel=False, glow_alpha=170)
            y += 20
        # Shadow behind the "1/5" counter so it holds on bright skies/windows;
        # draw_footer() then draws the same gold label exactly on top of it.
        page_label = f"{slide['slide_number']}/{len(post['slides'])}"
        page_font = font("body_semibold", 28)
        lx = CANVAS[0] - MARGIN - draw.textlength(page_label, font=page_font)
        draw_embossed_text(canvas, page_label, page_font, (int(lx), MARGIN - 10), CANVAS[0],
                           gold, bevel=False, glow_alpha=200)
        headline = subheadline = ""
        draw = ImageDraw.Draw(canvas)

    if headline:
        y = draw_multiline(draw, headline, heading_font, (MARGIN, y), content_width, text_colour, align="left")
        y += 20

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
            disc_font = font("body_light", 20)
            dy = CANVAS[1] - FOOTER_H - 40
            draw_multiline(draw, disclaimer, disc_font, (MARGIN, dy), content_width, hex_to_rgb(COLOURS["steel"]))

    if slide["slide_number"] != 1:
        paste_logo(canvas, on_dark)
    draw_footer(draw, slide["slide_number"], len(post["slides"]), on_dark, show_website=not use_photo_cover)

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
