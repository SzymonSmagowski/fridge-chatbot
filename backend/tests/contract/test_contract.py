"""Contract tests — for every §5 endpoint, call it and assert the response
parses cleanly against the Architect-declared Pydantic schema.

These exist to catch silent backend-vs-Architect drift. If a field is renamed
or removed without updating the schema, this suite fails. FrontendTester
mocks the backend at the HTTP layer — these tests guarantee the mock shape
matches what the backend actually returns.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.models import Member
from src.schemas.calendar_sync import SyncStateResponse
from src.schemas.cars import CarResponse
from src.schemas.events import (
    EventListResponse,
    EventResponse,
    EventTargetView,
)
from src.schemas.family import (
    FamilyPreferencesResponse,
    FamilyResponse,
)
from src.schemas.labels import LabelResponse
from src.schemas.members import GoogleState, MemberResponse
from src.schemas.notes import NoteListResponse, NoteResponse
from src.schemas.oauth import AuthorizeUrlResponse, PairingStartResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def stubbed_oauth(app):
    """Stub GoogleOAuthService for contract tests that need /pairing."""
    from src.core import dependencies as deps

    class _Stub:
        def build_authorize_url(self, state):
            return (
                f"https://accounts.google.com/o/oauth2/v2/auth?state={state}",
                "stub-code-verifier",
            )

        def exchange_code(self, code, code_verifier=None):
            return {
                "access_token": "x",
                "refresh_token": "rt",
                "scope": "x",
                "expires_in": 3600,
                "google_sub": "g-1",
                "google_email": "x@y.z",
                "google_name": "X",
                "google_given_name": "X",
            }

        async def revoke(self, t):
            return True

    app.dependency_overrides[deps.get_google_oauth_service] = lambda: _Stub()
    yield


@pytest.fixture
def stubbed_fan_out(monkeypatch):
    from src.routes import events as events_route

    async def _no_op(**kwargs):
        return None

    monkeypatch.setattr(events_route, "fan_out_event", _no_op)


# ---------------------------------------------------------------------------
# §5.1 Pairing & OAuth
# ---------------------------------------------------------------------------


def test_contract_pairing_start_response_matches_schema(
    client: TestClient, stubbed_oauth
) -> None:
    resp = client.post("/api/pairing/start", json={"device_label": "Kitchen"})
    PairingStartResponse.model_validate(resp.json())


def test_contract_oauth_authorize_response_matches_schema(
    client: TestClient, auth_headers, db, family, stubbed_oauth
) -> None:
    family_id, _, _ = family
    member = Member(family_id=family_id, name="Mom", color="rose")
    db.add(member)
    db.commit()
    resp = client.get(
        f"/oauth/google/authorize?member_id={member.id}", headers=auth_headers
    )
    AuthorizeUrlResponse.model_validate(resp.json())


# ---------------------------------------------------------------------------
# §5.2 Family
# ---------------------------------------------------------------------------


def test_contract_family_get_matches_schema(client: TestClient, auth_headers) -> None:
    resp = client.get("/api/family", headers=auth_headers)
    FamilyResponse.model_validate(resp.json())


def test_contract_family_patch_matches_schema(client: TestClient, auth_headers) -> None:
    resp = client.patch("/api/family", headers=auth_headers, json={"name": "X"})
    FamilyResponse.model_validate(resp.json())


# ---------------------------------------------------------------------------
# §5.3 Members
# ---------------------------------------------------------------------------


def test_contract_members_create_matches_schema(
    client: TestClient, auth_headers
) -> None:
    resp = client.post(
        "/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"}
    )
    body = resp.json()
    MemberResponse.model_validate(body)
    GoogleState.model_validate(body["google"])


def test_contract_members_list_matches_schema(client: TestClient, auth_headers) -> None:
    client.post("/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"})
    resp = client.get("/api/members", headers=auth_headers)
    for item in resp.json():
        MemberResponse.model_validate(item)


def test_contract_member_detail_matches_schema(
    client: TestClient, auth_headers
) -> None:
    created = client.post(
        "/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"}
    ).json()
    resp = client.get(f"/api/members/{created['id']}", headers=auth_headers)
    MemberResponse.model_validate(resp.json())


def test_contract_set_inactive_matches_schema(
    client: TestClient, auth_headers
) -> None:
    created = client.post(
        "/api/members", headers=auth_headers, json={"name": "Ola", "color": "sage"}
    ).json()
    resp = client.post(f"/api/members/{created['id']}/set-inactive", headers=auth_headers)
    MemberResponse.model_validate(resp.json())
    assert resp.json()["status"] == "inactive"


# ---------------------------------------------------------------------------
# §5.4 Cars
# ---------------------------------------------------------------------------


def test_contract_cars_create_matches_schema(client: TestClient, auth_headers) -> None:
    resp = client.post("/api/cars", headers=auth_headers, json={"name": "Civic"})
    CarResponse.model_validate(resp.json())


def test_contract_cars_list_matches_schema(client: TestClient, auth_headers) -> None:
    client.post("/api/cars", headers=auth_headers, json={"name": "Civic"})
    for item in client.get("/api/cars", headers=auth_headers).json():
        CarResponse.model_validate(item)


# ---------------------------------------------------------------------------
# §5.5 Notes
# ---------------------------------------------------------------------------


def test_contract_notes_create_matches_schema(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/notes",
        headers=auth_headers,
        json={"content": "test", "label_slugs": ["reminder"]},
    )
    NoteResponse.model_validate(resp.json())


def test_contract_notes_list_matches_schema(client: TestClient, auth_headers) -> None:
    client.post("/api/notes", headers=auth_headers, json={"content": "x"})
    NoteListResponse.model_validate(client.get("/api/notes", headers=auth_headers).json())


def test_contract_note_detail_matches_schema(
    client: TestClient, auth_headers
) -> None:
    created = client.post(
        "/api/notes", headers=auth_headers, json={"content": "x"}
    ).json()
    resp = client.get(f"/api/notes/{created['id']}", headers=auth_headers)
    NoteResponse.model_validate(resp.json())


def test_contract_shopping_list_append_matches_schema(
    client: TestClient, auth_headers
) -> None:
    resp = client.post(
        "/api/notes/shopping-list/append",
        headers=auth_headers,
        json={"line": "milk"},
    )
    NoteResponse.model_validate(resp.json())


# ---------------------------------------------------------------------------
# §5.6 Labels
# ---------------------------------------------------------------------------


def test_contract_labels_create_matches_schema(
    client: TestClient, auth_headers
) -> None:
    resp = client.post(
        "/api/labels", headers=auth_headers, json={"slug": "todo", "display_name": "Todo"}
    )
    LabelResponse.model_validate(resp.json())


def test_contract_labels_list_matches_schema(client: TestClient, auth_headers) -> None:
    client.post(
        "/api/labels", headers=auth_headers, json={"slug": "todo", "display_name": "Todo"}
    )
    for item in client.get("/api/labels", headers=auth_headers).json():
        LabelResponse.model_validate(item)


# ---------------------------------------------------------------------------
# §5.7 Events
# ---------------------------------------------------------------------------


def test_contract_events_create_matches_schema(
    client: TestClient, auth_headers, stubbed_fan_out
) -> None:
    resp = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "x",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    )
    body = resp.json()
    EventResponse.model_validate(body)
    for t in body["targets"]:
        EventTargetView.model_validate(t)


def test_contract_events_list_matches_schema(
    client: TestClient, auth_headers, stubbed_fan_out
) -> None:
    client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "x",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    )
    EventListResponse.model_validate(
        client.get("/api/events", headers=auth_headers).json()
    )


def test_contract_event_detail_matches_schema(
    client: TestClient, auth_headers, stubbed_fan_out
) -> None:
    created = client.post(
        "/api/events",
        headers=auth_headers,
        json={
            "title": "x",
            "start_at": "2026-05-01T10:00:00+00:00",
            "end_at": "2026-05-01T11:00:00+00:00",
        },
    ).json()
    resp = client.get(f"/api/events/{created['id']}", headers=auth_headers)
    EventResponse.model_validate(resp.json())


# ---------------------------------------------------------------------------
# §5.8 Family preferences
# ---------------------------------------------------------------------------


def test_contract_family_preferences_get_matches_schema(
    client: TestClient, auth_headers
) -> None:
    resp = client.get("/api/family/preferences", headers=auth_headers)
    FamilyPreferencesResponse.model_validate(resp.json())


def test_contract_family_preferences_patch_matches_schema(
    client: TestClient, auth_headers
) -> None:
    resp = client.patch(
        "/api/family/preferences",
        headers=auth_headers,
        json={"sync_interval_sec": 600},
    )
    FamilyPreferencesResponse.model_validate(resp.json())


# ---------------------------------------------------------------------------
# §5.9 Calendar sync
# ---------------------------------------------------------------------------


def test_contract_calendar_sync_state_matches_schema(
    client: TestClient, auth_headers, db, family
) -> None:
    family_id, _, _ = family
    db.add(Member(family_id=family_id, name="Mom", color="rose"))
    db.commit()
    for row in client.get("/api/calendar/sync-state", headers=auth_headers).json():
        SyncStateResponse.model_validate(row)


# ---------------------------------------------------------------------------
# Cross-family 404 invariant (§5.3 rationale, applies app-wide)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,code",
    [
        ("/api/members/{id}", "members.not_found"),
        ("/api/notes/{id}", "notes.not_found"),
        ("/api/events/{id}", "events.not_found"),
    ],
)
def test_contract_random_uuid_returns_404_with_typed_code(
    client: TestClient, auth_headers, path: str, code: str
) -> None:
    resp = client.get(path.format(id=uuid4()), headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == code
