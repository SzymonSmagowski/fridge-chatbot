import { getToken } from "@/lib/auth";

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8001";

export interface UserResponse {
  id: number;
  username: string;
  email: string | null;
}

export interface UserPublic extends UserResponse {
  is_active: boolean;
}

export interface ThreadResponse {
  id: number;
  thread_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageResponse {
  id: string;
  role: string;
  content: string;
  type: string;
  created_at: string | null;
  score: string | null;
  comment: string | null;
}

/**
 * Cursor-paginated page of messages for a thread. Wire order is **newest-first**
 * (DESC by created_at, then DESC by message_id for ties). `next_cursor` encodes
 * the oldest message in the returned page; pass it as `before` on the next call
 * to fetch the page immediately older than this one. `null` when `has_more === false`.
 *
 * This is the shape returned by:
 *   - `GET /threads/{id}/messages?before=…&limit=…` (older history)
 *   - the `messages_page` envelope embedded in `GET /threads/{id}` (initial open)
 */
export interface MessagesPageResponse {
  messages: MessageResponse[];
  has_more: boolean;
  next_cursor: string | null;
}

/**
 * Initial-open envelope for a thread. The thread metadata (id, title, timestamps)
 * lives at the top level alongside `messages`, `has_more`, `next_cursor` — the
 * latter three forming a `MessagesPageResponse`-shaped initial page (latest 30
 * messages by default).
 */
export interface ThreadMessagesResponse extends ThreadResponse, MessagesPageResponse {}

/**
 * Per-message thumbs up/down feedback (legacy, unrelated to the user-feedback
 * channel). Writes `messages.score` / `messages.comment` on a single chat reply.
 */
export interface MessageThumbsFeedbackResponse {
  message_id: string;
  feedback: string;
  success: boolean;
}

export class ApiError extends Error {
  status: number;
  detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function api<T>(
  path: string,
  init: RequestInit = {},
  { auth = true }: { auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BACKEND_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = await res.json();
      detail = body?.detail ?? body?.error ?? undefined;
    } catch {
      // non-JSON body
    }
    throw new ApiError(
      res.status,
      detail ?? `${res.status} ${res.statusText}`,
      detail,
    );
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const apiClient = {
  me: () => api<UserPublic>("/users/me"),

  listThreads: () => api<ThreadResponse[]>("/threads"),

  createThread: (firstUserMessage: string) =>
    api<ThreadResponse>("/threads", {
      method: "POST",
      body: JSON.stringify({ first_user_message: firstUserMessage }),
    }),

  getThread: (id: number) => api<ThreadMessagesResponse>(`/threads/${id}`),

  /**
   * Cursor-paginated older messages for a thread. Returns up to `limit` messages
   * strictly older than `before` (the cursor returned by a prior call or by the
   * initial `getThread` envelope). Wire order is newest-first; the FE reverses
   * to chronological before prepending into `useExternalStoreRuntime`.
   *
   * Server clamps `limit` to [1, 100] (default 30 if omitted).
   */
  getThreadMessagesPage: (
    id: number,
    opts: { before?: string; limit?: number } = {},
  ) => {
    const u = new URLSearchParams();
    if (opts.before) u.set("before", opts.before);
    if (opts.limit != null) u.set("limit", String(opts.limit));
    const q = u.toString();
    return api<MessagesPageResponse>(
      `/threads/${id}/messages${q ? `?${q}` : ""}`,
    );
  },

  renameThread: (id: number, title: string) =>
    api<ThreadResponse>(`/threads/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),

  deleteThread: (id: number) =>
    api<{ id: number; success: boolean }>(`/threads/${id}`, {
      method: "DELETE",
    }),

  messageFeedback: (
    messageId: string,
    feedback: "like" | "dislike",
    comment?: string,
  ) =>
    api<MessageThumbsFeedbackResponse>(
      `/threads/messages/${messageId}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({ feedback, comment }),
      },
    ),
};

export function wsUrl(threadId: number): string {
  const httpUrl = new URL(`/ws/threads/${threadId}`, BACKEND_URL);
  httpUrl.protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  return httpUrl.toString();
}
