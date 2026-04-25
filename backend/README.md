# Fridge Chatbot Backend

FastAPI + LangGraph backend for the fridge chatbot. Also serves as the **baseline template** for future Python backends in this monorepo.

## Stack
- **Python 3.11**, **Poetry**
- **FastAPI** + Uvicorn (HTTP + WebSocket)
- **SQLAlchemy** + **psycopg** (Postgres)
- **LangChain / LangGraph** for LLM orchestration
- **JWT** auth (bcrypt-hashed passwords)
- **Langfuse** + **LangSmith** for optional observability

## Layout
```
server.py              # uvicorn entry point
src/
├── main.py            # FastAPI app factory + lifespan
├── core/              # settings, DI, security
├── db/                # shared SQLAlchemy engine
├── models/            # ORM models
├── schemas/           # Pydantic request/response models
├── routes/            # auth, users, threads
├── services/          # auth, db ops, LLM factory, observability
├── llm_graphs/        # LangGraph orchestration
│   ├── parent_router.py
│   └── subgraphs/fridge_assistant/
└── utils/
```

## Run locally (inside the devcontainer)

Postgres at `postgres:5432` and Redis at `redis:6379` are already running as sidecar containers.

```bash
cd apps/fridge-chatbot/backend
cp .env.example .env     # fill in OPENAI_API_KEY and SECRET_KEY
poetry install
./run.sh                 # → http://localhost:8001
```

## Endpoints (current)
- `POST /auth/register` — create a user
- `POST /auth/login` — exchange username/password for JWT
- `GET /threads` — list current user's threads
- `POST /threads` — create a thread
- `GET /threads/{id}` — fetch thread + messages
- `PATCH /threads/{id}` — rename
- `DELETE /threads/{id}` — delete
- `WS /ws/threads/{id}` — stream chat with the fridge assistant
- `POST /threads/messages/{message_id}/feedback` — like/dislike a message
- `GET /health` — liveness check

## Roadmap (not yet wired)
- **Redis** — placeholder `REDIS_URL` is set. Planned use cases: LLM response cache, rate limiting, background job queue.
- RAG over a recipe / ingredient knowledge base.
