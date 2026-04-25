"""Fridge Assistant — LangGraph subgraph with optional tool bindings.

Tools are bound when a session_factory + family_id are provided at construction
(see core/dependencies and parent_router). Without them the graph stays a pure
LLM call so existing behavior (and tests) keep passing.

When a `chat_streamer` + `thread_id` are passed to `astream`, each emitted
token is also published to the Redis channel `thread:{thread_id}:tokens` per
§7.7 so future horizontally-scaled subscribers can attach without protocol
changes.
"""
from __future__ import annotations

from typing import Any, AsyncIterator
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from sqlalchemy.orm import sessionmaker

from src.core.settings import Settings
from src.services.chat_streaming import ChatStreamer
from src.services.llm_factory import LLMFactory
from src.services.logger import get_logger

logger = get_logger("fridge_assistant")

SYSTEM_PROMPT = (
    "You are a helpful fridge assistant for a family. You help users figure out "
    "what to cook given the ingredients they mention, suggest recipes, warn about "
    "spoilage, answer food-storage questions, and manage the family's notes and "
    "calendar through your tools. Be concise, friendly, and practical."
)


class FridgeAssistant:
    def __init__(
        self,
        settings: Settings,
        *,
        family_id: UUID | None = None,
        session_factory: sessionmaker | None = None,
    ) -> None:
        self.settings = settings
        self.family_id = family_id
        self.session_factory = session_factory
        base_llm = LLMFactory.create_llm(settings, temperature=settings.DEFAULT_TEMPERATURE)
        self.tools: list[Any] = []
        if family_id is not None and session_factory is not None:
            from src.llm_graphs.subgraphs.fridge_assistant.tools import build_tools

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
        async def call_model(state: MessagesState):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
            response = await self.llm.ainvoke(messages)
            return {"messages": [response]}

        async def call_tools(state: MessagesState):
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

        def needs_tools(state: MessagesState) -> str:
            last = state["messages"][-1]
            tool_calls = getattr(last, "tool_calls", None)
            if tool_calls:
                return "tools"
            return END

        builder = StateGraph(MessagesState)
        builder.add_node("assistant", call_model)
        builder.add_edge(START, "assistant")
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
