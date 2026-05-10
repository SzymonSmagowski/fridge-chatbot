# llm_graphs

LangGraph orchestration layer. **Owned by `AIEngineer`** in the build pipeline — BackendDeveloper does not write to this tree. If a tool needs a new service method, AIEngineer flags it in its summary and BackendDeveloper adds it under `src/services/` in a follow-up step.

## Layout

The tree is organised by what stays the same across channels (`shared/`) vs what diverges per channel (`graphs/`):

```
llm_graphs/
├── parent_router.py     # Chat-channel dispatcher; consumed by routes/threads.py WS handler
├── graph_utils.py       # Generic LangGraph helpers (message pruning, summary extraction)
├── shared/              # Channel-agnostic — both graphs import from here
│   ├── tools.py         # @tool definitions, family-scoped via closure
│   └── prompts.py       # build_prompt(channel) — single source of truth for tone + constraints
└── graphs/              # One compiled StateGraph per channel
    ├── chat_graph.py    # ChatGraph — assistant ↔ tools loop, markdown OK, streamed token-by-token
    └── voice_graph.py   # build_voice_graph() — assistant + tools + finalize_pending,
                         # Command(goto=...) routing, terse spoken output
```

**Two transports, two graphs, one tool layer.** Chat enters here through `parent_router.py` (consumed by the chat WS handler in `routes/threads.py`). Voice enters through a separate process — `src/voice_worker/worker.py` — which wraps `voice_graph` in LiveKit's `langchain.LLMAdapter` and runs an `AgentSession`. Channel selection is **transport-driven**, never LLM-classified.

## Files

- `parent_router.py` — `ParentRouter` class. Receives a user message + thread UUID, persists it, loads conversation history, delegates to `ChatGraph`, streams tokens back via WebSocket callback, persists the reply. Used by the chat channel only.
- `graph_utils.py` — shared graph construction helpers (message pruning, summary extraction).
- `shared/tools.py` — `@tool` definitions: `list_notes`, `add_note`, `add_to_shopping_list`, `add_event`, `read_calendar_window`, `set_member_inactive`, `set_member_active`, `list_members`, `list_cars`, `add_car`. All close over `family_id` + `session_factory` at construction time and call into the family-scoped service layer. **Both** `chat_graph` and `voice_graph` import the same `build_tools()`. Mutating tools set `current_actor.set("chat-tool")` for the service-layer broadcast tag; `voice_graph` overrides this to `"voice-tool"` at construction time. ContextVars are async-safe — each `asyncio.Task` inherits a copy. **Mutating tools (`add_*`, `set_member_*`) are async** — they `await` the service methods directly so the service-layer Redis publish runs on the same event loop as the process-wide redis singleton. An earlier sync-via-`_run`-bridge implementation crashed with "Event loop is closed" on every chat-tool write; postmortem at `docs/features/chat-graph-bugfix-async-bridge.md`. Read-only tools stay sync. `list_notes` and `read_calendar_window` apply a tool-layer cap of 50 items + `truncated`/`total_count` envelope so the LLM context can't be flooded; the underlying REST API is uncapped.
- `shared/prompts.py` — `build_prompt(channel: Literal["chat", "voice"])` returns the full system prompt. Channel-agnostic family conventions (shared appliance, members are assignees, shopping list is a tagged note) are common; channel-specific constraints (markdown allowed for chat; ≤25-word plain-text for voice) are appended.
- `graphs/chat_graph.py` — `ChatGraph` class. `StateGraph(MessagesState)` with `assistant` node (LLM call with `build_prompt("chat")`) and conditional `tools` node, looping back. Pure-LLM mode when no `family_id` is passed (used by tests). Backward-compat alias `FridgeAssistant = ChatGraph`.
- `graphs/voice_graph.py` — `build_voice_graph(...)` returns a `CompiledStateGraph` for LiveKit's `langchain.LLMAdapter`. Three-node topology: `assistant` returns `Command(goto=...)` (to `tools`, `finalize_pending`, or `END`); `tools` loops back; `finalize_pending` terminates the current turn after a clarifying question. `VoiceState` adds a `pending_action: dict | None` slot that survives across turns via the LangGraph checkpointer (when one is passed). Topology designed by AIEngineer; rationale + diagram at `.claude/designs/fridge-chatbot-architecture/llm-graph.drawio`.

## Routing

`ParentRouter` is the entrypoint for the **chat** channel. It hard-instantiates `ChatGraph` per call (closing over `family_id`). The **voice** channel is dispatched by `src/voice_worker/worker.py`, a separate process — it does not go through `ParentRouter`. Channel selection is **transport-driven**, not LLM-classified.

Within `voice_graph`, follow-up question handling uses LangGraph 1.x's `Command(goto=..., update={...})` primitive returned from the `assistant` node. We deliberately avoided `interrupt()` (would block the worker process and break LiveKit's barge-in semantics) and avoided a classifier dispatch shape (would add an extra LLM hop, blowing the <1.5s mic-stop → first-audio budget).

## Adding a new graph

1. Create `graphs/my_graph.py` with a class that exposes `async def astream(user_message, history) -> AsyncIterator[str]` (or that returns a `CompiledStateGraph` directly if you're plugging it into LiveKit's `langchain.LLMAdapter`).
2. Import tools from `shared/tools.py`. **Do not define new tools inside the graph file** — single source of truth lives in `shared/`.
3. Wire the new channel into a transport: chat goes through `parent_router.py`; voice will go through `voice_worker/worker.py`.

## Topology diagram

AIEngineer maintains `.claude/designs/<app>-llm-graph.drawio` — a directed tree showing transport → graph → StateGraph nodes → tools. Regenerated on every AIEngineer run from the actual code. If you change this layer manually (e.g. quick fix), regenerate the diagram or the tree will drift from reality.
