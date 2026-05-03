# llm_graphs

LangGraph orchestration layer. **Owned by `AIEngineer`** in the build pipeline — BackendDeveloper does not write to this tree. If a tool needs a new service method, AIEngineer flags it in its summary and BackendDeveloper adds it under `src/services/` in a follow-up step.

## Files

- `parent_router.py` — `ParentRouter` class. Receives a user message + thread UUID, persists it, loads conversation history, delegates to a subgraph, streams tokens back via WebSocket callback, persists the reply.
- `graph_utils.py` — shared graph construction helpers.
- `subgraphs/` — one directory per capability.

## Subgraphs

Each subgraph is a self-contained `StateGraph`. Current subgraphs:

| Directory | Class | Notes |
|-----------|-------|-------|
| `subgraphs/fridge_assistant/` | `FridgeAssistant` | Single-node graph; LLM + system prompt. Streams via `astream_events`. |

## Routing

`ParentRouter` currently hard-routes all messages to `FridgeAssistant`. When multiple subgraphs exist, route on `use_case` field or add a classifier node.

## Adding a new subgraph

1. Create `subgraphs/my_feature/my_feature.py` with a class that exposes `async def astream(user_message, history) -> AsyncIterator[str]`.
2. Instantiate it in `ParentRouter.__init__`.
3. Add routing logic in `ParentRouter.astream_response`.

## Topology diagram

AIEngineer maintains `.claude/designs/<app>-llm-graph.drawio` — a directed tree showing ParentRouter → subgraphs → StateGraph nodes → tools. Regenerated on every AIEngineer run from the actual code. If you change this layer manually (e.g. quick fix), regenerate the diagram or the tree will drift from reality.
