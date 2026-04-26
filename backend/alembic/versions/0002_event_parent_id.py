"""events.parent_event_id for recurring-split sibling lookup

Revision ID: 0002_event_parent_id
Revises: 0001_initial_schema
Create Date: 2026-04-26

Adds a nullable self-FK on `events` so the §6.7 recurring-split sibling
lookup can match by stable identity (`(family_id, parent_event_id, start_at)`)
instead of `title`, which gets rewritten by the patch and breaks idempotency.

ON DELETE SET NULL — orphaning the child is safer than cascading; a deleted
original master shouldn't drag its split-off children with it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_event_parent_id"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "parent_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_events_parent_event_id",
        source_table="events",
        referent_table="events",
        local_cols=["parent_event_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_events_family_parent_start",
        "events",
        ["family_id", "parent_event_id", "start_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_family_parent_start", table_name="events")
    op.drop_constraint("fk_events_parent_event_id", "events", type_="foreignkey")
    op.drop_column("events", "parent_event_id")
