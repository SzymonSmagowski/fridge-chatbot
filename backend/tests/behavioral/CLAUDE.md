# tests/behavioral

Behavioral suite for the **chat graph** (`src/llm_graphs/graphs/chat_graph.py`).
Each case asserts:

1. The expected `@tool` name(s) were invoked, in approximate order
2. A behavioral property of the final assistant message (substring / regex /
   length cap / language)
3. DB state changed (or didn't) as expected

## Opt-in only

```bash
poetry run pytest -m behavioral
```

The suite hits **real OpenAI** (gpt-4o-mini by default — see
`src/services/llm_factory.py`). Default `pytest` runs deselect the marker.
If `OPENAI_API_KEY` is missing the cases auto-skip rather than error.

## Source of truth

`docs/features/chat-graph-test-matrix.md` — the markdown matrix is the
human-reviewable source. This directory implements a representative subset
(currently 12 cases) that proves the harness compiles and assertions are
sensible. The full matrix is also pushed to the local Langfuse instance
under the dataset `chat-graph-behavioral` via the `langfuse-dataset` skill.

## Files

- `conftest.py` — `behavioral_family` factory (real Postgres family +
  preferences), `make_member` / `make_car` factories, real `ChatGraph`
  bound to that family, `run_turn` async helper that captures
  `(final_text, tool_calls, tool_args, history)` from one user prompt.
- `test_chat_graph_behavior.py` — the case implementations. New cases go
  here, indexed by the matrix `id` in the docstring.

## Adding a case

1. Add the row to `docs/features/chat-graph-test-matrix.md`.
2. Add a function `test_<id>` to `test_chat_graph_behavior.py` that uses
   `run_turn`, asserts on `tool_calls`, asserts on `final_text` via
   `text_matches`, asserts on DB state via `_count(db, Model, family_id)`.
3. Re-push the matrix: `poetry run python scripts/langfuse_dataset.py push docs/features/chat-graph-test-matrix.md`.

## Known gaps

The 12-case subset does not yet implement:

- Slot-fill multi-turn cases (`ae-no-time`) — needs the `run_turn` helper to
  accept a `history` arg and chain turns.
- Bilingual cases — requires the `lang=pl` predicate to be more rigorous than
  diacritic-counting.
- All P0/P1 rows — the orchestrator brief asked for ~10 cases to validate
  the harness; full coverage is a follow-up pass.
