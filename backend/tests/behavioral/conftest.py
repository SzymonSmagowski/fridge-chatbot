"""Fixtures for the chat-graph behavioral suite.

These tests intentionally hit the real OpenAI API (gpt-4o-mini) — they are
gated by the `behavioral` marker so they don't run in the default `pytest`
invocation. Run with:

    poetry run pytest -m behavioral

Cost discipline: gpt-4o-mini is ~$0.15 / 1M input tokens, so even running
all 75 cases costs single-digit cents per pass. Still, the suite is opt-in.

Each test gets:
- A real `ChatGraph` bound to a real Postgres family with a real session
  factory and a real Redis-backed `ChatStreamer`.
- A `make_member` / `make_car` / `make_note` factory to seed fixtures.
- An `astream_with_capture` helper that runs a single user prompt through
  the graph and returns `(final_text, tool_calls, raw_events)` so each
  case can assert tool selection AND response text AND DB state.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session, sessionmaker

from src.core.settings import Settings
from src.llm_graphs.graphs.chat_graph import ChatGraph
from src.models import (
    Car,
    CarStatus,
    Family,
    FamilyPreferences,
    Member,
    MemberStatus,
)


# ---------------------------------------------------------------------------
# Skip/guard the suite when no real OPENAI_API_KEY is available — opt-in.
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(config, items):
    """Auto-skip behavioral tests if the OpenAI key is missing.

    Behavioral tests are also gated by the `behavioral` marker (which makes
    them opt-in via `-m behavioral`); this is a second guard so accidentally
    running them without a key fails loud with a useful skip reason.
    """
    skip_no_key = pytest.mark.skip(
        reason="OPENAI_API_KEY not set — behavioral suite needs real LLM calls"
    )
    for item in items:
        if "behavioral" in item.keywords and not os.getenv("OPENAI_API_KEY"):
            item.add_marker(skip_no_key)


# ---------------------------------------------------------------------------
# Test settings — overrides the default test_settings to ensure the real
# OpenAI key flows through. Reads from the host environment, NOT the test
# defaults that wipe OPENAI_API_KEY to "".
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def behavioral_settings(test_settings: Settings) -> Settings:
    real_key = os.getenv("OPENAI_API_KEY", "")
    if not real_key:
        return test_settings
    cloned = test_settings.model_copy(update={"OPENAI_API_KEY": real_key})
    return cloned


# ---------------------------------------------------------------------------
# Family-with-fixtures factory. Each test seeds one family and gets a
# helper to add members, cars, notes.
# ---------------------------------------------------------------------------


@dataclass
class BehavioralFamily:
    family_id: UUID
    members: dict[str, Member] = field(default_factory=dict)
    cars: dict[str, Car] = field(default_factory=dict)


@pytest.fixture
def behavioral_family(db: Session) -> BehavioralFamily:
    fam = Family(name="Behavioral Test Family", timezone="Europe/Warsaw")
    db.add(fam)
    db.flush()
    db.add(
        FamilyPreferences(
            family_id=fam.id,
            sync_interval_sec=300,
            auto_create_shopping_list=True,
        )
    )
    db.commit()
    db.refresh(fam)
    return BehavioralFamily(family_id=fam.id)


@pytest.fixture
def make_member(db: Session, behavioral_family: BehavioralFamily):
    """Factory: add a member to the behavioral family by name."""

    def _make(
        name: str, *, color: str = "#FF8800", status: MemberStatus = MemberStatus.active
    ) -> Member:
        member = Member(
            family_id=behavioral_family.family_id,
            name=name,
            color=color,
            status=status,
            is_setup_owner=False,
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        behavioral_family.members[name] = member
        return member

    return _make


@pytest.fixture
def make_car(db: Session, behavioral_family: BehavioralFamily):
    def _make(
        name: str, *, year: int | None = None, color_label: str | None = None
    ) -> Car:
        car = Car(
            family_id=behavioral_family.family_id,
            name=name,
            year=year,
            color_label=color_label,
            status=CarStatus.active,
        )
        db.add(car)
        db.commit()
        db.refresh(car)
        behavioral_family.cars[name] = car
        return car

    return _make


@pytest.fixture
def make_note(db: Session, behavioral_family: BehavioralFamily):
    """Factory: seed a plain note (no labels) attached to the behavioral family."""
    from src.models import Note

    def _make(content: str, *, pinned: bool = False) -> Note:
        note = Note(
            family_id=behavioral_family.family_id,
            content=content,
            pinned=pinned,
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note

    return _make


@pytest.fixture
def make_note_with_label(db: Session, behavioral_family: BehavioralFamily):
    """Factory to seed a note already tagged with a label slug.

    Used to reproduce the "shopping list already exists" path and any other
    label-driven cases.
    """
    from src.models import Label, Note, NoteLabel

    def _make(content: str, label_slug: str, *, pinned: bool | None = None) -> Note:
        existing = (
            db.query(Label)
            .filter(
                Label.family_id == behavioral_family.family_id,
                Label.slug == label_slug,
            )
            .first()
        )
        if existing is None:
            db.add(
                Label(
                    family_id=behavioral_family.family_id,
                    slug=label_slug,
                    display_name=label_slug.replace("-", " ").title(),
                )
            )
            db.flush()
        if pinned is None:
            pinned = label_slug == "shopping-list"
        note = Note(
            family_id=behavioral_family.family_id,
            content=content,
            pinned=pinned,
        )
        db.add(note)
        db.flush()
        db.add(
            NoteLabel(
                note_id=note.id,
                family_id=behavioral_family.family_id,
                label_slug=label_slug,
            )
        )
        db.commit()
        db.refresh(note)
        return note

    return _make


@pytest.fixture
def disable_auto_shopping_list(db: Session, behavioral_family: BehavioralFamily):
    """Toggle off the auto_create_shopping_list family preference for this test."""
    from src.models import FamilyPreferences

    prefs = (
        db.query(FamilyPreferences)
        .filter(FamilyPreferences.family_id == behavioral_family.family_id)
        .first()
    )
    if prefs is not None:
        prefs.auto_create_shopping_list = False
        db.commit()
    return prefs


# ---------------------------------------------------------------------------
# ChatGraph + capture helper
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_redis_singleton():
    """Reset the process-wide Redis client between tests.

    Each behavioral test runs on its own asyncio event loop (pytest-asyncio
    `loop_scope="function"` default), but `redis_service._client` is a
    module-level singleton bound to whichever loop first instantiated it.
    Re-using a client across loops raises "Event loop is closed" on the
    next publish, surfacing as a confusing tool error inside add_event /
    add_to_shopping_list. Resetting it pre-test forces a rebuild on the
    current loop.
    """
    from src.services import redis_service as _rs

    _rs._client = None
    yield
    _rs._client = None


@pytest.fixture
def chat_graph(
    behavioral_settings: Settings,
    behavioral_family: BehavioralFamily,
    session_factory: sessionmaker,
) -> ChatGraph:
    return ChatGraph(
        behavioral_settings,
        family_id=behavioral_family.family_id,
        session_factory=session_factory,
    )


@dataclass
class GraphRun:
    final_text: str
    tool_calls: list[str]
    """Names of tools the assistant invoked, in order."""
    tool_args: list[dict[str, Any]]
    """Args passed to each tool, parallel to tool_calls."""
    history: list[Any]
    """The full message history at the end of the run (HumanMessage,
    AIMessage, ToolMessage…). Useful for asserting clarifying questions."""


@pytest_asyncio.fixture
async def run_turn(chat_graph: ChatGraph):
    """Run a single user turn through the graph and capture all the bits
    a behavioral assertion might want to look at."""

    async def _run(user_message: str, history: list | None = None) -> GraphRun:
        prior = history or []
        state_messages = prior + [HumanMessage(content=user_message)]

        # Use the underlying compiled graph directly so we capture the
        # complete final state — astream() only yields tokens, which loses
        # the tool-call list and final ToolMessages.
        final_state = None
        async for event in chat_graph.graph.astream_events(
            {"messages": state_messages}, version="v2"
        ):
            if event["event"] == "on_chain_end" and event.get("name") == "LangGraph":
                final_state = event["data"].get("output")

        if final_state is None:
            # Fallback: invoke once and read the state directly.
            final_state = await chat_graph.graph.ainvoke(
                {"messages": state_messages}
            )

        messages = final_state.get("messages", [])
        tool_calls: list[str] = []
        tool_args: list[dict[str, Any]] = []
        for m in messages:
            calls = getattr(m, "tool_calls", None) or []
            for c in calls:
                tool_calls.append(c.get("name", ""))
                tool_args.append(c.get("args", {}))

        # Final assistant text = last AIMessage content, ignoring tool-call
        # AIMessages whose content is empty.
        final_text = ""
        for m in reversed(messages):
            if isinstance(m, AIMessage) and m.content:
                final_text = m.content if isinstance(m.content, str) else str(m.content)
                break

        return GraphRun(
            final_text=final_text,
            tool_calls=tool_calls,
            tool_args=tool_args,
            history=messages,
        )

    return _run


# ---------------------------------------------------------------------------
# Tiny assertion helpers — kept here so each test reads cleanly.
# ---------------------------------------------------------------------------


def text_matches(text: str, predicate: str) -> bool:
    """Tiny matcher language: predicates from the matrix.

    - `substr=foo`             → case-insensitive substring
    - `substr=(a|b|c)`         → any of the alternates as a case-insensitive substring
    - `match=(a|b|c)`          → any regex pattern in the alternation matches
    - `len<=N`                 → text length cap
    - `lang=pl`                → at least 1 Polish-only diacritic in the reply
                                 (cheap heuristic; behavioral suite OK with it)
    """
    text_lc = text.lower()

    if predicate.startswith("substr="):
        needle = predicate[len("substr=") :].lower().strip()
        # Allow alternation form `substr=(a|b|c)` as a sugar over substring tests.
        if needle.startswith("(") and needle.endswith(")"):
            inner = needle[1:-1]
            alternates = [a.strip() for a in inner.split("|") if a.strip()]
            return any(a in text_lc for a in alternates)
        return needle in text_lc
    if predicate.startswith("match="):
        pattern = predicate[len("match=") :]
        return bool(re.search(pattern, text_lc))
    if predicate.startswith("len<="):
        cap = int(predicate[len("len<=") :])
        return len(text) <= cap
    if predicate == "lang=pl":
        # First cheap signal: any Polish-only diacritic.
        if any(ch in text_lc for ch in "ąćęłńóśźż"):
            return True
        # Diacritic-free Polish stop-words / function words. Polish replies
        # without diacritics are rare but happen for short answers like
        # "Mamy 1 aktywne auto" or "W rodzinie jest obecnie: Anna." We look
        # for at least one of these common Polish tokens as a backup signal.
        polish_tokens = (
            " mamy ", " jest ", " obecnie ", " rodzin", " auto",
            " samoch", " dodał", " dodan", " zapis", " notat",
            " mleko", " chleb", " kupić", " kupi", " jak ", " nie ",
            " dla ", " masz ", " masz?", " w rodz", " moja ", " twoja ",
            " ciebie", " czy ", " już ",
        )
        padded = " " + text_lc + " "
        return any(tok in padded for tok in polish_tokens)
    raise ValueError(f"Unknown predicate: {predicate}")
