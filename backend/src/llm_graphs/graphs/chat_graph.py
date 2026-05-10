"""Chat graph — LangGraph-compiled assistant for the text-chat channel.

Tools are bound when a session_factory + family_id are provided at construction
(see core/dependencies and parent_router). Without them the graph stays a pure
LLM call so existing behavior (and tests) keep passing.

When a `chat_streamer` + `thread_id` are passed to `astream`, each emitted
token is also published to the Redis channel `thread:{thread_id}:tokens` per
§7.7 so future horizontally-scaled subscribers can attach without protocol
changes.

History: this module was previously `src/llm_graphs/subgraphs/fridge_assistant/
fridge_assistant.py`. It moved here as part of the voice-steering split, where
a sibling `voice_graph.py` reuses the same tools (`shared/tools.py`) but
compiles a separate StateGraph optimized for terse spoken output. See
`.claude/designs/fridge-chatbot-architecture/voice-steering.md`.
"""
from __future__ import annotations

from typing import Any, AsyncIterator
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy.orm import sessionmaker
from typing_extensions import Annotated, TypedDict

from src.core.settings import Settings
from src.llm_graphs.shared.locale import detect_locale
from src.llm_graphs.shared.prompts import Locale, build_prompt
from src.services.chat_streaming import ChatStreamer
from src.services.llm_factory import LLMFactory
from src.services.logger import get_logger

logger = get_logger("chat_graph")


class ChatState(TypedDict):
    """Graph state. Adds `locale` to the standard MessagesState shape so the
    `assistant` node can render a locale-aware system prompt for each turn.

    The `messages` annotation `add_messages` is the same reducer LangGraph's
    built-in `MessagesState` uses — it appends/dedupes messages by id.
    `locale` has no reducer (defaults to "last value wins"), which is fine
    because only one node writes it (the `detect_language` entry node).
    """

    messages: Annotated[list, add_messages]
    locale: Locale


class ChatGraph:
    def __init__(
        self,
        settings: Settings,
        *,
        family_id: UUID | None = None,
        session_factory: sessionmaker | None = None,
        voice_locale: Locale | str = "auto",
    ) -> None:
        self.settings = settings
        self.family_id = family_id
        self.session_factory = session_factory
        # Default language pref from family_preferences. `'auto'` (default) →
        # the detect_language node uses the heuristic on every turn. `'en'`
        # / `'pl'` → those become the seed; the heuristic still flips on
        # clearly-the-other-language input. Stored as a plain string so we
        # don't have to cast at every read site.
        self.voice_locale: str = voice_locale
        base_llm = LLMFactory.create_llm(settings, temperature=settings.DEFAULT_TEMPERATURE)
        self.tools: list[Any] = []
        if family_id is not None and session_factory is not None:
            from src.llm_graphs.shared.tools import build_tools

            self.tools = build_tools(
                family_id=family_id,
                session_factory=session_factory,
                settings=settings,
            )
            self.llm = base_llm.bind_tools(self.tools)
        else:
            self.llm = base_llm
        self.graph = self._build_graph()

    def _build_graph(self):
        # Snapshot the seed locale at graph construction so the closure inside
        # `detect_language` doesn't have to read `self` per turn (and so the
        # behavior is stable for the lifetime of this graph instance).
        seed_locale = self.voice_locale

        def detect_language(state: ChatState):
            """Entry node — sets `state["locale"]`.

            Logic:
            - `voice_locale="auto"` → use the per-turn heuristic on the
              latest user message (the previous default).
            - `voice_locale="en"|"pl"` → seed with that, but if the
              heuristic detects the *other* language with high confidence
              (Polish diacritics or distinctive Polish words; the heuristic
              never returns `"pl"` on neutral input), let the heuristic
              override. This means a Polish-speaking guest at an English
              household still gets Polish replies, and vice versa.
            """
            latest_user = next(
                (
                    m for m in reversed(state["messages"])
                    if isinstance(m, HumanMessage)
                ),
                None,
            )
            if latest_user is None:
                # Pre-first-message: use the seed (en/pl) or fall back to en.
                return {"locale": seed_locale if seed_locale in ("en", "pl") else "en"}
            detected = detect_locale(str(latest_user.content))
            if seed_locale == "auto":
                return {"locale": detected}
            # Pinned mode: only let the heuristic override when it found
            # *Polish* signals (diacritics or word hints). The heuristic
            # never returns "pl" without strong evidence.
            if detected == "pl":
                return {"locale": "pl"}
            return {"locale": seed_locale}

        async def call_model(state: ChatState):
            locale: Locale = state.get("locale", "en")
            system_prompt = build_prompt("chat", locale)
            messages = [SystemMessage(content=system_prompt)] + state["messages"]
            response = await self.llm.ainvoke(messages)
            return {"messages": [response]}

        async def call_tools(state: ChatState):
            last = state["messages"][-1]
            tool_messages: list[ToolMessage] = []
            for call in getattr(last, "tool_calls", []) or []:
                fn = next((t for t in self.tools if t.name == call["name"]), None)
                if fn is None:
                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=call["id"],
                            content=f"Unknown tool: {call['name']}",
                        )
                    )
                    continue
                try:
                    result = await fn.ainvoke(call.get("args", {}))
                    tool_messages.append(
                        ToolMessage(tool_call_id=call["id"], content=str(result))
                    )
                except Exception as exc:  # noqa: BLE001
                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=call["id"], content=f"Tool error: {exc}"
                        )
                    )
            return {"messages": tool_messages}

        def needs_tools(state: ChatState) -> str:
            last = state["messages"][-1]
            tool_calls = getattr(last, "tool_calls", None)
            if tool_calls:
                return "tools"
            return END

        builder = StateGraph(ChatState)
        builder.add_node("detect_language", detect_language)
        builder.add_node("assistant", call_model)
        builder.add_edge(START, "detect_language")
        builder.add_edge("detect_language", "assistant")
        if self.tools:
            builder.add_node("tools", call_tools)
            builder.add_conditional_edges(
                "assistant", needs_tools, {"tools": "tools", END: END}
            )
            builder.add_edge("tools", "assistant")
        else:
            builder.add_edge("assistant", END)
        return builder.compile()

    async def astream(
        self,
        user_message: str,
        history: list | None = None,
        *,
        chat_streamer: ChatStreamer | None = None,
        thread_id: str | None = None,
    ) -> AsyncIterator[str]:
        prior = history or []
        state_messages = prior + [HumanMessage(content=user_message)]
        async for event in self.graph.astream_events(
            {"messages": state_messages}, version="v2"
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and isinstance(chunk, AIMessage) and chunk.content:
                    text = chunk.content
                    if chat_streamer and thread_id:
                        await chat_streamer.publish_token(
                            thread_id, {"type": "message", "content": text}
                        )
                    yield text


# Backward-compat alias: this class was named `FridgeAssistant` while it lived
# under `subgraphs/fridge_assistant/`. Aliasing keeps any lingering external
# reference (test docstrings, route comments) valid until they're cleaned up.
FridgeAssistant = ChatGraph
