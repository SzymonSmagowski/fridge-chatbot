"""Car — schedulable resource (assignable to events + notes)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.db.postgres import Base


class CarStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class Car(Base):
    __tablename__ = "cars"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(
        UUID(as_uuid=True),
        ForeignKey("families.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(120), nullable=False)
    year = Column(Integer, nullable=True)
    color_label = Column(String(32), nullable=True)
    color = Column(String(32), nullable=False, default="stone")
    notes = Column(Text, nullable=True)
    status = Column(
        Enum(CarStatus, name="car_status"),
        nullable=False,
        default=CarStatus.active,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="cars")

    __table_args__ = (Index("ix_cars_family_status", "family_id", "status"),)
