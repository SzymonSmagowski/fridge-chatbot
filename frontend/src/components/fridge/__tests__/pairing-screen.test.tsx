/**
 * Integration tests for PairingScreen — covers the QR-code pairing flow
 * against Architect §5.1 (`POST /api/pairing/start` returns
 * `{ authorize_url, pairing_id }`, kiosk shows QR, polls
 * `GET /api/pairing/status/<id>`, persists JWT and navigates on `complete`).
 *
 * The legacy direct-redirect path is exercised via the "Use this device"
 * fallback link, which is the only place `window.location.assign` is still
 * called from PairingScreen.
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
  // Each test starts with a clean kiosk marker; the production flow sets
  // this when /pairing/start succeeds.
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("[integration] PairingScreen", () => {
  test("idle: shows the title, subtitle, and start button", () => {
    render(<PairingScreen />);
    expect(screen.getByText(/set up your fridge/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start pairing/i })).toBeEnabled();
  });

  test("starting → polling: POSTs /api/pairing/start and renders a QR for authorize_url", async () => {
    let captured: { device_label?: string } | null = null;
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, async ({ request }) => {
        captured = (await request.json()) as { device_label?: string };
        return HttpResponse.json({
          pairing_id: "abc123",
          authorize_url: AUTHORIZE_URL,
        });
      }),
      http.get(`${BACKEND}/api/pairing/status/abc123`, () =>
        HttpResponse.json({ status: "pending", token: null }),
      ),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));

    await screen.findByText(/scan with your phone/i);
    expect(captured).toEqual({ device_label: "Kitchen Fridge" });
    // The kiosk marker should be set so /pair/complete can later identify
    // a fallback-flow callback as belonging to this device.
    expect(window.localStorage.getItem("fridge:kiosk_pairing_id")).toBe(
      "abc123",
    );
    // The "Use this device" fallback link is present and points at Google.
    expect(
      screen.getByRole("link", { name: /use this device instead/i }),
    ).toHaveAttribute("href", AUTHORIZE_URL);
    // Polling has not redirected anywhere yet — the QR is meant to be scanned.
    expect(assignSpy).not.toHaveBeenCalled();
  });

  test("polling complete: persists token and navigates to /", async () => {
    let statusCalls = 0;
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, () =>
        HttpResponse.json({ pairing_id: "abc123", authorize_url: AUTHORIZE_URL }),
      ),
      http.get(`${BACKEND}/api/pairing/status/abc123`, () => {
        statusCalls += 1;
        if (statusCalls === 1) {
          return HttpResponse.json({ status: "pending", token: null });
        }
        return HttpResponse.json({
          status: "complete",
          token: "device-jwt-fake",
        });
      }),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));
    await screen.findByText(/scan with your phone/i);

    await waitFor(
      () => {
        expect(assignSpy).toHaveBeenCalledWith("/");
      },
      { timeout: 5000 },
    );
    // The marker is cleared once the kiosk is fully paired.
    expect(window.localStorage.getItem("fridge:kiosk_pairing_id")).toBeNull();
  });

  test("polling expired: shows expired body + retry resets to idle", async () => {
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, () =>
        HttpResponse.json({ pairing_id: "abc123", authorize_url: AUTHORIZE_URL }),
      ),
      http.get(`${BACKEND}/api/pairing/status/abc123`, () =>
        HttpResponse.json({ status: "expired", token: null }),
      ),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));
    await screen.findByText(/pairing session expired/i);

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(
      screen.getByRole("button", { name: /start pairing/i }),
    ).toBeEnabled();
  });

  test("use-this-device fallback: clicking the link assigns to authorize_url", async () => {
    server.use(
      http.post(`${BACKEND}/api/pairing/start`, () =>
        HttpResponse.json({ pairing_id: "abc123", authorize_url: AUTHORIZE_URL }),
      ),
      http.get(`${BACKEND}/api/pairing/status/abc123`, () =>
        HttpResponse.json({ status: "pending", token: null }),
      ),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));
    await screen.findByText(/scan with your phone/i);

    await userEvent.click(
      screen.getByRole("link", { name: /use this device instead/i }),
    );
    expect(assignSpy).toHaveBeenCalledWith(AUTHORIZE_URL);
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

  test("error → retry: clicking retry re-issues the request and shows the QR on success", async () => {
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
      http.get(`${BACKEND}/api/pairing/status/abc123`, () =>
        HttpResponse.json({ status: "pending", token: null }),
      ),
    );

    render(<PairingScreen />);
    await userEvent.click(screen.getByRole("button", { name: /start pairing/i }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    await screen.findByText(/scan with your phone/i);
    expect(calls).toBe(2);
  });
});
