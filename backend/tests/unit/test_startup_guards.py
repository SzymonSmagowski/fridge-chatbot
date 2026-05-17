"""Unit tests for `core/startup_guards`.

Pure logic — no DB, no FastAPI, no network. Each test instantiates a fresh
Settings so we don't pollute the test_settings fixture.

Two functions to cover:
- `validate_production_secrets` — refuses to boot in prod with placeholder
  values. No-op in dev.
- `ensure_dev_fernet_key` — auto-generates a Fernet key in dev when missing.
  No-op in prod or when a key is already set.
"""
from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from src.core.settings import Settings
from src.core.startup_guards import (
    PUBLISHED_DEFAULT_SECRET_KEYS,
    ensure_dev_fernet_key,
    validate_production_secrets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prod_safe_settings(**overrides) -> Settings:
    """A Settings instance that would pass validation in prod, with optional
    targeted overrides to break each guard one at a time.
    """
    base = {
        "ENVIRONMENT": "prod",
        "SECRET_KEY": "a-real-prod-secret-" + "x" * 40,
        "FERNET_KEY": Fernet.generate_key().decode(),
        "ALLOWED_ORIGINS": "https://kiosk.example.com,https://app.example.com",
    }
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# validate_production_secrets — dev no-op
# ---------------------------------------------------------------------------


def test_validate_production_secrets_in_dev_is_a_noop_with_placeholder_values() -> None:
    """ENVIRONMENT='dev' (the default for contributors) must NEVER raise,
    even when SECRET_KEY is a placeholder, FERNET_KEY is blank, and CORS
    contains localhost. Otherwise the dev experience breaks on
    `cp .env.example .env`.
    """
    settings = Settings(
        ENVIRONMENT="dev",
        SECRET_KEY="changeme",
        FERNET_KEY="",
        ALLOWED_ORIGINS="http://localhost:3000",
    )
    # Must not raise.
    validate_production_secrets(settings)


# ---------------------------------------------------------------------------
# validate_production_secrets — prod failure modes (one per guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("default_secret", sorted(PUBLISHED_DEFAULT_SECRET_KEYS))
def test_validate_production_secrets_rejects_placeholder_secret_key(
    default_secret: str,
) -> None:
    settings = _prod_safe_settings(SECRET_KEY=default_secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_secrets(settings)


def test_validate_production_secrets_rejects_empty_fernet_key_in_prod() -> None:
    settings = _prod_safe_settings(FERNET_KEY="")
    with pytest.raises(RuntimeError, match="FERNET_KEY"):
        validate_production_secrets(settings)


def test_validate_production_secrets_rejects_localhost_in_allowed_origins() -> None:
    settings = _prod_safe_settings(
        ALLOWED_ORIGINS="https://kiosk.example.com,http://localhost:3000"
    )
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        validate_production_secrets(settings)


def test_validate_production_secrets_rejects_127_in_allowed_origins() -> None:
    settings = _prod_safe_settings(
        ALLOWED_ORIGINS="https://kiosk.example.com,http://127.0.0.1:3000"
    )
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        validate_production_secrets(settings)


# ---------------------------------------------------------------------------
# validate_production_secrets — prod happy path
# ---------------------------------------------------------------------------


def test_validate_production_secrets_in_prod_with_clean_overrides_passes() -> None:
    settings = _prod_safe_settings()
    # Must not raise.
    validate_production_secrets(settings)


def test_validate_production_secrets_in_prod_message_includes_actionable_hint() -> None:
    """A failed boot must tell the operator how to fix it.

    Error message contract: includes the offending env var AND a hint on how
    to generate a new one.
    """
    settings = _prod_safe_settings(SECRET_KEY="changeme")
    with pytest.raises(RuntimeError) as excinfo:
        validate_production_secrets(settings)
    msg = str(excinfo.value)
    assert "SECRET_KEY" in msg
    assert "secrets.token_urlsafe" in msg or "generate" in msg.lower()


# ---------------------------------------------------------------------------
# ensure_dev_fernet_key — auto-generation behavior
# ---------------------------------------------------------------------------


def test_ensure_dev_fernet_key_generates_when_dev_and_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Dev + empty FERNET_KEY → generates a valid Fernet key + logs a warning."""
    settings = Settings(ENVIRONMENT="dev", FERNET_KEY="")
    with caplog.at_level(logging.WARNING):
        ensure_dev_fernet_key(settings)

    # Mutated to a non-empty value.
    assert settings.FERNET_KEY != ""
    # The generated value is a real, usable Fernet key (not just any string).
    Fernet(settings.FERNET_KEY.encode())
    # And we logged a warning so the contributor knows what just happened.
    assert any(
        "FERNET_KEY" in rec.message and "ephemeral" in rec.message
        for rec in caplog.records
    )


def test_ensure_dev_fernet_key_is_noop_when_dev_and_already_set() -> None:
    """Dev + key already provided → leave it alone."""
    existing = Fernet.generate_key().decode()
    settings = Settings(ENVIRONMENT="dev", FERNET_KEY=existing)
    ensure_dev_fernet_key(settings)
    assert settings.FERNET_KEY == existing


def test_ensure_dev_fernet_key_is_noop_in_prod_even_when_missing() -> None:
    """Prod + empty FERNET_KEY → don't auto-generate (production demands an
    explicit operator choice; `validate_production_secrets` raises first).
    """
    settings = Settings(
        ENVIRONMENT="prod",
        SECRET_KEY="a-real-prod-secret-" + "x" * 40,
        FERNET_KEY="",
        ALLOWED_ORIGINS="https://kiosk.example.com",
    )
    ensure_dev_fernet_key(settings)
    assert settings.FERNET_KEY == ""
