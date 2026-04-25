"""Unit tests for src/core/labels.py — pure slug normalization + reserved set.

Unit-level because there's no DB, no Redis, and the logic is deterministic.
"""
from __future__ import annotations

from src.core.labels import (
    RESERVED_DISPLAY_NAMES,
    RESERVED_SLUGS,
    display_name_for_slug,
    is_reserved,
    normalize_slug,
)


def test_normalize_slug_lowercases_and_kebabifies() -> None:
    assert normalize_slug("Shopping List") == "shopping-list"


def test_normalize_slug_strips_non_alphanumeric() -> None:
    assert normalize_slug("Pets & Plants!") == "pets-plants"


def test_normalize_slug_trims_leading_and_trailing_dashes() -> None:
    assert normalize_slug("  --hello--  ") == "hello"


def test_normalize_slug_empty_input_returns_empty() -> None:
    assert normalize_slug("") == ""


def test_normalize_slug_is_idempotent_for_already_valid_slug() -> None:
    assert normalize_slug("shopping-list") == "shopping-list"


def test_is_reserved_returns_true_for_known_reserved_slug() -> None:
    assert is_reserved("shopping-list") is True


def test_is_reserved_returns_false_for_user_slug() -> None:
    assert is_reserved("random-slug") is False


def test_display_name_for_slug_returns_curated_for_reserved() -> None:
    assert display_name_for_slug("shopping-list") == "Shopping list"


def test_display_name_for_slug_title_cases_user_slug() -> None:
    assert display_name_for_slug("pets-plants") == "Pets Plants"


def test_reserved_set_contains_shopping_list() -> None:
    assert "shopping-list" in RESERVED_SLUGS
    assert "Shopping list" == RESERVED_DISPLAY_NAMES["shopping-list"]
