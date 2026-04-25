"""Reserved label slugs and slug-normalization helper.

Reserved slugs are seeded by the pairing transaction (D9) and protected from
deletion (`LabelService.delete` raises `LabelReservedError`). The chat assistant
uses these slugs as stable handles regardless of the user-facing display name.
"""
import re

RESERVED_SLUGS: frozenset[str] = frozenset({"shopping-list"})

RESERVED_DISPLAY_NAMES: dict[str, str] = {
    "shopping-list": "Shopping list",
}


_SLUG_INVALID = re.compile(r"[^a-z0-9]+")


def normalize_slug(raw: str) -> str:
    """Lowercase, ASCII-fold, kebab-case. Empty input returns empty string."""
    if not raw:
        return ""
    s = raw.strip().lower()
    s = _SLUG_INVALID.sub("-", s)
    return s.strip("-")


def is_reserved(slug: str) -> bool:
    return slug in RESERVED_SLUGS


def display_name_for_slug(slug: str) -> str:
    """Title-case slug for use as auto-created `labels.display_name`."""
    if slug in RESERVED_DISPLAY_NAMES:
        return RESERVED_DISPLAY_NAMES[slug]
    return slug.replace("-", " ").strip().title() or slug
