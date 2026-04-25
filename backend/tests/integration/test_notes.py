"""Integration tests for /notes (§5.5, notes.md MoSCoW).

Covers all Musts:
- CRUD with family-scoping enforced
- Pinned ordering
- Free-form labels (auto-materialized via LabelService.upsert_for_slugs)
- Shopping-list append (existing list, auto-create branch, no-line edge)
- icon nullable
- linked_event_id field present
- Hard delete with no confirmation
- §7.6 cache invalidation + §5.11 pub/sub
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from src.models import Note
from src.schemas.notes import NoteListResponse, NoteResponse


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_post_notes_creates_note_with_labels_and_returns_201(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/notes",
        headers=auth_headers,
        json={
            "content": "Trash Mon 8am",
            "icon": "trash",
            "label_slugs": ["reminder"],
            "pinned": True,
            "assignee_member_id": None,
            "car_ids": [],
            "linked_event_id": None,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["content"] == "Trash Mon 8am"
    assert body["icon"] == "trash"
    assert body["pinned"] is True
    assert body["labels"] == [{"slug": "reminder", "display_name": "Reminder"}]
    NoteResponse.model_validate(body)


def test_post_notes_normalizes_freeform_label_slug(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """notes.md Must: free-form labels — slug is normalized."""
    resp = client.post(
        "/notes",
        headers=auth_headers,
        json={"content": "test", "label_slugs": ["Shopping List", "PETS"]},
    )
    body = resp.json()
    slugs = sorted(label["slug"] for label in body["labels"])
    assert slugs == ["pets", "shopping-list"]


def test_get_notes_returns_pinned_first(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """notes.md Must: pinned notes render first, rest by recency."""
    client.post(
        "/notes", headers=auth_headers, json={"content": "older", "pinned": False}
    )
    client.post(
        "/notes",
        headers=auth_headers,
        json={"content": "Pinned trash reminder", "pinned": True},
    )
    listed = client.get("/notes", headers=auth_headers).json()
    assert listed["items"][0]["content"] == "Pinned trash reminder"
    NoteListResponse.model_validate(listed)


def test_patch_note_updates_content(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    note = client.post(
        "/notes", headers=auth_headers, json={"content": "old"}
    ).json()
    resp = client.patch(
        f"/notes/{note['id']}", headers=auth_headers, json={"content": "new"}
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "new"


def test_delete_note_hard_deletes(
    client: TestClient, auth_headers: dict[str, str], db
) -> None:
    """notes.md Must: hard delete with no confirmation."""
    note = client.post(
        "/notes", headers=auth_headers, json={"content": "to delete"}
    ).json()
    resp = client.delete(f"/notes/{note['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert db.query(Note).filter(Note.id == UUID(note["id"])).first() is None


def test_get_note_in_other_family_returns_404(
    client: TestClient, auth_headers: dict[str, str], make_family
) -> None:
    _other_fam, _device, other_token = make_family(family_name="Other")
    other_note = client.post(
        "/notes",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"content": "secret"},
    ).json()
    resp = client.get(f"/notes/{other_note['id']}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "notes.not_found"


def test_get_notes_filtered_by_label_returns_only_matching(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/notes",
        headers=auth_headers,
        json={"content": "buy milk", "label_slugs": ["shopping-list"]},
    )
    client.post(
        "/notes",
        headers=auth_headers,
        json={"content": "trash mon", "label_slugs": ["reminder"]},
    )
    resp = client.get("/notes?label=shopping-list", headers=auth_headers).json()
    contents = [n["content"] for n in resp["items"]]
    assert "buy milk" in contents
    assert "trash mon" not in contents


# ---------------------------------------------------------------------------
# Shopping list (notes.md Must + Should)
# ---------------------------------------------------------------------------


def test_shopping_list_append_to_existing_list_appends_line(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """notes.md Must: appending 'milk' adds a new line ending in 'milk'."""
    list_note = client.post(
        "/notes",
        headers=auth_headers,
        json={
            "content": "eggs",
            "label_slugs": ["shopping-list"],
            "pinned": True,
        },
    ).json()
    resp = client.post(
        "/notes/shopping-list/append",
        headers=auth_headers,
        json={"line": "milk"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == list_note["id"]
    assert body["content"].splitlines()[-1] == "milk"


def test_shopping_list_append_creates_note_when_none_exists_and_auto_create_on(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """notes.md Should: auto-create when no shopping-list note exists."""
    resp = client.post(
        "/notes/shopping-list/append",
        headers=auth_headers,
        json={"line": "milk"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "milk"
    assert body["pinned"] is True
    assert {"slug": "shopping-list", "display_name": "Shopping list"} in body["labels"]


def test_shopping_list_append_with_empty_line_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/notes/shopping-list/append",
        headers=auth_headers,
        json={"line": ""},
    )
    assert resp.status_code == 422


def test_shopping_list_append_skips_duplicate_last_line(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Service skips append if last line already matches — idempotent for chat."""
    client.post(
        "/notes",
        headers=auth_headers,
        json={"content": "milk", "label_slugs": ["shopping-list"]},
    )
    after = client.post(
        "/notes/shopping-list/append",
        headers=auth_headers,
        json={"line": "milk"},
    ).json()
    assert after["content"] == "milk"  # not "milk\nmilk"


# ---------------------------------------------------------------------------
# Cache + pub/sub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_note_invalidates_notes_cache(
    client: TestClient, auth_headers: dict[str, str], redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    client.get("/notes", headers=auth_headers)
    primed = await redis_client.keys(f"family:{family_id}:notes:*")
    assert primed
    client.post("/notes", headers=auth_headers, json={"content": "new"})
    after = await redis_client.keys(f"family:{family_id}:notes:*")
    assert after == []


@pytest.mark.asyncio
async def test_post_note_publishes_note_created_event(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.post("/notes", headers=auth_headers, json={"content": "test"})
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "note.created"
    assert frames[0]["entity"] == "notes"
    assert frames[0]["actor"] == "rest"


@pytest.mark.asyncio
async def test_shopping_list_append_publishes_appended_event(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.post(
            "/notes/shopping-list/append",
            headers=auth_headers,
            json={"line": "milk"},
        )
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "note.shopping_list.appended"
