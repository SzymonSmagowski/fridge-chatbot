/**
 * Per-domain API barrel. Re-exports the typed clients introduced for the
 * full fridge feature set so callers can `import { membersApi } from "@/lib/api"`.
 *
 * The pre-existing chat/auth client lives in `lib/api.ts` and is re-exported
 * here for one-stop access. Do not introduce duplicate fetch wrappers — both
 * paths route through the shared http() helper or apiClient (same BACKEND_URL,
 * same JWT slot).
 */
export { apiClient, ApiError, BACKEND_URL, wsUrl } from "./_legacy";
export type {
  MessageResponse,
  MessagesPageResponse,
  MessageThumbsFeedbackResponse,
  ThreadMessagesResponse,
  ThreadResponse,
  UserPublic,
  UserResponse,
} from "./_legacy";

export { feedbackApi } from "./feedback";
export type {
  FeedbackAuthorKind,
  FeedbackCategory,
  FeedbackCreateRequest,
  FeedbackListFilters,
  FeedbackListResponse,
  FeedbackResponse,
  FeedbackStatus,
} from "./feedback";

export { familyApi } from "./family";
export type {
  FamilyPreferencesPatch,
  FamilyPreferencesResponse,
  FamilyResponse,
  FamilyUpdateRequest,
} from "./family";

export { membersApi } from "./members";
export type {
  GoogleStateResponse,
  GoogleStatus,
  MemberCreateRequest,
  MemberResponse,
  MemberStatus,
  MemberStatusFilter,
  MemberUpdateRequest,
} from "./members";

export { carsApi } from "./cars";
export type {
  CarCreateRequest,
  CarResponse,
  CarStatus,
  CarStatusFilter,
  CarUpdateRequest,
} from "./cars";

export { labelsApi, SHOPPING_LIST_SLUG } from "./labels";
export type {
  LabelCreateRequest,
  LabelResponse,
  LabelUpdateRequest,
} from "./labels";

export { notesApi } from "./notes";
export type {
  NoteCreateRequest,
  NoteLabelView,
  NoteListFilters,
  NoteListResponse,
  NoteResponse,
  NoteUpdateRequest,
} from "./notes";

export { eventsApi } from "./events";
export type {
  EventCreateRequest,
  EventListFilters,
  EventListResponse,
  EventResponse,
  EventScope,
  EventSource,
  EventSyncStatus,
  EventTargetView,
  EventUpdateRequest,
  ExternalEventResponse,
} from "./events";

export { calendarSyncApi } from "./calendar-sync";
export type { SyncStateResponse } from "./calendar-sync";

export { oauthApi, pairingApi } from "./oauth";
export type { AuthorizeUrlResponse, PairingStartResponse } from "./oauth";

export { livekitApi } from "./livekit";
export type { LiveKitTokenResponse } from "./livekit";
