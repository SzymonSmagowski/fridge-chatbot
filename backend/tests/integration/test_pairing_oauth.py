"""Integration tests for /pairing and /oauth/google/* (§5.1, §4.1).

Google OAuth is mocked at the service layer (`GoogleOAuthService`) so no
network IO. Token exchange returns canned tokens; revoke is a no-op.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.core import dependencies as deps
from src.models import (
    Device,
    Family,
    FamilyPreferences,
    GoogleToken,
    GoogleTokenStatus,
    Label,
    Member,
    Note,
)


class _StubOAuthService:
    """Drop-in for GoogleOAuthService used in tests."""

    def __init__(self, *, refresh_token: str = "rt-123") -> None:
        self.refresh_token = refresh_token

    def build_authorize_url(self, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        return {
            "access_token": "at-xyz",
            "refresh_token": self.refresh_token,
            "scope": "openid email https://www.googleapis.com/auth/calendar",
            "expires_in": 3600,
            "google_sub": "google-sub-123",
            "google_email": "ola@example.com",
            "google_name": "Ola",
            "google_given_name": "Ola",
        }

    async def revoke(self, token: str) -> bool:
        return True


@pytest.fixture
def oauth_stub(app):
    """Override the GoogleOAuthService dependency with our stub."""
    stub = _StubOAuthService()
    app.dependency_overrides[deps.get_google_oauth_service] = lambda: stub
    yield stub


# ---------------------------------------------------------------------------
# /pairing/start
# ---------------------------------------------------------------------------


def test_pairing_start_returns_authorize_url_and_pairing_id(
    client: TestClient, oauth_stub
) -> None:
    resp = client.post("/api/pairing/start", json={"device_label": "Kitchen"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["pairing_id"]
    assert body["authorize_url"].startswith("https://accounts.google.com/")
    assert "state=pair:" in body["authorize_url"]


# ---------------------------------------------------------------------------
# /oauth/google/callback (kind=pair) — full bootstrap
# ---------------------------------------------------------------------------


def test_pair_callback_creates_family_device_member_and_sets_token(
    client: TestClient, db, oauth_stub
) -> None:
    """D9: pairing transaction seeds family + family_preferences + device +
    first member + reserved labels + auto shopping-list note + Google token."""
    start = client.post("/api/pairing/start", json={"device_label": "Kitchen"}).json()
    pairing_id = start["pairing_id"]

    resp = client.get(
        "/oauth/google/callback",
        params={"code": "fake-code", "state": f"pair:{pairing_id}"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # A1: callback now redirects to /pair/complete?token=<jwt> (architecture §5.1).
    # The cookie path was removed — the SPA grabs the token from the query string
    # and persists it to localStorage itself.
    assert resp.headers["location"].startswith("/pair/complete?token=")
    assert "fridge_device_token" not in resp.cookies

    family = db.query(Family).first()
    assert family is not None
    assert family.name == "Ola's Family"

    prefs = db.query(FamilyPreferences).filter(
        FamilyPreferences.family_id == family.id
    ).first()
    assert prefs.auto_create_shopping_list is True

    device = db.query(Device).filter(Device.family_id == family.id).first()
    assert device is not None

    member = db.query(Member).filter(Member.family_id == family.id).first()
    assert member.name == "Ola"
    assert member.is_setup_owner is True
    assert member.color == "sage"

    token = db.query(GoogleToken).filter(GoogleToken.member_id == member.id).first()
    assert token is not None
    assert token.status == GoogleTokenStatus.connected
    assert token.refresh_token_encrypted  # Fernet ciphertext

    # Reserved labels seeded.
    labels = db.query(Label).filter(Label.family_id == family.id).all()
    slugs = {label.slug for label in labels}
    assert "shopping-list" in slugs

    # Auto-created shopping-list note (per D9).
    notes = db.query(Note).filter(Note.family_id == family.id).all()
    assert len(notes) == 1
    assert notes[0].pinned is True


def test_pair_callback_with_unknown_state_returns_400(
    client: TestClient, oauth_stub
) -> None:
    resp = client.get(
        "/oauth/google/callback",
        params={"code": "fake", "state": "pair:does-not-exist"},
    )
    assert resp.status_code == 400


def test_pair_callback_with_unknown_kind_returns_400(
    client: TestClient, oauth_stub
) -> None:
    resp = client.get(
        "/oauth/google/callback",
        params={"code": "fake", "state": "garbage:abc"},
    )
    assert resp.status_code == 400


def test_pair_callback_without_refresh_token_returns_400(
    client: TestClient, app, db
) -> None:
    """Per §4.1 D9: Google MUST return a refresh_token; otherwise 400."""

    class _NoRefreshStub(_StubOAuthService):
        def exchange_code(self, code):
            data = super().exchange_code(code)
            data["refresh_token"] = None
            return data

    app.dependency_overrides[deps.get_google_oauth_service] = lambda: _NoRefreshStub()
    start = client.post("/api/pairing/start", json={"device_label": "Kitchen"}).json()
    resp = client.get(
        "/oauth/google/callback",
        params={"code": "fake", "state": f"pair:{start['pairing_id']}"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /oauth/google/authorize?member_id (connect-additional-member flow)
# ---------------------------------------------------------------------------


def test_oauth_authorize_for_unknown_member_returns_404(
    client: TestClient, auth_headers, oauth_stub
) -> None:
    from uuid import uuid4
    resp = client.get(
        f"/oauth/google/authorize?member_id={uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_oauth_authorize_for_member_returns_authorize_url(
    client: TestClient, auth_headers, db, family, oauth_stub
) -> None:
    family_id, _, _ = family
    member = Member(family_id=family_id, name="Mom", color="rose")
    db.add(member)
    db.commit()
    resp = client.get(
        f"/oauth/google/authorize?member_id={member.id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert "state=connect:" in resp.json()["authorize_url"]


# ---------------------------------------------------------------------------
# A1 — contract: pair callback redirects to /pair/complete?token=<jwt>, NOT
# the legacy /settings?paired=1&token= target. The frontend Pairing page reads
# the token from the query string and persists it; drift here breaks the SPA.
# ---------------------------------------------------------------------------


def test_pair_callback_redirect_location_targets_pair_complete_with_token(
    client: TestClient, db, oauth_stub
) -> None:
    """A1 contract: 302 Location must be `/pair/complete?token=<jwt>` and the
    token must decode as a device-scoped JWT."""
    import jwt

    from src.core.dependencies import get_settings

    start = client.post(
        "/api/pairing/start", json={"device_label": "Kitchen"}
    ).json()
    resp = client.get(
        "/oauth/google/callback",
        params={"code": "fake-code", "state": f"pair:{start['pairing_id']}"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("/pair/complete?token=")
    # The token must be present and decode against our JWT secret with typ=device.
    token = location.split("token=", 1)[1]
    assert token, "Location header had no JWT after token="
    settings = get_settings()
    payload = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    assert payload["typ"] == "device"
    assert payload.get("family_id")
    assert payload.get("sub")
    # The legacy cookie path is gone — must NOT be set.
    assert "fridge_device_token" not in resp.cookies
