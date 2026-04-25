# services

One class per file. Services are injected via `core/dependencies.py`.

## Files

| File | Class | Notes |
|------|-------|-------|
| `auth_service.py` | `AuthService` | JWT creation/validation + bcrypt password hashing |
| `family_service.py` | `FamilyService` | Family + preferences CRUD |
| `member_service.py` | `MemberService` | Member CRUD |
| `car_service.py` | `CarService` | Car CRUD |
| `note_service.py` | `NoteService` | Note CRUD + assignee handling |
| `event_service.py` | `EventService` | Calendar event CRUD; `scope=all_future` is a stub for Google's "this and following" mechanic |
| `event_target_resolver.py` | — | Resolves which family members/cars an event applies to |
| `label_service.py` | `LabelService` | Label CRUD |
| `google_oauth_service.py` | `GoogleOAuthService` | OAuth flow (code exchange, token storage) |
| `google_token_service.py` | `GoogleTokenService` | Token refresh + storage |
| `google_calendar_service.py` | `GoogleCalendarService` | Read/write Google Calendar API |
| `family_preferences_service.py` | `FamilyPreferencesService` | Family language/timezone preferences |
| `crypto_service.py` | `CryptoService` | Encrypt/decrypt Google refresh tokens at rest |
| `redis_service.py` | — | `get_redis_client()` / `close_redis_client()` lifecycle helpers |
| `chat_streaming.py` | — | Redis pub/sub wrappers for token streaming + subscription lifecycle |
| `db_operations_service.py` | `DatabaseOperationsService` | High-level DB queries (threads, messages, users) |
| `llm_factory.py` | `LLMFactory` | Static factory; returns `ChatOpenAI` — OpenAI only, no multi-provider |
| `llm_utils.py` | — | Thread title generation helper |
| `langfuse_service.py` | `LangfuseService` | v3 singleton; call `initialize(settings)` once at startup, then `get_client()` anywhere |
| `langsmith_tracing.py` | `LangSmithTracing` | Optional LangSmith tracing; same init pattern |
| `logger.py` | — | `get_logger(name)` returns a stdlib logger |

## Singleton pattern

`LangfuseService` and `LangSmithTracing` use a classmethod `initialize(settings)` + `_initialized` guard. Call `initialize` in `main.py::lifespan`. After that, import `get_client` from the `langfuse` package directly.

## Dependency injection

`core/dependencies.py` exposes FastAPI dependencies (`get_db_service`, `get_parent_router`, `get_current_user`, `get_auth_service`, `get_chat_streamer`, `get_redis`). Use these as `Depends(...)` parameters in route handlers.
