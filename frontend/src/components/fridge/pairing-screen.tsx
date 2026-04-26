"use client";
import { useCallback, useState } from "react";
import { ApiError, pairingApi } from "@/lib/api";
import { m } from "@/paraglide/messages.js";
import styles from "./fridge.module.css";
import pairing from "./pairing-screen.module.css";
import { AmbientLayer } from "./ambient-layer";

type PairingState =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "redirecting" }
  | { kind: "error"; message: string };

/**
 * First-boot kiosk screen. Calls POST /api/pairing/start (Architect §5.1) and
 * redirects the browser to Google's consent URL. Google then redirects to
 * GET /oauth/google/callback?state=pair:<id> on the backend, which completes
 * the pair atomically and 302s back to the frontend with `?token=<jwt>` —
 * see `app/pair/complete/page.tsx` for the landing handler.
 *
 * The flow is single-screen and redirect-based; there is no polling and no
 * separate phone-side step in the current backend contract.
 */
export function PairingScreen() {
  const [state, setState] = useState<PairingState>({ kind: "idle" });

  const start = useCallback(async () => {
    setState({ kind: "starting" });
    try {
      const res = await pairingApi.start("Kitchen Fridge");
      setState({ kind: "redirecting" });
      window.location.assign(res.authorize_url);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : m.pairing_error_hint();
      setState({ kind: "error", message });
    }
  }, []);

  const isBusy = state.kind === "starting" || state.kind === "redirecting";

  return (
    <div className={styles.fridgeRoot}>
      <AmbientLayer />
      <main className={pairing.stage} role="main">
        <div className={pairing.card}>
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
            onClick={start}
            disabled={isBusy}
          >
            {state.kind === "starting" || state.kind === "redirecting"
              ? m.pairing_starting()
              : state.kind === "error"
                ? m.pairing_retry_button()
                : m.pairing_start_button()}
          </button>

          <p className={pairing.hint}>{m.pairing_redirect_hint()}</p>

          <a className={pairing.escapeLink} href="/login">
            {m.pairing_back_to_login()}
          </a>
        </div>
      </main>
    </div>
  );
}
