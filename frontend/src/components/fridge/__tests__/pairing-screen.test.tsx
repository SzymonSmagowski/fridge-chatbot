/**
 * Integration tests for PairingScreen — covers the redirect-based pairing
 * flow against Architect §5.1 (`POST /api/pairing/start` returns
 * `{ authorize_url, pairing_id }`, then the kiosk navigates to that URL).
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { PairingScreen } from "@/components/fridge/pairing-screen";
import { server } from "@/test/msw-server";

const BACKEND = "http://localhost:8001";
const AUTHORIZE_URL =
  "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id=fake";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));

let assignSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  assignSpy = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, assign: assignSpy },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("[integration] PairingScreen", () => {
  test("idle: shows the title, subtitle, and start button", () => {
    render(<PairingScreen />);
    expect(screen.getByText(/set up your fridge/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start pairing/i })).toBeEnabled();
  });

  test("starting → redirecting: POSTs /api/pairing/start and assigns to authorize_url", async () => {
    let captured: { device_label?: string } | null = null;
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, async ({ request }) => {
        captured = (await request.json()) as { device_label?: string };
        return HttpResponse.json({
          pairing_id: "abc123",
          authorize_url: AUTHORIZE_URL,
        });
      }),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));

    await waitFor(() => {
      expect(assignSpy).toHaveBeenCalledWith(AUTHORIZE_URL);
    });
    expect(captured).toEqual({ device_label: "Kitchen Fridge" });
  });

  test("error: 503 from /api/pairing/start surfaces an error box and a retry button", async () => {
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, () =>
        HttpResponse.json(
          { detail: "Pairing temporarily unavailable" },
          { status: 503 },
        ),
      ),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/couldn't start pairing/i);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/pairing temporarily unavailable/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeEnabled();
    expect(assignSpy).not.toHaveBeenCalled();
  });

  test("error → retry: clicking retry re-issues the request and redirects on success", async () => {
    let calls = 0;
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ detail: "boom" }, { status: 503 });
        }
        return HttpResponse.json({
          pairing_id: "abc123",
          authorize_url: AUTHORIZE_URL,
        });
      }),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => {
      expect(assignSpy).toHaveBeenCalledWith(AUTHORIZE_URL);
    });
    expect(calls).toBe(2);
  });

});
