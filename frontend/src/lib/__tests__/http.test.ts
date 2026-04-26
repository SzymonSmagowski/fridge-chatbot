/**
 * Unit tests for the typed HTTP client error envelope handling.
 *
 * Covers Architect §5 conventions:
 *   - error envelope `{ detail, code }` is parsed into ApiError.
 *   - 429 with `retry_after_sec` triggers a sonner toast.
 *   - 204 returns undefined (no body parse).
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { toast } from "sonner";
import { server } from "@/test/msw-server";
import { ApiError, notesApi } from "@/lib/api";
import { saveToken } from "@/lib/auth";

const BACKEND = "http://localhost:8001";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    warning: vi.fn(),
    message: vi.fn(),
    dismiss: vi.fn(),
  },
}));

beforeEach(() => {
  saveToken("test-jwt");
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("[unit] api/http error envelope handling", () => {
  test("parses { detail, code } from a 4xx response into ApiError", async () => {
    server.use(
      http.get(`${BACKEND}/api/notes`, () =>
        HttpResponse.json(
          { detail: "Note not found", code: "notes.not_found" },
          { status: 404 },
        ),
      ),
    );

    await expect(notesApi.list()).rejects.toMatchObject({
      status: 404,
      message: "Note not found",
    });
  });

  test("falls back to status text when body isn't JSON", async () => {
    server.use(
      http.get(`${BACKEND}/api/notes`, () => new HttpResponse("nope", { status: 500 })),
    );

    await expect(notesApi.list()).rejects.toMatchObject({
      status: 500,
    });
  });

  test("429 with retry_after_sec triggers a sonner toast", async () => {
    server.use(
      http.get(`${BACKEND}/api/notes`, () =>
        HttpResponse.json(
          {
            detail: "Too many requests — try again in 30s.",
            code: "auth.rate_limited",
            retry_after_sec: 30,
          },
          { status: 429 },
        ),
      ),
    );

    await expect(notesApi.list()).rejects.toBeInstanceOf(ApiError);
    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining("Too many requests"),
    );
  });

  test("DELETE returning 204 resolves to undefined", async () => {
    server.use(
      http.delete(`${BACKEND}/api/notes/n-1`, () => new HttpResponse(null, { status: 204 })),
    );

    await expect(notesApi.delete("n-1")).resolves.toBeUndefined();
  });

  test("attaches Authorization header when a token is set", async () => {
    let captured: string | null = null;
    server.use(
      http.get(`${BACKEND}/api/notes`, ({ request }) => {
        captured = request.headers.get("Authorization");
        return HttpResponse.json({ items: [], total: 0 });
      }),
    );

    await notesApi.list();
    expect(captured).toBe("Bearer test-jwt");
  });
});
