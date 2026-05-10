"""Re-export every SQLAlchemy model so `Base.metadata` sees them all and Alembic
autogenerate picks them up.
"""
from src.models.car import Car, CarStatus
from src.models.database import Message, Thread, User
from src.models.event import (
    Event,
    EventCar,
    EventTarget,
    EventTargetSyncStatus,
    ExternalEventCacheRow,
)
from src.models.family import Device, Family, FamilyPreferences
from src.models.feedback import (
    Feedback,
    FeedbackAuthorKind,
    FeedbackCategory,
    FeedbackStatus,
)
from src.models.label import Label, NoteLabel
from src.models.member import (
    CalendarSyncState,
    GoogleToken,
    GoogleTokenStatus,
    Member,
    MemberStatus,
)
from src.models.note import Note, NoteCar

__all__ = [
    "User",
    "Thread",
    "Message",
    "Family",
    "FamilyPreferences",
    "Device",
    "Member",
    "MemberStatus",
    "GoogleToken",
    "GoogleTokenStatus",
    "CalendarSyncState",
    "Car",
    "CarStatus",
    "Label",
    "NoteLabel",
    "Note",
    "NoteCar",
    "Event",
    "EventTarget",
    "EventTargetSyncStatus",
    "EventCar",
    "ExternalEventCacheRow",
    "Feedback",
    "FeedbackAuthorKind",
    "FeedbackCategory",
    "FeedbackStatus",
]
