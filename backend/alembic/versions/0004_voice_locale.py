"""family_preferences.voice_locale for assistant default language

Revision ID: 0004_voice_locale
Revises: 0003_thread_summary
Create Date: 2026-05-09

Adds a household-level language preference to `family_preferences`. Values:

- `'auto'` (default) — agent detects language per turn from user input.
- `'en'` — agent defaults to English; user input still flips to Polish if it
  has unmistakable Polish characters/words (per
  `src/llm_graphs/shared/locale.py`).
- `'pl'` — symmetric with `'en'` for Polish-speaking households.

The seed-not-pin design is intentional: a Polish-speaking guest visiting an
English household should still get Polish replies, and vice versa. The
pinned setting determines what happens when input is *ambiguous*, not when
it's clearly the other language.

Read by:
- `parent_router.py` when constructing the chat graph per call.
- `voice_worker/worker.py` when starting an `AgentSession` (also drives the
  greeting language).
- `detect_language` node in both `chat_graph.py` and `voice_graph.py` as
  the seed locale.

Nullable + defaulted to `'auto'` so existing rows don't need a backfill.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_voice_locale"
down_revision: Union[str, Sequence[str], None] = "0003_thread_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "family_preferences",
        sa.Column(
            "voice_locale",
            sa.String(length=8),
            nullable=False,
            server_default="auto",
        ),
    )


def downgrade() -> None:
    op.drop_column("family_preferences", "voice_locale")
