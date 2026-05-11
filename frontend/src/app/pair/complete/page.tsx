"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { setDeviceToken } from "@/lib/auth";
import { m } from "@/paraglide/messages.js";
import styles from "@/components/fridge/fridge.module.css";
import pairing from "@/components/fridge/pairing-screen.module.css";
import { AmbientLayer } from "@/components/fridge/ambient-layer";

const KIOSK_PAIRING_KEY = "fridge:kiosk_pairing_id";

/**
 * Landing route for the OAuth callback. Three states the page must handle:
 *
 *  - **Kiosk fallback path** (user clicked "Use this device" on the QR screen):
 *    same browser does OAuth on Google. The backend callback issues a 302
 *    here with `?token=<device-jwt>`. localStorage's `fridge:kiosk_pairing_id`
 *    is present because the kiosk wrote it before starting pairing. → persist
 *    the JWT and navigate to /.
 *
 *  - **Phone QR-scan path**: the kiosk shows a QR code, the user's phone
 *    scans it and completes OAuth, the backend 302s the *phone* here with
 *    the token in the URL. The phone's localStorage has no kiosk marker.
 *    → ignore the token, show "Pairing complete on the fridge — close this tab."
 *
 *  - **Missing token**: someone hit /pair/complete directly. Defensive only.
 */
export default function PairCompletePage() {
  return (
    <Suspense fallback={<PairingTransition />}>
      <PairCompleteInner />
    </Suspense>
  );
}

type Outcome = "transitioning" | "phone-done" | "missing-token";

function PairCompleteInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [outcome, setOutcome] = useState<Outcome>("transitioning");

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setOutcome("missing-token");
      return;
    }

    // Is this browser the kiosk that initiated pairing?
    let isKiosk = false;
    try {
      isKiosk = window.localStorage.getItem(KIOSK_PAIRING_KEY) !== null;
    } catch {
      // Some browsers (private mode on some platforms) throw on access. If
      // we can't read localStorage, assume phone — never silently log in a
      // device that didn't initiate the pairing.
      isKiosk = false;
    }

    if (isKiosk) {
      // Clear the marker; we're about to become a fully-paired kiosk.
      try {
        window.localStorage.removeItem(KIOSK_PAIRING_KEY);
      } catch {
        // ignore
      }
      setDeviceToken(token);
      router.replace("/");
      return;
    }

    // Phone path: backend ALSO wrote the JWT into Redis for the kiosk's
    // poll to pick up. So we just confirm to the user and stop.
    setOutcome("phone-done");
  }, [params, router]);

  if (outcome === "missing-token") {
    return (
      <div className={styles.fridgeRoot}>
        <AmbientLayer />
        <main className={pairing.stage} role="main">
          <div className={pairing.card}>
            <p className={pairing.eyebrow}>{m.pairing_screen_eyebrow()}</p>
            <h1 className={pairing.title}>{m.pairing_complete_missing_title()}</h1>
            <p className={pairing.subtitle}>{m.pairing_complete_missing_hint()}</p>
            <button
              type="button"
              className={pairing.primaryButton}
              onClick={() => router.replace("/pair")}
            >
              {m.pairing_retry_button()}
            </button>
          </div>
        </main>
      </div>
    );
  }

  if (outcome === "phone-done") {
    return (
      <div className={styles.fridgeRoot}>
        <AmbientLayer />
        <main className={pairing.stage} role="main">
          <div className={pairing.card}>
            <p className={pairing.eyebrow}>{m.pairing_screen_eyebrow()}</p>
            <h1 className={pairing.title}>{m.pairing_complete_on_phone_title()}</h1>
            <p className={pairing.subtitle}>
              {m.pairing_complete_on_phone_subtitle()}
            </p>
          </div>
        </main>
      </div>
    );
  }

  return <PairingTransition />;
}

function PairingTransition() {
  return (
    <div className={styles.fridgeRoot}>
      <AmbientLayer />
      <main className={pairing.stage} role="main">
        <div className={pairing.card}>
          <p className={pairing.eyebrow}>{m.pairing_screen_eyebrow()}</p>
          <h1 className={pairing.title}>{m.pairing_complete_title()}</h1>
          <p className={pairing.subtitle}>{m.pairing_complete_subtitle()}</p>
        </div>
      </main>
    </div>
  );
}
