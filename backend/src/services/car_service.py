"""Car CRUD scoped to one family."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.context import current_actor
from src.core.family_events import family_event_payload
from src.models import Car, CarStatus
from src.schemas.cars import CarCreateRequest, CarUpdateRequest
from src.services.chat_streaming import ChatStreamer

CarStatusFilter = Literal["active", "inactive", "all"]


class CarService:
    def __init__(
        self, db: Session, family_id: UUID, streamer: ChatStreamer
    ) -> None:
        self.db = db
        self.family_id = family_id
        self.streamer = streamer

    async def _publish(self, *, type: str, car_id: UUID) -> None:
        await self.streamer.publish_family_event(
            self.family_id,
            family_event_payload(
                type=type,
                entity="cars",
                id=car_id,
                actor=current_actor.get(),
            ),
        )

    def list(self, status_filter: CarStatusFilter = "active") -> list[Car]:
        q = self.db.query(Car).filter(Car.family_id == self.family_id)
        if status_filter == "active":
            q = q.filter(Car.status == CarStatus.active)
        elif status_filter == "inactive":
            q = q.filter(Car.status == CarStatus.inactive)
        return q.order_by(Car.created_at.asc()).all()

    def get(self, car_id: UUID) -> Car:
        car = (
            self.db.query(Car)
            .filter(Car.id == car_id, Car.family_id == self.family_id)
            .first()
        )
        if not car:
            raise HTTPException(
                status_code=404,
                detail={"code": "cars.not_found", "detail": "Car not found"},
            )
        return car

    async def create(self, data: CarCreateRequest) -> Car:
        car = Car(
            family_id=self.family_id,
            name=data.name,
            year=data.year,
            color_label=data.color_label,
            color=data.color,
            notes=data.notes,
            status=CarStatus.active,
        )
        self.db.add(car)
        self.db.commit()
        self.db.refresh(car)
        await self._publish(type="car.created", car_id=car.id)
        return car

    async def update(self, car_id: UUID, data: CarUpdateRequest) -> Car:
        car = self.get(car_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(car, field, value)
        self.db.commit()
        self.db.refresh(car)
        await self._publish(type="car.updated", car_id=car.id)
        return car

    async def set_status(self, car_id: UUID, status: CarStatus) -> Car:
        car = self.get(car_id)
        car.status = status
        self.db.commit()
        self.db.refresh(car)
        type_name = (
            "car.set-active"
            if status == CarStatus.active
            else "car.set-inactive"
        )
        await self._publish(type=type_name, car_id=car.id)
        return car

    async def hard_delete(self, car_id: UUID) -> None:
        car = self.get(car_id)
        deleted_id = car.id
        self.db.delete(car)
        self.db.commit()
        await self._publish(type="car.deleted", car_id=deleted_id)
