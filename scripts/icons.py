"""Render Material Symbols Outlined glyphs as icon images (no image-gen API needed).

Font: Google Material Symbols Outlined, Apache 2.0 licence, no attribution required.
Codepoint map: 00_brand_assets/icons/icon_map.json (curated subset, cash/piggy-bank
glyphs deliberately excluded per brand_rules.md).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_PATH = ROOT / "00_brand_assets" / "fonts" / "MaterialSymbolsOutlined.ttf"
ICON_MAP = json.loads((ROOT / "00_brand_assets" / "icons" / "icon_map.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    font.set_variation_by_axes([0, 0, 48, weight])  # FILL, GRAD, opsz, wght
    return font


def render_icon(name: str, size: int, colour: tuple[int, int, int], weight: int = 400) -> Image.Image:
    """Returns an RGBA image of the requested icon, tightly cropped to its glyph bounds."""
    if name not in ICON_MAP:
        raise KeyError(f"Unknown icon '{name}'. Add it to 00_brand_assets/icons/icon_map.json")
    char = chr(int(ICON_MAP[name], 16))
    font = _font(size, weight)

    canvas = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((size // 2, size // 2), char, font=font, fill=(*colour, 255))

    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    return canvas


def paste_icon(base: Image.Image, name: str, xy: tuple[int, int], size: int, colour: tuple[int, int, int], weight: int = 400) -> None:
    """Pastes an icon so its glyph is vertically centred on xy (left edge, vertical centre)."""
    icon = render_icon(name, size, colour, weight)
    x, y_centre = xy
    base.paste(icon, (x, y_centre - icon.height // 2), icon)
