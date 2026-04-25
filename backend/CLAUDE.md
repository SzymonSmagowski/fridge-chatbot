# fridge-chatbot / backend

Python/FastAPI/LangGraph backend. Baseline template for all future Python backends in this monorepo.

## Stack

- Python 3.11+ (runs on 3.14), Poetry
- FastAPI, Pydantic v2, pydantic-settings
- SQLAlchemy 2.x + psycopg (v3, async-capable), Alembic
- Redis (asyncio client) — cache-aside + pub/sub
- LangChain / LangGraph, langchain-openai
- Langfuse v3 SDK (observability)
- JWT auth via python-jose + bcrypt
- slowapi — rate limiting
- WebSocket streaming (FastAPI native)

## Run locally

```bash
cd apps/fridge-chatbot/backend
cp .env.example .env          # fill in OPENAI_API_KEY at minimum
poetry install
./run.sh                       # starts uvicorn on http://localhost:8001
```

Health check: `GET http://localhost:8001/health` → `{"status":"healthy","service":"fridge-chatbot-backend"}`

Auto-migration: on startup, if `AUTO_MIGRATE=true` (default), the lifespan calls `alembic upgrade head`. Fresh DB provisions automatically — no manual `alembic upgrade` needed.

## Tests

```bash
cd apps/fridge-chatbot/backend
poetry run pytest              # 151 tests: 149 pass + 2 xfail
```

xfail tests (Open items #8/#9): workers and LangGraph tool nodes do not yet publish `family:{id}:events` events to Redis — only REST handlers do.

## Domain model

| Entity | Table | Notes |
|--------|-------|-------|
| Family | `families` | Top-level tenant; all data is family-scoped |
| Member | `members` | Household member; assignee, never login identity |
| Car | `cars` | Shared vehicle; assignable to members |
| Note | `notes` | Sticky notes with optional member + car assignees |
| CalendarEvent | `calendar_events` | Google Calendar integration + local events |
| Label | `labels` | Color-coded tags for notes/events |

Families own everything. Users (JWT subjects) are associated to a family via the pairing flow.

## Structure

```
server.py                          # uvicorn entrypoint → imports src/main.py::app
src/
├── main.py                        # FastAPI app factory + lifespan
├── core/
│   ├── settings.py                # Pydantic Settings (reads .env)
│   ├── dependencies.py            # FastAPI DI: get_settings, get_db_service, get_parent_router, etc.
│   ├── security.py                # JWT encode/decode helpers
│   ├── cache.py                   # Cache-aside helper (SETNX single-flight, pattern invalidation)
│   ├── pubsub.py                  # Redis channel name helpers (thread_tokens_channel, family_events_channel)
│   ├── family_events.py           # publish_family_event() — writes to family:{id}:events channel
│   ├── migrations.py              # run_alembic_upgrade() wrapper called by lifespan
│   ├── rate_limit.py              # slowapi limiter setup
│   └── labels.py                  # Label ownership helpers
├── db/
│   ├── shared_engine.py           # SQLAlchemy engine singleton
│   └── postgres.py                # Session factory, DatabaseService class
├── models/                        # SQLAlchemy ORM models (one file per entity)
│   ├── database.py                # User, Thread, Message
│   ├── family.py                  # Family, FamilyPreferences
│   ├── member.py                  # Member
│   ├── car.py                     # Car
│   ├── note.py                    # Note, NoteAssignee
│   ├── event.py                   # CalendarEvent, EventAssignee
│   └── label.py                   # Label
├── schemas/                       # Pydantic request/response schemas (mirrors models/)
├── routes/
│   ├── auth.py                    # POST /auth/register, POST /auth/login
│   ├── users.py                   # GET /users/me
│   ├── family.py                  # Family CRUD + preferences
│   ├── members.py                 # Member CRUD
│   ├── cars.py                    # Car CRUD
│   ├── notes.py                   # Note CRUD
│   ├── events.py                  # Calendar event CRUD
│   ├── calendar_sync.py           # Google Calendar sync triggers
│   ├── labels.py                  # Label CRUD
│   ├── oauth.py                   # Google OAuth flow
│   ├── pairing.py                 # /api/pairing/* — device pairing (UI not yet built)
│   ├── threads.py                 # Thread CRUD + WS /ws/threads/{id}
│   └── family_events_ws.py        # WS /ws/family/{family_id}/events — Redis pub/sub subscriber
├── services/                      # See services/CLAUDE.md
├── llm_graphs/                    # See llm_graphs/CLAUDE.md
├── workers/
│   ├── calendar_sync_worker.py    # Polling loop: pull Google Calendar → local DB
│   └── calendar_write_worker.py   # Write-through: local events → Google Calendar
└── utils/
    ├── json_utils.py
    └── db_state.py
```

## Key patterns

**Cache-aside:** `core/cache.py` provides `cache_get_or_set(redis, key, ttl, loader)` with SETNX single-flight (prevents stampedes). Every read endpoint that is list-shaped uses it. Every write endpoint calls `invalidate_pattern(redis, pattern)` per the invalidation map in the architecture doc (§7.6).

**Pub/sub:** `core/pubsub.py` defines channel name builders. `core/family_events.py` provides `publish_family_event(redis, family_id, event_dict)`. REST write handlers call this after committing so the family events WS subscriber can push the update to connected kiosk clients.

**Family events WS:** `routes/family_events_ws.py` — one long-lived WS per device. Subscribes to `family:{family_id}:events` Redis channel and forwards JSON text frames. Auth via `?token=` query param.

**LangGraph orchestration:** `ParentRouter` receives WS messages, loads thread history, delegates to a subgraph, streams tokens via callback. Add new capabilities as subgraphs under `llm_graphs/subgraphs/`.

**SQLAlchemy singleton:** `shared_engine.py` creates the engine once; `postgres.py` wraps in `DatabaseService`. Session is yielded per-request via `get_db()` context manager.

**JWT auth:** `security.py` signs/verifies. `core/dependencies.py` exposes `get_current_user` as a FastAPI dependency. Family resolution is a second lookup keyed to the user's `family_id`.

**Rate limiting:** `slowapi` at the app level; `core/rate_limit.py` configures the limiter and the custom error handler.

**Langfuse v3:** `LangfuseService.initialize(settings)` in `lifespan`. After that, `get_client()` from the `langfuse` package directly.

**Auto-migration:** lifespan checks `settings.AUTO_MIGRATE` (default `true`) and calls `alembic upgrade head` in a thread-pool executor before any request is served.

## Key env vars (see `.env.example` for all)

| Variable | Default | Notes |
|----------|---------|-------|
| `OPENAI_API_KEY` | — | Required for LLM calls |
| `AUTO_MIGRATE` | `true` | Run `alembic upgrade head` on startup |
| `POSTGRES_HOST` | `postgres` | Matches devcontainer service name |
| `REDIS_URL` | `redis://redis:6379` | Cache + pub/sub |
| `GOOGLE_CLIENT_ID` | — | Required for Google OAuth / Calendar sync |
| `GOOGLE_CLIENT_SECRET` | — | Required for Google OAuth / Calendar sync |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-dev-0000…` | Matches devcontainer Langfuse seed |
| `LANGFUSE_SECRET_KEY` | `sk-lf-dev-0000…` | Matches devcontainer Langfuse seed |
| `LANGFUSE_HOST` | `http://langfuse-web:3000` | Internal container URL |
| `LANGFUSE_ENABLED` | `false` | Set `true` to activate tracing |
| `SECRET_KEY` | `changeme` | JWT signing key — change in production |

## How to extend

**Add a subgraph:** create `src/llm_graphs/subgraphs/my_feature/my_feature.py`, register in `parent_router.py`.

**Add a route:** create `src/routes/my_route.py`, include the router in `src/main.py::create_app()`.

**Add a DB model:** add the class to the appropriate `src/models/*.py`; generate an Alembic migration with `alembic revision --autogenerate -m "description"`.

**Emit a family event:** after a write, call `await publish_family_event(redis, family_id, {...})` from `core/family_events.py`.
