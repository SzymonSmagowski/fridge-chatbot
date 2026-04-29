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

export interface ThreadMessagesResponse extends ThreadResponse {
  messages: MessageResponse[];
}

export interface FeedbackResponse {
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
    api<FeedbackResponse>(`/threads/messages/${messageId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ feedback, comment }),
    }),
};

export function wsUrl(threadId: number): string {
  const httpUrl = new URL(`/ws/threads/${threadId}`, BACKEND_URL);
  httpUrl.protocol = httpUrl.protocol === "https:" ? "wss:" : "ws:";
  return httpUrl.toString();
}
