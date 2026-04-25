"""Integration tests for /cars (§5.4, cars.md MoSCoW).

Covers all Musts:
- CRUD via settings UI (name, year, color_label, notes)
- status active/inactive — soft delete via set-inactive
- Hard delete with explicit DELETE
- Cars assignable to events alongside or instead of members (cross-spec)
"""
from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from src.models import Car
from src.schemas.cars import CarResponse


def test_post_cars_creates_active_car_and_returns_201(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/cars",
        headers=auth_headers,
        json={
            "name": "Red Civic",
            "year": 2019,
            "color_label": "Red",
            "color": "rose",
            "notes": "at Pete's Garage",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Red Civic"
    assert body["year"] == 2019
    assert body["color_label"] == "Red"
    assert body["status"] == "active"
    CarResponse.model_validate(body)


def test_get_cars_lists_only_active_by_default(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    client.post("/cars", headers=auth_headers, json={"name": "Volvo"})
    b = client.post("/cars", headers=auth_headers, json={"name": "Civic"}).json()
    client.post(f"/cars/{b['id']}/set-inactive", headers=auth_headers)
    listed = client.get("/cars", headers=auth_headers).json()
    names = [c["name"] for c in listed]
    assert "Volvo" in names
    assert "Civic" not in names


def test_patch_car_updates_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    car = client.post("/cars", headers=auth_headers, json={"name": "Volvo"}).json()
    resp = client.patch(
        f"/cars/{car['id']}",
        headers=auth_headers,
        json={"notes": "in the shop"},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "in the shop"


def test_set_inactive_then_active_round_trip(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    car = client.post("/cars", headers=auth_headers, json={"name": "Civic"}).json()
    inactive = client.post(
        f"/cars/{car['id']}/set-inactive", headers=auth_headers
    ).json()
    assert inactive["status"] == "inactive"
    active = client.post(
        f"/cars/{car['id']}/set-active", headers=auth_headers
    ).json()
    assert active["status"] == "active"


def test_delete_car_hard_deletes_row(
    client: TestClient, auth_headers: dict[str, str], db
) -> None:
    """cars.md MoSCoW Must: hard-delete with explicit confirmation removes the row."""
    car = client.post("/cars", headers=auth_headers, json={"name": "Civic"}).json()
    resp = client.delete(f"/cars/{car['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert db.query(Car).filter(Car.id == UUID(car["id"])).first() is None


def test_get_car_in_other_family_returns_404(
    client: TestClient, auth_headers: dict[str, str], make_family
) -> None:
    """Cross-family scoping: §5.3 rationale applies to cars too."""
    _other_fam, _device, other_token = make_family(family_name="Other")
    other_car = client.post(
        "/cars",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "Stranger Wagon"},
    ).json()
    # Try to PATCH it from our family — must 404.
    resp = client.patch(
        f"/cars/{other_car['id']}",
        headers=auth_headers,
        json={"notes": "stolen"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "cars.not_found"


def test_post_car_with_empty_name_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post("/cars", headers=auth_headers, json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_car_invalidates_notes_and_events_caches(
    client: TestClient, auth_headers: dict[str, str], redis_client: Redis, family
) -> None:
    """§7.6: deleting a car evicts notes and events caches because car-chips
    appear in those views."""
    family_id, _, _ = family
    car = client.post("/cars", headers=auth_headers, json={"name": "Civic"}).json()
    # Prime three caches
    client.get("/cars", headers=auth_headers)
    client.get("/notes", headers=auth_headers)
    client.get("/events", headers=auth_headers)
    primed = await redis_client.keys(f"family:{family_id}:*")
    assert any(k.startswith(f"family:{family_id}:cars:") for k in primed)
    assert any(k.startswith(f"family:{family_id}:notes:") for k in primed)
    assert any(k.startswith(f"family:{family_id}:events:") for k in primed)

    client.delete(f"/cars/{car['id']}", headers=auth_headers)
    after = await redis_client.keys(f"family:{family_id}:*")
    assert not any(k.startswith(f"family:{family_id}:cars:") for k in after)
    assert not any(k.startswith(f"family:{family_id}:notes:") for k in after)
    assert not any(k.startswith(f"family:{family_id}:events:") for k in after)


@pytest.mark.asyncio
async def test_post_car_publishes_car_created_event(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    async with family_event_collector(family_id) as collector:
        client.post("/cars", headers=auth_headers, json={"name": "Civic"})
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "car.created"
    assert frames[0]["entity"] == "cars"


@pytest.mark.asyncio
async def test_delete_car_publishes_car_deleted_event(
    client: TestClient, auth_headers, family, family_event_collector
) -> None:
    family_id, _, _ = family
    car = client.post("/cars", headers=auth_headers, json={"name": "Volvo"}).json()
    async with family_event_collector(family_id) as collector:
        client.delete(f"/cars/{car['id']}", headers=auth_headers)
        frames = await collector.wait_for(1)
    assert frames[0]["type"] == "car.deleted"
