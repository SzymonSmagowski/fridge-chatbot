"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { ApiError, pairingApi } from "@/lib/api";
import { setDeviceToken } from "@/lib/auth";
import { m } from "@/paraglide/messages.js";
import styles from "./fridge.module.css";
import pairing from "./pairing-screen.module.css";
import { AmbientLayer } from "./ambient-layer";

type PairingState =
  | { kind: "idle" }
  | { kind: "starting" }
  | {
      kind: "polling";
      pairingId: string;
      authorizeUrl: string;
    }
  | { kind: "redirecting" }  // fallback "use this device" branch
  | { kind: "expired" }
  | { kind: "error"; message: string };

const POLL_INTERVAL_MS = 2000;
const KIOSK_PAIRING_KEY = "fridge:kiosk_pairing_id";

/**
 * First-boot kiosk screen.
 *
 * 1. POST /api/pairing/start → receive {pairing_id, authorize_url}.
 * 2. Render authorize_url as a QR code; user scans with their phone and
 *    completes Google OAuth there (no typing on the fridge).
 * 3. Poll /api/pairing/status/<id> every 2s. The backend's OAuth callback
 *    writes the device JWT to a short-lived Redis key after the transaction
 *    commits; the poll picks it up exactly once.
 * 4. On `complete`, persist the JWT to localStorage and navigate to /.
 *
 * Fallback: "Use this device instead" link triggers the legacy direct-redirect
 * path. The kiosk's browser navigates to Google → /pair/complete page reads
 * the token from the URL (the kiosk_pairing_id localStorage marker tells that
 * page it's the kiosk and should persist).
 */
export function PairingScreen() {
  const [state, setState] = useState<PairingState>({ kind: "idle" });

  // Pre-baked greeting strings; pulled out so the render block stays clean.
  const startLabel =
    state.kind === "starting" || state.kind === "redirecting"
      ? m.pairing_starting()
      : state.kind === "error"
        ? m.pairing_retry_button()
        : m.pairing_start_button();

  const start = useCallback(async () => {
    setState({ kind: "starting" });
    try {
      const res = await pairingApi.start("Kitchen Fridge");
      // Tag this browser as the kiosk for this pairing. /pair/complete uses
      // this marker to decide whether to persist the JWT or just show a
      // "you're done, return to your fridge" terminal page.
      try {
        window.localStorage.setItem(KIOSK_PAIRING_KEY, res.pairing_id);
      } catch {
        // localStorage can throw in private-mode browsers; non-fatal — the
        // polling path doesn't need the marker, only the fallback does.
      }
      setState({
        kind: "polling",
        pairingId: res.pairing_id,
        authorizeUrl: res.authorize_url,
      });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : m.pairing_error_hint();
      setState({ kind: "error", message });
    }
  }, []);

  // Polling loop. Lives in a ref so re-renders don't restart the interval.
  // Stops when the state leaves "polling" — see effect cleanup.
  const stateRef = useRef(state);
  stateRef.current = state;
  useEffect(() => {
    if (state.kind !== "polling") return;
    const pairingId = state.pairingId;

    let cancelled = false;
    const tick = async () => {
      try {
        const res = await pairingApi.status(pairingId);
        if (cancelled) return;
        if (res.status === "complete" && res.token) {
          setDeviceToken(res.token);
          try {
            window.localStorage.removeItem(KIOSK_PAIRING_KEY);
          } catch {
            // ignore
          }
          // Hard navigate so the app shell sees the new auth cookie on first
          // paint. router.replace would work too but a full reload is what
          // the existing /pair/complete handler does, so we match.
          window.location.assign("/");
          return;
        }
        if (res.status === "expired") {
          setState({ kind: "expired" });
          return;
        }
        // status === "pending" → keep polling.
      } catch {
        // Network blips are common (kiosk on flaky wifi during setup).
        // Swallow and let the next tick retry; only a `expired` status from
        // the server is a terminal failure.
      }
    };

    // Fire immediately so a fast phone completes within sub-2s.
    void tick();
    const handle = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [state]);

  const useThisDevice = useCallback(() => {
    if (state.kind !== "polling") return;
    setState({ kind: "redirecting" });
    window.location.assign(state.authorizeUrl);
  }, [state]);

  const retry = useCallback(() => {
    try {
      window.localStorage.removeItem(KIOSK_PAIRING_KEY);
    } catch {
      // ignore
    }
    setState({ kind: "idle" });
  }, []);

  return (
    <div className={styles.fridgeRoot}>
      <AmbientLayer />
      <main className={pairing.stage} role="main">
        <div className={pairing.card}>
          {state.kind === "polling" ? (
            <PollingBody
              authorizeUrl={state.authorizeUrl}
              onUseThisDevice={useThisDevice}
            />
          ) : state.kind === "expired" ? (
            <ExpiredBody onRetry={retry} />
          ) : (
            <IdleBody
              state={state}
              startLabel={startLabel}
              isBusy={
                state.kind === "starting" || state.kind === "redirecting"
              }
              onStart={start}
            />
          )}
        </div>
      </main>
    </div>
  );
}

function IdleBody({
  state,
  startLabel,
  isBusy,
  onStart,
}: {
  state: PairingState;
  startLabel: string;
  isBusy: boolean;
  onStart: () => void;
}) {
  return (
    <>
      <p className={pairing.eyebrow}>{m.pairing_screen_eyebrow()}</p>
      <h1 className={pairing.title}>{m.pairing_screen_title()}</h1>
      <p className={pairing.subtitle}>{m.pairing_screen_subtitle()}</p>

      {state.kind === "error" ? (
        <div className={pairing.errorBox} role="alert">
          <strong>{m.pairing_error_title()}</strong>
          <span>{state.message}</span>
        </div>
      ) : null}

      <button
        type="button"
        className={pairing.primaryButton}
        onClick={onStart}
        disabled={isBusy}
      >
        {startLabel}
      </button>

      <p className={pairing.hint}>{m.pairing_redirect_hint()}</p>
    </>
  );
}

function PollingBody({
  authorizeUrl,
  onUseThisDevice,
}: {
  authorizeUrl: string;
  onUseThisDevice: () => void;
}) {
  return (
    <>
      <p className={pairing.eyebrow}>{m.pairing_screen_eyebrow()}</p>
      <h1 className={pairing.title}>{m.pairing_qr_title()}</h1>
      <p className={pairing.subtitle}>{m.pairing_qr_subtitle()}</p>

      <div
        style={{
          display: "flex",
          justifyContent: "center",
          padding: "16px 0 12px",
        }}
      >
        <div
          style={{
            background: "#fff",
            padding: 16,
            borderRadius: "var(--fridge-radius)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <QRCodeSVG value={authorizeUrl} size={240} level="M" marginSize={0} />
        </div>
      </div>

      <p className={pairing.hint} aria-live="polite">
        {m.pairing_qr_waiting()}
      </p>

      <p
        style={{
          fontSize: 13,
          textAlign: "center",
          margin: "12px 0 0",
        }}
      >
        <a
          href={authorizeUrl}
          onClick={(e) => {
            e.preventDefault();
            onUseThisDevice();
          }}
          style={{
            color: "var(--accent)",
            textDecoration: "underline",
            textUnderlineOffset: 3,
          }}
        >
          {m.pairing_qr_use_this_device()}
        </a>
      </p>
    </>
  );
}

function ExpiredBody({ onRetry }: { onRetry: () => void }) {
  return (
    <>
      <p className={pairing.eyebrow}>{m.pairing_screen_eyebrow()}</p>
      <h1 className={pairing.title}>{m.pairing_qr_expired_title()}</h1>
      <p className={pairing.subtitle}>{m.pairing_qr_expired_hint()}</p>
      <button
        type="button"
        className={pairing.primaryButton}
        onClick={onRetry}
      >
        {m.pairing_retry_button()}
      </button>
    </>
  );
}
