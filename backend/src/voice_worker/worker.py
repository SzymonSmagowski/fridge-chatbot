"""LiveKit Agents worker — voice transport for the fridge chatbot.

Runs as a separate process, NOT inside the FastAPI event loop. Connects out to
the LiveKit server (devcontainer: `ws://livekit-server:7880`), waits for room
dispatches, and runs one `AgentSession` per joined room.

Pipeline per turn (when a participant speaks):
    mic → Silero VAD → OpenAI Whisper STT → langchain.LLMAdapter(voice_graph)
        → OpenAI TTS → speaker.

The voice_graph is the canonical brain — same tools as the chat path, terser
prompt, three-node `Command(goto=...)` topology for multi-turn slot filling.
See `src/llm_graphs/graphs/voice_graph.py` and the implementation plan at
`.claude/designs/fridge-chatbot-architecture/voice-steering.md`.

## Run locally

```bash
cd apps/fridge-chatbot/backend
poetry run python -m src.voice_worker.worker dev
```

The `dev` subcommand registers the worker against the LiveKit dev server and
streams logs to stdout. Use the LiveKit Sandbox or `@livekit/components-react`
playground to join the room and exercise the loop.

## Required env vars

- `OPENAI_API_KEY` — Whisper + gpt-4o-mini + tts-1
- `LIVEKIT_URL`   — defaults to `ws://livekit-server:7880` from compose
- `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — `devkey` / `secret` in dev

## Family resolution

The room name encodes the family scope: `<prefix>-<family-uuid>`, e.g.
`fridge-3f1c…b2`. The backend mints the JWT with `room_join` grants for that
exact room (see `routes/livekit_token.py`), so a kiosk cannot join a different
family's room even if it tampers with the name. The worker parses the UUID
back out of the room name on dispatch. Without a parseable suffix the worker
logs an error and ends the session — there is no "default" family.

We considered routing via room metadata (originally specced in the impl plan),
but room metadata can only be set by an admin connection — that means a
backend roundtrip on every kiosk join *just* to set metadata. Encoding into
the room name removes that trip and keeps the JWT room grant as the single
authoritative scoping primitive.
"""
from __future__ import annotations

import logging
from uuid import UUID

import asyncio

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli
from livekit.plugins import langchain, openai, silero

from src.core.family_events import family_event_payload
from src.core.settings import Settings
from src.db.shared_engine import get_session_factory
from src.llm_graphs.graphs.voice_graph import build_voice_graph
from src.services.chat_streaming import ChatStreamer
from src.services.logger import get_logger
from src.services.redis_service import get_redis_client

logger = get_logger("voice_worker")


# Greeting spoken by the agent the moment the LiveKit session is live, so
# the user hears confirmation that the fridge picked them up. Keyed on the
# resolved locale; `'auto'` falls back to English (we don't yet know what
# language the user will speak, and English is the safer default for the
# kiosk's targeted households). Kept short — Siri-style, not chatty.
_VOICE_GREETINGS = {
    "en": "Yes, I'm listening.",
    "pl": "Tak, słucham.",
}


def _greeting_for(voice_locale: str) -> str:
    return _VOICE_GREETINGS.get(voice_locale, _VOICE_GREETINGS["en"])


def _resolve_voice_thread_id(session_factory, family_id: UUID):
    """Find or create the thread that voice transcripts get saved to.

    Logic: pick the family's most recent thread (mirrors the chat tab's
    auto-resolution in `chat-view.tsx`) so voice and chat conversations
    interleave in one history. If none exists, create a default thread
    against the family's first paired device's shadow user. Returns the
    thread's UUID (the FK used by `messages.thread_id`).

    Returns `None` if the family has no devices (shouldn't happen — a
    family with an active voice session must have a paired device, but
    we tolerate it so a stray voice session never crashes the worker).
    """
    from datetime import datetime
    from src.models.database import Thread
    from src.models.family import Device

    with session_factory() as db:
        device = (
            db.query(Device)
            .filter(Device.family_id == family_id, Device.shadow_user_id.isnot(None))
            .order_by(Device.paired_at.asc())
            .first()
        )
        if device is None:
            logger.warning(
                "no paired device with shadow_user found for family %s; "
                "voice transcripts won't be persisted",
                family_id,
            )
            return None

        thread = (
            db.query(Thread)
            .filter(Thread.user_id == device.shadow_user_id)
            .order_by(Thread.updated_at.desc())
            .first()
        )
        if thread is None:
            thread = Thread(
                user_id=device.shadow_user_id, title="Fridge chat",
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)
            logger.info(
                "created voice thread %s for family %s shadow_user %s",
                thread.thread_id, family_id, device.shadow_user_id,
            )
        return thread.thread_id


async def _save_voice_message(
    session_factory,
    streamer: ChatStreamer,
    family_id: UUID,
    thread_id,
    role: str,
    content: str,
) -> None:
    """Persist a voice transcript to the messages table and broadcast a
    family event so any subscriber (e.g. the chat tab's history view, once
    that listens for thread updates) can pick up the new message live.

    Best-effort: a failure here logs and returns. Voice should never go
    silent because saving a transcript hiccupped.
    """
    from src.models.database import Message

    if not content or thread_id is None:
        return
    try:
        with session_factory() as db:
            msg = Message(
                thread_id=thread_id, role=role, content=content, type="message"
            )
            db.add(msg)
            db.commit()
        # Family event so future subscribers can refresh the chat history
        # view in real time. The chat tab's runtime doesn't yet listen for
        # this — voice messages still appear on tab reload — but emitting
        # the event keeps the architecture push-on-change consistent.
        await streamer.publish_family_event(
            family_id,
            family_event_payload(
                type="thread_message.created",
                entity="messages",
                id=thread_id,
                actor="voice-tool",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "failed to persist voice transcript role=%s family=%s: %s",
            role, family_id, exc,
        )


def _load_voice_locale(session_factory, family_id: UUID) -> str:
    """Read `family_preferences.voice_locale` for this family. Run once at
    session start — the family's setting is fixed for the duration of the
    LiveKit room. Falls back to 'auto' on missing row or transient error so
    the voice path keeps working even if prefs are unreachable.
    """
    from src.models.family import FamilyPreferences

    try:
        with session_factory() as db:
            prefs = (
                db.query(FamilyPreferences)
                .filter(FamilyPreferences.family_id == family_id)
                .first()
            )
            return prefs.voice_locale if prefs else "auto"
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "voice_locale lookup failed for family %s: %s; defaulting to auto",
            family_id,
            exc,
        )
        return "auto"


def _family_id_from_room_name(name: str | None) -> UUID | None:
    """Parse the family UUID out of a room name shaped `<prefix>-<uuid>`.

    The prefix is informational and may contain hyphens itself, so we anchor
    on the *trailing* 36-char UUID instead of splitting on `-`.
    """
    if not name or len(name) < 36:
        return None
    try:
        return UUID(name[-36:])
    except ValueError:
        logger.warning("Room name %r has no parseable trailing UUID", name)
        return None


async def entrypoint(ctx: JobContext) -> None:
    settings = Settings()
    if not settings.OPENAI_API_KEY:
        logger.error(
            "OPENAI_API_KEY is not set; voice worker cannot start STT/TTS. "
            "Set it in apps/fridge-chatbot/backend/.env."
        )
        return

    family_id = _family_id_from_room_name(ctx.room.name)
    if family_id is None:
        logger.error(
            "Room %s has no resolvable family_id in name; session aborted",
            ctx.room.name,
        )
        return

    session_factory = get_session_factory(settings)
    voice_locale = _load_voice_locale(session_factory, family_id)
    voice_thread_id = _resolve_voice_thread_id(session_factory, family_id)
    # Event the `end_session` tool sets when the LLM decides the user is
    # done. The watcher coroutine below waits on this event and closes
    # the LiveKit session after a short grace window so the goodbye TTS
    # has time to finish playing.
    end_session_signal = asyncio.Event()
    voice_graph = build_voice_graph(
        settings=settings,
        family_id=family_id,
        session_factory=session_factory,
        voice_locale=voice_locale,
        end_session_signal=end_session_signal,
    )

    # Streamer is shared across all transcript-persistence calls below; reuses
    # the process-wide async Redis client (singleton in redis_service).
    streamer = ChatStreamer(get_redis_client(settings))

    # The openai plugin reads OPENAI_API_KEY from os.environ by default; we
    # thread it through Settings instead so the worker stays consistent with
    # the rest of the backend (one .env, one Settings class). LangGraph's LLM
    # is constructed via LLMFactory inside build_voice_graph and already gets
    # the key the same way.
    # When the household has pinned a specific language, give Whisper the
    # hint — it's catastrophically biased toward English without it. We saw
    # "Stwórz mi nową notatkę" land as "Stroke me now on tatka." in the
    # auto-language path. With `language="pl"` it transcribes correctly.
    # `auto` mode (default) leaves Whisper's auto-detect alone.
    stt_kwargs: dict = {
        "model": "whisper-1",
        "api_key": settings.OPENAI_API_KEY,
    }
    if voice_locale in ("en", "pl"):
        stt_kwargs["language"] = voice_locale

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(**stt_kwargs),
        llm=langchain.LLMAdapter(graph=voice_graph),
        # `tts-1` is OpenAI's older but well-supported TTS model. We tried
        # `gpt-4o-mini-tts` (officially multilingual, better Polish) but the
        # LiveKit Agents `openai.TTS` plugin appears to silently produce no
        # audio for that model — both the greeting and assistant replies
        # came out as dead air with no error logged. Until the plugin
        # supports the newer model, `tts-1` is the safe default. Polish
        # output through `tts-1` voices has a noticeable English accent
        # but is intelligible. Voice spec §Localization tracks the eventual
        # multilingual upgrade.
        tts=openai.TTS(
            model="tts-1",
            voice="nova",
            api_key=settings.OPENAI_API_KEY,
        ),
    )

    # Agent is the LiveKit-side identity that joins the room as a participant.
    # The actual behavior — system prompt, tools, routing — lives in the
    # voice_graph above; the Agent's instructions field is intentionally left
    # blank so the graph's prompt is the single source of truth for behavior.
    await session.start(
        agent=Agent(instructions=""),
        room=ctx.room,
    )

    # Persist user transcripts + agent replies into the family's chat thread
    # so voice and chat conversations share one history surface. LiveKit emits
    # `conversation_item_added` once a turn (user or assistant) is complete;
    # we extract the role + text and dispatch to a background coroutine so
    # the DB write never blocks the audio loop.
    @session.on("conversation_item_added")
    def _on_conversation_item(event):  # pragma: no cover — runtime-only path
        item = getattr(event, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None)
        text = (
            getattr(item, "text_content", None)
            or getattr(item, "content", None)
            or ""
        )
        if isinstance(text, list):
            text = " ".join(str(p) for p in text if isinstance(p, str)).strip()
        if not isinstance(text, str):
            text = str(text)
        # LiveKit's history can include "system" turns and tool messages we
        # don't want in the user-facing chat thread.
        if role not in ("user", "assistant") or not text.strip():
            return
        asyncio.create_task(
            _save_voice_message(
                session_factory,
                streamer,
                family_id,
                voice_thread_id,
                role,
                text.strip(),
            )
        )

    # Speak a short confirmation as soon as the session is live so the user
    # knows the fridge picked them up. `auto` mode greets in English — we
    # haven't heard the user yet, so we don't know which language to use;
    # the per-turn `detect_language` node takes over from the first user
    # utterance. If the household has pinned `pl`, we greet in Polish
    # immediately.
    #
    # `allow_interruptions=False` is critical here: by the time `session.start()`
    # returns, the LiveKit room has been open for a couple of seconds, so the
    # user may already be speaking ("Hey Jarvis, what's …"). With interruption
    # allowed, the still-incoming user audio cancels the greeting before it
    # plays. Forcing it through guarantees the user gets the audible "I'm
    # listening" cue even if they jumped straight into a question.
    greeting = _greeting_for(voice_locale)
    try:
        await session.say(greeting, allow_interruptions=False)
    except Exception as exc:  # noqa: BLE001
        # Greeting is a nice-to-have. If TTS fails (rare — model down,
        # cancellation race), don't tear the session down over it.
        logger.warning("voice greeting failed: %s", exc)

    logger.info(
        "Voice session started: room=%s family_id=%s locale=%s",
        ctx.room.name,
        family_id,
        voice_locale,
    )

    # Watch for an explicit end-of-session signal from the LLM (the
    # `end_session` tool). When it fires, give the goodbye TTS ~3s to
    # play, then publish a family event the kiosk listens for + close
    # the room.
    #
    # Why the family event: relying on LiveKit's participant-disconnect
    # semantics is unreliable from the kiosk client's perspective —
    # `session.aclose()` removes the agent participant but doesn't
    # always propagate to `useVoiceAssistant().agent === null` in
    # @livekit/components-react@2.9. Publishing an explicit
    # `voice_session.ended` event over our existing family-events WS
    # gives the frontend a deterministic signal: when it arrives, close
    # the overlay. This works regardless of LiveKit's internal state
    # transitions.
    async def _watch_end_signal() -> None:
        await end_session_signal.wait()
        logger.info(
            "[voice] end_session signaled — closing room %s in 3s "
            "(grace window for goodbye TTS to finish)",
            ctx.room.name,
        )
        await asyncio.sleep(3.0)
        # Publish before aclose so the kiosk sees the signal even if
        # session teardown blocks or errors.
        try:
            await streamer.publish_family_event(
                family_id,
                family_event_payload(
                    type="voice_session.ended",
                    entity="voice_session",
                    id=ctx.room.name,
                    actor="voice-agent",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("publish voice_session.ended failed: %s", exc)
        try:
            await session.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("session.aclose() failed: %s", exc)

    asyncio.create_task(_watch_end_signal())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
