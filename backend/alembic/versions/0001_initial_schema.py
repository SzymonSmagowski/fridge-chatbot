"""initial schema: users/threads/messages + 13 new family-scoped tables

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-24

Creates the entire schema in one shot since the dev DB is empty and there's
no existing user data to preserve. Idempotent against the previous behavior of
`init_db()` (Base.metadata.create_all): if those legacy tables already exist
they are left untouched on first run via `IF NOT EXISTS` guards on the legacy
trio (users / threads / messages).

The 13 family-scoped tables are NEW; this is the first time they're created.
Reserved label seeding (`shopping-list`) is a per-family concern handled inside
the pairing transaction (D9), not here.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # pgcrypto for gen_random_uuid() support (PK defaults rely on Python uuid4
    # at the SQLAlchemy layer, but the extension is idiomatic + harmless).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # --- legacy: users / threads / messages (kept; chat-only) --------------
    if not _table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=50), nullable=False, unique=True),
            sa.Column("email", sa.String(length=200), nullable=True, unique=True),
            sa.Column("hashed_password", sa.String(length=200), nullable=False),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not _table_exists(bind, "threads"):
        op.create_table(
            "threads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "thread_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                unique=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=200), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_threads_thread_id", "threads", ["thread_id"], unique=True)

    if not _table_exists(bind, "messages"):
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "message_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                unique=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "thread_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("threads.thread_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column(
                "type",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'message'"),
            ),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("score", sa.String(length=10), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_messages_message_id", "messages", ["message_id"], unique=True
        )
        op.create_index("ix_messages_thread_id", "messages", ["thread_id"])
        op.create_index("ix_messages_type", "messages", ["type"])

    # --- enums --------------------------------------------------------------
    member_status = postgresql.ENUM(
        "active", "inactive", name="member_status", create_type=False
    )
    google_token_status = postgresql.ENUM(
        "connected",
        "reconnect_needed",
        "revoked",
        name="google_token_status",
        create_type=False,
    )
    car_status = postgresql.ENUM(
        "active", "inactive", name="car_status", create_type=False
    )
    event_target_sync_status = postgresql.ENUM(
        "pending",
        "synced",
        "failed",
        "skipped",
        name="event_target_sync_status",
        create_type=False,
    )
    member_status.create(bind, checkfirst=True)
    google_token_status.create(bind, checkfirst=True)
    car_status.create(bind, checkfirst=True)
    event_target_sync_status.create(bind, checkfirst=True)

    # --- families -----------------------------------------------------------
    op.create_table(
        "families",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'Europe/Warsaw'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )

    # --- family_preferences -------------------------------------------------
    op.create_table(
        "family_preferences",
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "sync_interval_sec", sa.Integer(), nullable=False, server_default="300"
        ),
        sa.Column(
            "fanout_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "voice_wake_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "always_on", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "auto_create_shopping_list",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- devices ------------------------------------------------------------
    op.create_table(
        "devices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column(
            "paired_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column(
            "shadow_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_devices_family", "devices", ["family_id"])

    # --- members ------------------------------------------------------------
    op.create_table(
        "members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("nickname", sa.String(length=120), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "inactive", name="member_status", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "is_setup_owner",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_members_family_status", "members", ["family_id", "status"])

    # --- google_tokens ------------------------------------------------------
    op.create_table(
        "google_tokens",
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("google_sub", sa.String(length=64), nullable=False),
        sa.Column("google_email", sa.String(length=200), nullable=False),
        sa.Column("scope", sa.String(length=400), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "connected",
                "reconnect_needed",
                "revoked",
                name="google_token_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'connected'"),
        ),
        sa.Column(
            "connected_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_refreshed_at", sa.DateTime(), nullable=True),
    )

    # --- calendar_sync_state ------------------------------------------------
    op.create_table(
        "calendar_sync_state",
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("last_pull_at", sa.DateTime(), nullable=True),
        sa.Column("last_pull_sync_token", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # --- cars ---------------------------------------------------------------
    op.create_table(
        "cars",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("color_label", sa.String(length=32), nullable=True),
        sa.Column(
            "color",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'stone'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "inactive", name="car_status", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_cars_family_status", "cars", ["family_id", "status"])

    # --- labels -------------------------------------------------------------
    op.create_table(
        "labels",
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("family_id", "slug", name="pk_labels"),
    )
    op.create_index("ix_labels_family", "labels", ["family_id"])

    # --- events (created BEFORE notes because notes.linked_event_id FKs it) -
    op.create_table(
        "events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=400), nullable=True),
        sa.Column(
            "assignee_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_events_family_start", "events", ["family_id", "start_at"])
    op.create_index(
        "ix_events_family_assignee", "events", ["family_id", "assignee_member_id"]
    )

    # --- notes --------------------------------------------------------------
    op.create_table(
        "notes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assignee_member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column(
            "pinned", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "linked_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_notes_family_pinned_updated",
        "notes",
        ["family_id", "pinned", "updated_at"],
    )
    op.create_index(
        "ix_notes_family_assignee", "notes", ["family_id", "assignee_member_id"]
    )

    # --- note_labels (composite FK back to labels) -------------------------
    op.create_table(
        "note_labels",
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_slug", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("note_id", "label_slug", name="pk_note_labels"),
        sa.ForeignKeyConstraint(
            ["family_id", "label_slug"],
            ["labels.family_id", "labels.slug"],
            ondelete="CASCADE",
            name="fk_note_labels_label",
        ),
    )
    op.create_index(
        "ix_note_labels_family_slug", "note_labels", ["family_id", "label_slug"]
    )

    # --- note_cars ----------------------------------------------------------
    op.create_table(
        "note_cars",
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "car_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cars.id", ondelete="CASCADE"),
        ),
        sa.PrimaryKeyConstraint("note_id", "car_id", name="pk_note_cars"),
    )

    # --- event_targets ------------------------------------------------------
    op.create_table(
        "event_targets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("google_event_id", sa.String(length=256), nullable=True),
        sa.Column(
            "sync_status",
            postgresql.ENUM(
                "pending",
                "synced",
                "failed",
                "skipped",
                name="event_target_sync_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "event_id", "member_id", name="uq_event_targets_event_member"
        ),
    )
    op.create_index(
        "ix_event_targets_status_retry",
        "event_targets",
        ["sync_status", "retry_count"],
    )

    # --- event_cars ---------------------------------------------------------
    op.create_table(
        "event_cars",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "car_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cars.id", ondelete="CASCADE"),
        ),
        sa.PrimaryKeyConstraint("event_id", "car_id", name="pk_event_cars"),
    )

    # --- external_events_cache ---------------------------------------------
    op.create_table(
        "external_events_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("google_event_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=400), nullable=True),
        sa.Column(
            "is_all_day", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column(
            "created_by_fridge",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "member_id",
            "google_event_id",
            name="uq_external_events_member_geid",
        ),
    )
    op.create_index(
        "ix_external_events_family_start",
        "external_events_cache",
        ["family_id", "start_at"],
    )
    op.create_index(
        "ix_external_events_family_member_start",
        "external_events_cache",
        ["family_id", "member_id", "start_at"],
    )


def downgrade() -> None:
    """Drop the 13 family-scoped tables (legacy users/threads/messages stay)."""
    op.drop_index(
        "ix_external_events_family_member_start", table_name="external_events_cache"
    )
    op.drop_index(
        "ix_external_events_family_start", table_name="external_events_cache"
    )
    op.drop_table("external_events_cache")

    op.drop_table("event_cars")

    op.drop_index("ix_event_targets_status_retry", table_name="event_targets")
    op.drop_table("event_targets")

    op.drop_table("note_cars")

    op.drop_index("ix_note_labels_family_slug", table_name="note_labels")
    op.drop_table("note_labels")

    op.drop_index("ix_notes_family_assignee", table_name="notes")
    op.drop_index("ix_notes_family_pinned_updated", table_name="notes")
    op.drop_table("notes")

    op.drop_index("ix_events_family_assignee", table_name="events")
    op.drop_index("ix_events_family_start", table_name="events")
    op.drop_table("events")

    op.drop_index("ix_labels_family", table_name="labels")
    op.drop_table("labels")

    op.drop_index("ix_cars_family_status", table_name="cars")
    op.drop_table("cars")

    op.drop_table("calendar_sync_state")
    op.drop_table("google_tokens")

    op.drop_index("ix_members_family_status", table_name="members")
    op.drop_table("members")

    op.drop_index("ix_devices_family", table_name="devices")
    op.drop_table("devices")

    op.drop_table("family_preferences")
    op.drop_table("families")

    bind = op.get_bind()
    for enum_name in (
        "event_target_sync_status",
        "car_status",
        "google_token_status",
        "member_status",
    ):
        bind.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))


def _table_exists(bind, name: str) -> bool:
    insp = sa.inspect(bind)
    return insp.has_table(name)
