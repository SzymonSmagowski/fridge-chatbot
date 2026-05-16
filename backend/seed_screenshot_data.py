"""One-off seed for the README screenshots — populates a family with realistic data
and prints a device JWT for the kiosk to pick up via localStorage.

Run from `apps/fridge-chatbot/backend/`:
    poetry run python seed_screenshot_data.py

Idempotent: wipes any family whose name matches FAMILY_NAME before seeding.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from src.core.settings import Settings
from src.db.postgres import Database
from src.models.car import Car, CarStatus
from src.models.database import User
from src.models.event import Event
from src.models.family import Device, Family, FamilyPreferences
from src.models.label import Label, NoteLabel
from src.models.member import Member, MemberStatus
from src.models.note import Note

FAMILY_NAME = "The Magowski Family"


def main() -> None:
    settings = Settings()
    db = Database(settings)

    with db.get_db() as session:
        # --- wipe prior runs so this is idempotent --------------------------
        old = session.query(Family).filter(Family.name == FAMILY_NAME).all()
        for fam in old:
            session.delete(fam)
        session.flush()

        # --- family + preferences ------------------------------------------
        family = Family(name=FAMILY_NAME, timezone="Europe/Warsaw")
        session.add(family)
        session.flush()
        session.add(
            FamilyPreferences(
                family_id=family.id,
                sync_interval_sec=300,
                auto_create_shopping_list=True,
                updated_at=datetime.utcnow(),
            )
        )

        # --- shadow user + device ------------------------------------------
        shadow = User(
            username=f"device-{family.id.hex[:12]}",
            email=None,
            hashed_password="$2b$12$placeholderplaceholderplaceholderplaceholder",
            is_active=True,
        )
        session.add(shadow)
        session.flush()
        device = Device(
            family_id=family.id,
            label="Kitchen fridge",
            paired_at=datetime.utcnow(),
            shadow_user_id=shadow.id,
        )
        session.add(device)
        session.flush()

        # --- members --------------------------------------------------------
        monika = Member(family_id=family.id, name="Monika", nickname="Mom", color="blush", status=MemberStatus.active, is_setup_owner=True)
        szymon = Member(family_id=family.id, name="Szymon", nickname="Dad", color="blue", status=MemberStatus.active, is_setup_owner=False)
        ola = Member(family_id=family.id, name="Ola", nickname=None, color="butter", status=MemberStatus.active, is_setup_owner=False)
        for m in (monika, szymon, ola):
            session.add(m)
        session.flush()

        # --- cars -----------------------------------------------------------
        cars = [
            Car(family_id=family.id, name="Family Volvo", year=2019, color_label="silver", color="stone", status=CarStatus.active),
            Car(family_id=family.id, name="Red Civic", year=2015, color_label="red", color="blush", status=CarStatus.active),
            Car(family_id=family.id, name="Ola's Scooter", year=2024, color_label="lime", color="sage", status=CarStatus.active),
        ]
        for c in cars:
            session.add(c)
        session.flush()

        # --- labels ---------------------------------------------------------
        shopping_label = Label(family_id=family.id, slug="shopping-list", display_name="Shopping list")
        session.add(shopping_label)
        session.flush()

        # --- notes ----------------------------------------------------------
        notes: list[Note] = []

        shopping = Note(
            family_id=family.id,
            assignee_member_id=None,
            content=(
                "[ ] Milk\n"
                "[ ] Eggs (dozen)\n"
                "[x] Sourdough\n"
                "[ ] Romaine + tomatoes\n"
                "[ ] Coffee beans\n"
                "[ ] Apples (gala)"
            ),
            icon="🛒",
            pinned=True,
        )
        notes.append(shopping)

        notes.append(
            Note(
                family_id=family.id,
                assignee_member_id=monika.id,
                content="Bins out by 7am Monday. Green bin this week — recycling.",
                icon="🗑️",
                pinned=True,
            )
        )
        notes.append(
            Note(
                family_id=family.id,
                assignee_member_id=ola.id,
                content="Ola's permission slip for the science museum trip — sign and return by Friday.",
                icon="📝",
                pinned=True,
            )
        )
        notes.append(
            Note(
                family_id=family.id,
                assignee_member_id=ola.id,
                content="Dr. Carter's office, insurance card on the fridge.",
                icon="🦷",
                pinned=False,
            )
        )
        notes.append(
            Note(
                family_id=family.id,
                assignee_member_id=szymon.id,
                content="Red Civic is at Pete's garage — oil change + new tires. Ready Thursday.",
                icon="🚗",
                pinned=False,
            )
        )
        notes.append(
            Note(
                family_id=family.id,
                assignee_member_id=None,
                content="Locker at Whole Foods, code 4421. Expires Sat 9pm.",
                icon="📦",
                pinned=False,
            )
        )
        for n in notes:
            session.add(n)
        session.flush()

        # Tag the shopping note with the shopping-list label
        session.add(NoteLabel(note_id=shopping.id, family_id=family.id, label_slug="shopping-list"))

        # --- calendar events (this week + next) ----------------------------
        tz = timezone(timedelta(hours=2))  # Europe/Warsaw, dev-time ok
        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        # Snap to Monday of the current week so the week view is populated end-to-end
        monday = today - timedelta(days=today.weekday())

        def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
            return monday + timedelta(days=day_offset, hours=hour, minutes=minute)

        events = [
            # Monday
            Event(family_id=family.id, title="Soccer practice", description="Riverside Park, field 2", start_at=at(0, 16), end_at=at(0, 17, 30), timezone="Europe/Warsaw", location="Riverside Park", assignee_member_id=ola.id),
            Event(family_id=family.id, title="Trash & recycling (green bin)", description=None, start_at=at(0, 7), end_at=at(0, 7, 30), timezone="Europe/Warsaw", location=None, assignee_member_id=monika.id),
            # Tuesday
            Event(family_id=family.id, title="Dentist — Dr. Carter", description="Bring insurance card", start_at=at(1, 10), end_at=at(1, 11), timezone="Europe/Warsaw", location="Dr. Carter's office", assignee_member_id=ola.id),
            Event(family_id=family.id, title="Standup (work)", description=None, start_at=at(1, 9), end_at=at(1, 9, 15), timezone="Europe/Warsaw", location=None, assignee_member_id=szymon.id),
            # Wednesday
            Event(family_id=family.id, title="Dinner with the Smiths", description="Their place, 8pm", start_at=at(2, 19), end_at=at(2, 22), timezone="Europe/Warsaw", location="Smiths' house", assignee_member_id=None),
            Event(family_id=family.id, title="Pilates", description=None, start_at=at(2, 8), end_at=at(2, 9), timezone="Europe/Warsaw", location="Studio One", assignee_member_id=monika.id),
            # Thursday
            Event(family_id=family.id, title="Pick up Red Civic from Pete's", description="Oil change + new tires", start_at=at(3, 17), end_at=at(3, 17, 30), timezone="Europe/Warsaw", location="Pete's Garage", assignee_member_id=szymon.id),
            Event(family_id=family.id, title="Volvo service appointment", description="Yearly check", start_at=at(3, 11), end_at=at(3, 12, 30), timezone="Europe/Warsaw", location="Volvo dealer", assignee_member_id=None),
            # Friday
            Event(family_id=family.id, title="Science museum trip", description="Permission slip required — Ola", start_at=at(4, 9), end_at=at(4, 15), timezone="Europe/Warsaw", location="Science Museum", assignee_member_id=ola.id),
            # Saturday
            Event(family_id=family.id, title="Civic at Pete's pickup", description=None, start_at=at(5, 10), end_at=at(5, 10, 30), timezone="Europe/Warsaw", location="Pete's Garage", assignee_member_id=szymon.id),
            Event(family_id=family.id, title="Family swim", description=None, start_at=at(5, 16), end_at=at(5, 17, 30), timezone="Europe/Warsaw", location="Aqua Park", assignee_member_id=None),
        ]
        for e in events:
            session.add(e)

        session.commit()

        # --- mint JWT ------------------------------------------------------
        payload = {
            "sub": str(device.id),
            "family_id": str(family.id),
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(days=settings.DEVICE_TOKEN_EXPIRE_DAYS),
            "typ": "device",
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        print("---SEED-DONE---")
        print(f"family_id={family.id}")
        print(f"device_id={device.id}")
        print(f"members=Monika,Szymon,Ola")
        print(f"events={len(events)}")
        print(f"notes={len(notes)}")
        print("---TOKEN-BEGIN---")
        print(token)
        print("---TOKEN-END---")


if __name__ == "__main__":
    main()
