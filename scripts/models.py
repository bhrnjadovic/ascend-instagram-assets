"""Pydantic data models for the carousel content library."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

BANNED_PHRASES = [
    "guaranteed approval",
    "guaranteed funding",
    "everyone qualifies",
    "no credit checks",
    "cheapest rate",
    "best rate",
    "instant money",
    "free money",
    "risk-free",
    "no documents ever required",
]


class Slide(BaseModel):
    slide_number: int = Field(ge=1, le=6)
    slide_type: str
    headline: str = ""
    subheadline: str = ""
    body: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    bullet_icons: list[str] = Field(default_factory=list)
    cta: str = ""
    visual_concept: str = ""
    image_prompt: str = ""

    @field_validator("headline", "subheadline", "body", "cta")
    @classmethod
    def no_banned_phrases(cls, value: str) -> str:
        lowered = value.lower()
        for phrase in BANNED_PHRASES:
            if phrase in lowered:
                raise ValueError(f"Banned phrase found: '{phrase}' in '{value}'")
        return value

    @field_validator("bullet_icons")
    @classmethod
    def icons_match_bullets(cls, value: list[str], info) -> list[str]:
        bullets = info.data.get("bullet_points", [])
        if value and bullets and len(value) != len(bullets):
            raise ValueError(f"bullet_icons ({len(value)}) must match bullet_points ({len(bullets)}) in count")
        return value


class Carousel(BaseModel):
    post_id: str
    slug: str
    topic: str
    category: str
    primary_finance_product: str
    audience: list[str]
    awareness_stage: str
    objective: str
    website_source: str = ""
    cover_has_photo: bool = True
    slides: list[Slide]
    caption: str
    short_caption: str
    hashtags: list[str]
    suggested_hero_image_concept: str = ""
    suggested_icon_set: str = ""
    suggested_filename: str
    compliance_notes: list[str] = Field(default_factory=list)
    image_disclaimer: str

    @field_validator("slides")
    @classmethod
    def exactly_five_or_six_slides(cls, value: list[Slide]) -> list[Slide]:
        if len(value) not in (5, 6):
            raise ValueError("A carousel must have 5 slides (6 only if genuinely required)")
        numbers = [s.slide_number for s in value]
        if numbers != sorted(numbers) or numbers != list(range(1, len(value) + 1)):
            raise ValueError("Slide numbers must be sequential starting at 1")
        return value

    @field_validator("hashtags")
    @classmethod
    def hashtag_count(cls, value: list[str]) -> list[str]:
        if not (8 <= len(value) <= 12):
            raise ValueError(f"Expected 8-12 hashtags, got {len(value)}")
        return value
