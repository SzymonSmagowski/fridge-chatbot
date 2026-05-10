"""Voice graph — terse spoken assistant for the LiveKit voice transport.

Compiled by `build_voice_graph(...)` and consumed by LiveKit Agents via
`langchain.LLMAdapter(graph=compiled_graph)`. Topology designed by the
AIEngineer pass — see `.claude/designs/fridge-chatbot-architecture/llm-graph.drawio` and
`.claude/designs/fridge-chatbot-architecture/voice-steering.md`.

Three-node `StateGraph(VoiceState)`:

- **assistant** — returns `Command(goto=...)` to dynamically route. If the
  model emitted tool_calls → goto "tools". If the model emitted a clarifying
  question (no tool_calls, content ends with "?") → goto "finalize_pending"
  with the question text staged into `pending_action`. Otherwise → goto END.
- **tools** — executes @tool calls, returns ToolMessages, loops back to
  assistant for the spoken summary turn.
- **finalize_pending** — terminator for the current turn after a clarification
  question. The next user utterance arrives as a fresh invocation through the
  checkpointer-backed thread state, with `pending_action` still populated so
  the LLM can pick the slot-fill back up.

Why `Command(goto=...)` and not `add_conditional_edges` like chat_graph: voice
needs the routing decision to depend on the *content* of the assistant's
response, not just on its tool_calls field. `Command` lets the assistant node
both *update state* and *route*, atomically.

Why no `interrupt()`: the standard LangGraph human-in-the-loop primitive blocks
the graph and requires `Command(resume=...)` to continue. LiveKit feeds the
next utterance as a fresh `HumanMessage` invocation — there's no resume
channel, and blocking would break barge-in.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.orm import sessionmaker

from src.core.context import current_actor
from src.core.settings import Settings
from src.llm_graphs.shared.locale import detect_locale
from src.llm_graphs.shared.prompts import Locale, build_prompt
from src.llm_graphs.shared.tools import build_tools
from src.services.llm_factory import LLMFactory
from src.services.logger import get_logger

logger = get_logger("voice_graph")


class VoiceState(MessagesState):
    """MessagesState + one slot for in-flight slot-filling intents + locale.

    `pending_action` carries forward across turns via the LangGraph checkpointer
    so the assistant can resume a multi-turn flow ("add an event" → "when?" →
    "Saturday at 3" → tool call) without losing the original intent.

    `locale` is set by the entry node `detect_language` per turn and read by
    the assistant node when assembling the system prompt. Per-turn detection
    means a household can code-switch (en→pl→en) and the agent follows.
    """

    pending_action: dict | None
    locale: Locale


def _looks_like_clarification(text: str) -> bool:
    """Heuristic: assistant emitted no tool call but is asking the user something.

    Cheap; refine later if false positives bite (e.g. add a structured marker
    the prompt asks the model to emit).
    """
    if not text:
        return False
    stripped = text.strip()
    return stripped.endswith("?") or stripped.endswith("？")


def _trunc(text: str, n: int = 120) -> str:
    """Truncate a long string for log lines. Keeps newlines visible as `\\n`
    so multi-line content stays one log entry. The voice path runs at
    ~10 turns/min — bounding log size keeps the console readable."""
    if text is None:
        return ""
    s = str(text).replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 1] + "…"


def _summarize_messages(messages: list, n_recent: int = 4) -> str:
    """Compact summary of the last `n_recent` messages in `state['messages']`,
    used by the voice graph's diagnostic logging. Format:
        [Human] dodaj mleko… | [AI] (tool_calls=add_note) | [Tool] {ok:true,…}
    """
    out: list[str] = []
    for m in messages[-n_recent:]:
        cls = type(m).__name__.replace("Message", "")
        text = getattr(m, "content", "") or ""
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            names = ",".join(c.get("name", "?") for c in tool_calls)
            out.append(f"[{cls} tool_calls={names}]")
        else:
            out.append(f"[{cls}] {_trunc(text)}")
    return " | ".join(out)


def build_voice_graph(
    settings: Settings,
    *,
    family_id: UUID | None = None,
    session_factory: sessionmaker | None = None,
    checkpointer: Any | None = None,
    voice_locale: str = "auto",
    end_session_signal: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile the voice channel's StateGraph.

    Both `family_id` and `session_factory` are required for the tool-bound
    path. Without them the graph still compiles but has no tools — useful for
    smoke tests and CI without a real DB.

    `checkpointer` (optional, e.g. PostgresSaver from langgraph-postgres) is
    what makes `pending_action` survive across user turns. Pass `None` for
    in-memory single-turn use.

    `voice_locale` is the household's default language preference from
    `family_preferences.voice_locale` (`'auto' | 'en' | 'pl'`). Drives the
    seed locale for the `detect_language` node — see the chat_graph.py
    docstring on that node for the auto-vs-pinned logic. Read once at
    graph construction; the voice_worker rebuilds the graph per session so
    a settings change takes effect on the next session.
    """
    base_llm = LLMFactory.create_llm(settings, temperature=settings.DEFAULT_TEMPERATURE)
    tools: list[Any] = []
    if family_id is not None and session_factory is not None:
        # Stamp every tool invocation in this graph as voice-originated so the
        # service layer broadcasts get tagged correctly. ContextVars are
        # async-safe and inherited by spawned tasks (per shared/tools.py).
        current_actor.set("voice-tool")
        tools = build_tools(
            family_id=family_id,
            session_factory=session_factory,
            settings=settings,
            end_session_signal=end_session_signal,
        )
        llm = base_llm.bind_tools(tools)
    else:
        llm = base_llm

    def detect_language(state: VoiceState) -> dict:
        """Entry node — sets `state["locale"]`. Same auto-vs-pinned logic
        as `chat_graph.detect_language` (see that docstring for the
        rationale). Heuristic-only — no LLM round-trip — to keep the
        mic-stop → first-audio budget under 1.5s.
        """
        latest_user = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if latest_user is None:
            chosen = voice_locale if voice_locale in ("en", "pl") else "en"
            logger.info(
                "[voice-graph] detect_language: no user message yet, "
                "using seed locale=%s", chosen,
            )
            return {"locale": chosen}
        detected = detect_locale(str(latest_user.content))
        if voice_locale == "auto":
            chosen = detected
        elif detected == "pl":
            chosen = "pl"
        else:
            chosen = voice_locale
        logger.info(
            "[voice-graph] detect_language: pin=%s detected=%s → locale=%s "
            "from user_text=%r",
            voice_locale, detected, chosen, _trunc(str(latest_user.content)),
        )
        return {"locale": chosen}

    # Hard cap on tool-loop iterations. Real traffic finishes in 1-2; the
    # cap exists to bound a misbehaving model that loops forever (e.g. a
    # tool that always returns "tool error" can lure a stubborn LLM into
    # endless retries). Exceeding the cap returns whatever the LLM said
    # last as a final reply.
    _MAX_TOOL_LOOPS = 6

    async def _run_tools_internal(response: Any) -> list[ToolMessage]:
        """Execute every tool_call on `response` and return the resulting
        ToolMessages. Used inside the assistant node — these messages do
        NOT enter graph state, so LiveKit's langchain.LLMAdapter (which
        streams every state-message-add to TTS) never sees them."""
        out: list[ToolMessage] = []
        for call in getattr(response, "tool_calls", []) or []:
            fn = next((t for t in tools if t.name == call["name"]), None)
            if fn is None:
                logger.warning(
                    "[voice-graph] tool: unknown %r", call.get("name")
                )
                out.append(
                    ToolMessage(
                        tool_call_id=call["id"],
                        content=f"Unknown tool: {call['name']}",
                    )
                )
                continue
            args = call.get("args", {})
            logger.info(
                "[voice-graph] tool: %s args=%s",
                call.get("name"), _trunc(str(args)),
            )
            try:
                result = await fn.ainvoke(args)
                logger.info(
                    "[voice-graph] tool: %s ← %s",
                    call.get("name"), _trunc(str(result)),
                )
                out.append(
                    ToolMessage(tool_call_id=call["id"], content=str(result))
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[voice-graph] tool: %s raised %s",
                    call.get("name"), exc,
                )
                out.append(
                    ToolMessage(
                        tool_call_id=call["id"], content=f"Tool error: {exc}"
                    )
                )
        return out

    async def assistant(
        state: VoiceState,
    ) -> Command[Literal["finalize_pending", "__end__"]]:
        """Run the LLM↔tool dance entirely *inside* this node so the only
        thing that ever lands in graph state (and therefore ever streams
        through LiveKit's langchain.LLMAdapter to TTS) is the FINAL
        AIMessage with spoken text.

        Why this matters: LiveKit's adapter uses `stream_mode="messages"`
        which yields every message added to state during the run. With a
        classic `assistant ↔ tools` loop, that includes ToolMessage rows
        whose content is the tool's raw JSON return — the adapter would
        pipe that JSON straight into TTS. Collapsing the loop here means
        ToolMessages stay local to this function and never reach the
        adapter.

        Trade-off: we lose explicit `tools` and node-level visibility in
        graph diagrams. The internal loop logs every tool call so the
        debug surface stays the same; only the topology is flattened.
        """
        locale: Locale = state.get("locale", "en")
        system_prompt = build_prompt("voice", locale)
        # Working buffer: starts as the persisted history + current user
        # turn; intermediate AI(tool_calls) and ToolMessage rows append
        # here but never escape this function.
        working: list[Any] = (
            [SystemMessage(content=system_prompt)] + list(state["messages"])
        )
        logger.info(
            "[voice-graph] assistant→LLM: locale=%s history_count=%d tail=%s",
            locale, len(state["messages"]),
            _summarize_messages(state["messages"]),
        )

        response: Any = None
        for loop_n in range(_MAX_TOOL_LOOPS):
            response = await llm.ainvoke(working)
            tool_calls = getattr(response, "tool_calls", None) or []
            response_text = getattr(response, "content", "") or ""
            logger.info(
                "[voice-graph] assistant←LLM[%d]: tool_calls=%s text=%r",
                loop_n,
                [c.get("name") for c in tool_calls] if tool_calls else None,
                _trunc(response_text),
            )
            if not tool_calls:
                break  # final reply
            # Run tools, append to working buffer, loop. None of this is
            # ever returned to graph state.
            working.append(response)
            tool_msgs = await _run_tools_internal(response)
            working.extend(tool_msgs)
        else:
            logger.warning(
                "[voice-graph] assistant: exhausted %d tool loops without "
                "a final reply; emitting last AIMessage as-is",
                _MAX_TOOL_LOOPS,
            )

        response_text = getattr(response, "content", "") or ""
        if _looks_like_clarification(response_text):
            logger.info(
                "[voice-graph] assistant→finalize_pending: clarification "
                "question staged"
            )
            return Command(
                goto="finalize_pending",
                update={
                    "messages": [response],
                    "pending_action": {"awaiting": response.content},
                },
            )

        logger.info("[voice-graph] assistant→END: final reply")
        return Command(
            goto=END,
            update={"messages": [response], "pending_action": None},
        )

    async def finalize_pending(state: VoiceState) -> dict:
        """Terminator for the clarification turn.

        No-op at the message level — the assistant's question is already in
        state. Exists so the topology has an explicit landing node for the
        "awaiting more input" branch (improves diagram clarity + lets us add
        per-channel telemetry later without changing call sites).
        """
        return {}

    builder = StateGraph(VoiceState)
    builder.add_node("detect_language", detect_language)
    builder.add_node("assistant", assistant)
    builder.add_node("finalize_pending", finalize_pending)
    # No separate `tools` node — `assistant` runs the tool loop internally
    # so ToolMessage rows never enter graph state and never reach
    # LiveKit's langchain.LLMAdapter (which would otherwise stream their
    # raw JSON content to TTS via `stream_mode="messages"`).
    builder.add_edge(START, "detect_language")
    builder.add_edge("detect_language", "assistant")
    builder.add_edge("finalize_pending", END)

    return builder.compile(checkpointer=checkpointer)
