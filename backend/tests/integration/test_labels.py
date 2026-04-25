"""Integration tests for /labels (§5.6).

Covers reserved-slug protection, family-scoped CRUD, normalization invariants,
note_count aggregation, and §5.11 frame emission.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.schemas.labels import LabelResponse


def test_post_label_creates_with_normalized_slug(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/labels",
        headers=auth_headers,
        json={"slug": "Pets & Plants", "display_name": "Pets & Plants"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "pets-plants"
    assert body["display_name"] == "Pets & Plants"
    assert body["is_reserved"] is False
    LabelResponse.model_validate(body)


def test_post_label_with_empty_slug_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/labels", headers=auth_headers, json={"slug": "", "display_name": "X"}
    )
    assert resp.status_code == 422


def test_get_labels_returns_list_with_note_counts(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/labels", headers=auth_headers, json={"slug": "todo", "display_name": "Todo"}
    )
    client.post(
        "/notes", headers=auth_headers, json={"content": "x", "label_slugs": ["todo"]}
    )
    client.post(
        "/notes", headers=auth_headers, json={"content": "y", "label_slugs": ["todo"]}
    )
    resp = client.get("/labels", headers=auth_headers)
    by_slug = {label["slug"]: label for label in resp.json()}
    assert by_slug["todo"]["note_count"] == 2


def test_patch_label_updates_display_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/labels", headers=auth_headers, json={"slug": "todo", "display_name": "Todo"}
    )
    resp = client.patch(
        "/labels/todo", headers=auth_headers, json={"display_name": "Tasks"}
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Tasks"


def test_delete_user_label_returns_204(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post(
        "/labels", headers=auth_headers, json={"slug": "todo", "display_name": "Todo"}
    )
    resp = client.delete("/labels/todo", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_reserved_shopping_list_label_returns_409(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Reserved labels must not be deletable — required by NoteService.append_shopping_list contract."""
    # Materialize via a note so the label row exists in the family.
    client.post(
        "/notes",
        headers=auth_headers,
        json={"content": "milk", "label_slugs": ["shopping-list"]},
    )
    resp = client.delete("/labels/shopping-list", headers=auth_headers)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "labels.reserved"


def test_patch_unknown_label_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch(
        "/labels/nonexistent",
        headers=auth_headers,
        json={"display_name": "X"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "labels.not_found"


@pytest.mark.asyncio
async def test_post_label_publishes_label_created_event(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.post(
            "/labels",
            headers=auth_headers,
            json={"slug": "todo", "display_name": "Todo"},
        )
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "label.created"
    assert frames[0]["entity"] == "labels"
    # Labels are keyed by slug, not UUID.
    assert frames[0]["id"] == "todo"
