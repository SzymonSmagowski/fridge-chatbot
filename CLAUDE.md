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

- REST API: `http://localhost:8001/api/*` for family-scoped routes (members, cars, notes, events, labels, family, family/preferences, calendar/sync*, pairing). Bare-path routes: `/auth/*`, `/oauth/google/*`, `/threads*`, `/users/me`, `/health`.
- Streaming chat WS: `ws://localhost:8001/ws/threads/{id}` — first message is JWT auth handshake
- Family broadcast WS: `ws://localhost:8001/ws/family/{family_id}/events?token=<jwt>` — Redis pub/sub push for board state
- Auth: device JWT obtained from `POST /api/pairing/start` (first-time pairing → Google OAuth → callback redirects to `/pair/complete?token=<jwt>`). Legacy `POST /auth/login` is still available as a developer escape hatch.

## Known gaps

- `EventService.scope=all_future` recurring-event split is implemented (Architect §6.7) but lacks UI — calendar editor only exposes `scope=instance` for now.
- No multi-device pairing UI — schema supports it (`devices` table with `family_id` FK), but the "add another device to this family" flow doesn't exist.
