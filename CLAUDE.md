# fridge-chatbot

A shared-appliance kiosk chatbot for household management. Members are assignees and scope boundaries, never login identities. No per-user auth — a family is the top-level tenant. This app is the worked example for the autonomous pipeline; its architecture is the baseline for future Python/Next.js projects in the monorepo.

## Subdirectories

- `backend/` — Python/FastAPI/LangGraph service. See `backend/CLAUDE.md`.
- `frontend/` — Next.js 16 (App Router, Turbopack) + React 19 + TypeScript + Tailwind CSS 4 + shadcn + `@assistant-ui/react`. Uses assistant-ui components only; runtime is custom (REST + WebSocket directly to our FastAPI — no vendor SDK). See `frontend/CLAUDE.md`.

## Dev

```bash
./apps/fridge-chatbot/dev.sh
```

Runs preflight checks for `poetry` and `pnpm`, then starts backend (port 8001) and frontend (port 3000). Ctrl+C kills both cleanly. Logs are color-coded: `[backend]` cyan, `[frontend]` magenta.

## Backend ↔ Frontend contract

- REST API: `http://localhost:8001` (family, members, cars, notes, events, labels, threads, OAuth)
- Streaming chat WS: `ws://localhost:8001/ws/threads/{id}` — first message is JWT auth handshake
- Family broadcast WS: `ws://localhost:8001/ws/family/{family_id}/events?token=<jwt>` — Redis pub/sub push for board state
- Auth: JWT bearer token, obtained from `POST /auth/login` (bypass) or `POST /api/pairing/*` (first-time pairing, UI not yet built)

## Known gaps

- No first-time pairing UI — falls back to legacy `/login`. Backend `/api/pairing/*` routes exist.
- Workers (`calendar_sync_worker`, `calendar_write_worker`) and LangGraph tool nodes do not yet emit `family:{id}:events` pub/sub events — only REST handlers do. Two `xfail` backend tests document this.
