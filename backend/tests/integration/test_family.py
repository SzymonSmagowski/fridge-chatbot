"""Integration tests for /family + /family/preferences (§5.2, §5.8)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from src.schemas.family import FamilyPreferencesResponse, FamilyResponse


def test_get_family_returns_seeded_family(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/api/family", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test Family"
    assert body["timezone"] == "Europe/Warsaw"
    FamilyResponse.model_validate(body)


def test_patch_family_updates_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch(
        "/api/family", headers=auth_headers, json={"name": "The Magowski Family"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "The Magowski Family"


def test_get_family_preferences_returns_defaults(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.get("/api/family/preferences", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["sync_interval_sec"] == 300
    assert body["auto_create_shopping_list"] is True
    assert body["always_on"] is True
    FamilyPreferencesResponse.model_validate(body)


def test_patch_family_preferences_partial_update(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.patch(
        "/api/family/preferences",
        headers=auth_headers,
        json={"sync_interval_sec": 600, "voice_wake_enabled": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sync_interval_sec"] == 600
    assert body["voice_wake_enabled"] is True
    # Unspecified fields preserved.
    assert body["auto_create_shopping_list"] is True


@pytest.mark.asyncio
async def test_patch_family_publishes_family_updated(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.patch("/api/family", headers=auth_headers, json={"name": "Renamed"})
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "family.updated"
    assert frames[0]["entity"] == "family"


@pytest.mark.asyncio
async def test_patch_family_preferences_publishes_event(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.patch(
            "/api/family/preferences",
            headers=auth_headers,
            json={"sync_interval_sec": 120},
        )
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "family_preferences.updated"
    assert frames[0]["entity"] == "family_preferences"


@pytest.mark.asyncio
async def test_patch_family_invalidates_family_cache(
    client: TestClient, auth_headers, redis_client: Redis, family
) -> None:
    family_id, _, _ = family
    client.get("/api/family", headers=auth_headers)
    primed = await redis_client.keys(f"family:{family_id}:family")
    assert primed
    client.patch("/api/family", headers=auth_headers, json={"name": "New"})
    after = await redis_client.keys(f"family:{family_id}:family")
    assert after == []
