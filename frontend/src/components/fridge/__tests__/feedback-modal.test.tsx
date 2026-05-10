/**
 * Component tests for FeedbackModal — covers Tier A #4, #5 and Tier B #8, #9
 * plus Tier C #10 (Polish locale rendering) of the FrontendTester brief.
 *
 * What's intentionally NOT here:
 *   - Snapshot of the modal HTML — markup churns on every CSS tweak.
 *   - Verifying exact request bytes — only that the right `category`+`message`
 *     end up in the body. The api client's serialization is its own concern.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { FeedbackModal } from "@/components/fridge/feedback-modal";
import { server } from "@/test/msw-server";
import { saveToken } from "@/lib/auth";
import { setLocale } from "@/paraglide/runtime.js";

const BACKEND = "http://localhost:8001";

// Hold a real-ish toast spy. We mock the module so the test can read what
// actually fired without rendering Sonner's portal.
const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    warning: vi.fn(),
    message: vi.fn(),
    dismiss: vi.fn(),
  },
}));

beforeEach(() => {
  saveToken("eyJhbGciOiJub25lIn0.eyJmYW1pbHlfaWQiOiJmYW0tMSJ9.x");
  toastSuccess.mockReset();
  toastError.mockReset();
});

afterEach(() => vi.restoreAllMocks());

/** Shared helper — submits a successful POST and records the request body. */
function captureSubmit(): { last: () => Record<string, unknown> | null } {
  let body: Record<string, unknown> | null = null;
  server.use(
    http.post(`${BACKEND}/api/feedback`, async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        {
          id: "fb-1",
          family_id: "fam-1",
          member_id: null,
          device_id: "dev-1",
          thread_id: body.thread_id ?? null,
          category: body.category,
          message: body.message,
          author_kind: "user",
          status: "open",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        { status: 201 },
      );
    }),
  );
  return { last: () => body };
}

describe("[component] FeedbackModal — happy path", () => {
  test("submits the selected category and message, closes, and fires success toast", async () => {
    const onClose = vi.fn();
    const captured = captureSubmit();

    render(<FeedbackModal open threadId={null} onClose={onClose} />);
    const user = userEvent.setup();

    // Pick "Improvement"
    await user.click(screen.getByLabelText(/improvement/i));
    // Type an above-min-length message
    const textarea = screen.getByPlaceholderText(/tell us what's not working/i);
    await user.type(textarea, "Please add dark mode for kiosk display");

    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(captured.last()).not.toBeNull();
    });
    const body = captured.last()!;
    expect(body.category).toBe("improvement");
    expect(body.message).toBe("Please add dark mode for kiosk display");
    // Security boundary: FE never sends author_kind — backend pins it server-side.
    expect(body).not.toHaveProperty("author_kind");

    expect(toastSuccess).toHaveBeenCalledWith("Thanks — your feedback was logged.");
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test("propagates threadId to the request body when provided", async () => {
    const captured = captureSubmit();
    render(
      <FeedbackModal open threadId="uuid-thread-99" onClose={() => undefined} />,
    );
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "I have at least ten characters here",
    );
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => expect(captured.last()).not.toBeNull());
    expect(captured.last()!.thread_id).toBe("uuid-thread-99");
  });
});

describe("[component] FeedbackModal — validation guards", () => {
  test("Send is disabled when the textarea is empty", () => {
    render(<FeedbackModal open onClose={() => undefined} />);
    const send = screen.getByRole("button", { name: /^send$/i });
    expect(send).toBeDisabled();
  });

  test("Send stays disabled for a 5-character message (under 10-char min)", async () => {
    render(<FeedbackModal open onClose={() => undefined} />);
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "hi me",
    );
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
  });

  test("Send is disabled when whitespace-only padding makes a message effectively under min", async () => {
    render(<FeedbackModal open onClose={() => undefined} />);
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "  hi  ",
    );
    // After trim, this is "hi" — 2 chars < 10. Send must remain disabled.
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
  });

  test("Send is disabled past 2000 characters and char counter shows error state", async () => {
    render(<FeedbackModal open onClose={() => undefined} />);
    const textarea = screen.getByPlaceholderText(
      /tell us what's not working/i,
    ) as HTMLTextAreaElement;

    // userEvent.type(2001 chars) is too slow — fire a programmatic input event.
    const big = "a".repeat(2001);
    textarea.focus();
    // Use the React-friendly fireEvent path.
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(textarea, { target: { value: big } });

    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
    // The char counter element has `data-state="error"` past the cap.
    const counter = screen.getByText(/\/ 2000$/);
    expect(counter).toHaveAttribute("data-state", "error");
  });

  test("char counter switches to warn state past 1800 characters", async () => {
    render(<FeedbackModal open onClose={() => undefined} />);
    const textarea = screen.getByPlaceholderText(
      /tell us what's not working/i,
    ) as HTMLTextAreaElement;
    textarea.focus();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(textarea, { target: { value: "x".repeat(1900) } });
    const counter = screen.getByText(/\/ 2000$/);
    expect(counter).toHaveAttribute("data-state", "warn");
  });
});

describe("[component] FeedbackModal — error handling", () => {
  test("429 from server fires the rate-limit toast (not the generic error toast)", async () => {
    server.use(
      http.post(`${BACKEND}/api/feedback`, () =>
        HttpResponse.json(
          {
            detail: "Too many requests",
            code: "feedback.rate_limited",
            retry_after_sec: 30,
          },
          { status: 429 },
        ),
      ),
    );

    render(<FeedbackModal open onClose={() => undefined} />);
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "Slow down please, this is a real message",
    );
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      // The modal's own rate-limit toast text uses the `feedback_rate_limit_toast`
      // message. The shared http() helper also fires its own generic toast,
      // which is fine — what matters is that the feedback-specific copy fired.
      expect(toastError).toHaveBeenCalledWith(
        "Please wait a moment before sending again.",
      );
    });
  });

  test("generic 500 fires the generic error toast", async () => {
    server.use(
      http.post(`${BACKEND}/api/feedback`, () =>
        HttpResponse.json({ detail: "Boom" }, { status: 500 }),
      ),
    );

    render(<FeedbackModal open onClose={() => undefined} />);
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "Something is broken in the kiosk",
    );
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      // The api client's ApiError carries the server's detail message; the
      // modal prefers it over the canned fallback. We only assert that *some*
      // error toast was fired — and that it wasn't the rate-limit copy.
      expect(toastError).toHaveBeenCalled();
      const calls = toastError.mock.calls.map((c) => String(c[0]));
      expect(
        calls.some((s) => /please wait a moment/i.test(s)),
      ).toBe(false);
    });
  });
});

describe("[component] FeedbackModal — Esc-to-close behavior", () => {
  test("Esc closes the modal when not submitting", async () => {
    const onClose = vi.fn();
    render(<FeedbackModal open onClose={onClose} />);
    const user = userEvent.setup();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  test("Esc is suppressed while a submit is in flight", async () => {
    // Hold the response open so the modal stays in the `submitting=true` state.
    let resolveResponse!: () => void;
    const gate = new Promise<void>((resolve) => {
      resolveResponse = resolve;
    });
    server.use(
      http.post(`${BACKEND}/api/feedback`, async () => {
        await gate;
        return HttpResponse.json(
          {
            id: "fb-x",
            family_id: "fam-1",
            member_id: null,
            device_id: null,
            thread_id: null,
            category: "bug",
            message: "msg",
            author_kind: "user",
            status: "open",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          { status: 201 },
        );
      }),
    );

    const onClose = vi.fn();
    render(<FeedbackModal open onClose={onClose} />);
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "Please be patient and wait for me",
    );
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    // Esc fires while submitting — must NOT close.
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();

    // Release the gate; modal should now close from the success path.
    resolveResponse();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});

describe("[component] FeedbackModal — a11y + Polish locale", () => {
  test("dialog has aria-modal and accessible name", () => {
    render(<FeedbackModal open onClose={() => undefined} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "feedback-modal-title");
    // The labelled element (h3) carries the title text.
    expect(within(dialog).getByRole("heading", { name: "Send feedback" })).toBeInTheDocument();
  });

  test("Polish locale renders translated category labels", () => {
    setLocale("pl", { reload: false });
    render(<FeedbackModal open onClose={() => undefined} />);
    // Per pl.json: Błąd / Pomysł / Pytanie / Inne
    expect(screen.getByLabelText("Błąd")).toBeInTheDocument();
    expect(screen.getByLabelText("Pomysł")).toBeInTheDocument();
    expect(screen.getByLabelText("Pytanie")).toBeInTheDocument();
    expect(screen.getByLabelText("Inne")).toBeInTheDocument();
    // Submit button uses Polish copy.
    expect(screen.getByRole("button", { name: /^Wyślij$/ })).toBeInTheDocument();
  });

  test("does not render when `open` is false", () => {
    render(<FeedbackModal open={false} onClose={() => undefined} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("resets form fields when reopened (no leftover text)", async () => {
    const { rerender } = render(
      <FeedbackModal open onClose={() => undefined} />,
    );
    const user = userEvent.setup();
    await user.type(
      screen.getByPlaceholderText(/tell us what's not working/i),
      "draft text",
    );
    rerender(<FeedbackModal open={false} onClose={() => undefined} />);
    rerender(<FeedbackModal open onClose={() => undefined} />);

    const textarea = screen.getByPlaceholderText(
      /tell us what's not working/i,
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe("");
  });
});
