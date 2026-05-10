"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Mic } from "lucide-react";

import { livekitApi, type LiveKitTokenResponse, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import {
  useFamilyEvents,
  type FamilyEventPayload,
} from "@/lib/use-family-events";
import { m } from "@/paraglide/messages.js";
import styles from "./fridge.module.css";

/**
 * Voice overlay — opens above the chat composer when the user taps the mic
 * button. Replaces the standalone `/voice` route as the primary entry point;
 * the kiosk shell stays mounted underneath, dimmed but visible (the user
 * stays in the app, doesn't navigate away).
 *
 * The LiveKit-dependent `VoiceSession` is `next/dynamic`-imported so the
 * ~150 KB `@livekit/components-react` bundle is paid only when the overlay
 * actually opens — the chat tab's first paint is unaffected.
 *
 * Token fetch happens here (outer) so the inner session can stay focused on
 * the room lifecycle. Each open mints a fresh token and tears down on close.
 */

const VoiceSession = dynamic(
  () => import("./voice-session").then((mod) => mod.VoiceSession),
  { ssr: false, loading: () => <ConnectingState /> },
);

type Props = {
  open: boolean;
  onClose: () => void;
};

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "no-auth" }
  | { kind: "error"; message: string }
  | { kind: "ready"; cred: LiveKitTokenResponse };

export function VoiceOverlay({ open, onClose }: Props) {
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  // Server-driven dismiss: voice_worker publishes `voice_session.ended` to
  // the family-events channel right before closing the LiveKit session
  // (after the LLM uses `end_session` and the goodbye TTS finishes).
  // Listening here gives us a deterministic close — independent of
  // LiveKit's participant-disconnect signal which doesn't reliably
  // propagate through `useVoiceAssistant().agent === null`.
  useFamilyEvents((event: FamilyEventPayload | undefined) => {
    if (!open) return;
    if (event?.type === "voice_session.ended") {
      onClose();
    }
  });

  useEffect(() => {
    if (!open) {
      // Sync: when the parent closes us, reset so the next open-cycle starts
      // from a clean slate (no stale "ready" token leaking into the next
      // session). Same prop-driven sync pattern used in chat-view.tsx.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setStatus({ kind: "loading" });
    void (async () => {
      const token = getToken();
      if (!token) {
        if (!cancelled) setStatus({ kind: "no-auth" });
        return;
      }
      try {
        const cred = await livekitApi.mintToken();
        if (!cancelled) setStatus({ kind: "ready", cred });
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof ApiError
            ? `Backend rejected the token request (${err.status}). ${err.message}`
            : err instanceof Error
              ? err.message
              : "Could not reach the backend.";
        setStatus({ kind: "error", message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className={styles.voiceOverlay}
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        // Backdrop tap dismisses — kept as a recovery affordance, but no
        // visible close button: the overlay auto-closes when the conversation
        // ends (`voice-session` calls `onClose` after a sustained-idle window).
        // ESC also closes (see effect below) for devs / a11y.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {status.kind === "loading" && <ConnectingState />}
      {status.kind === "no-auth" && (
        <CenteredMessage
          title={m.voice_overlay_no_auth_title()}
          subtitle={m.voice_overlay_no_auth_sub()}
        />
      )}
      {status.kind === "error" && (
        <CenteredMessage title={m.voice_overlay_error_title()} subtitle={status.message} />
      )}
      {status.kind === "ready" && (
        <VoiceSession
          credUrl={status.cred.url}
          credToken={status.cred.token}
          onError={(message) => setStatus({ kind: "error", message })}
          onClose={onClose}
        />
      )}
    </div>
  );
}

function ConnectingState() {
  return (
    <div className={styles.voiceCenter}>
      <div className={styles.voiceOrb} data-state="connecting">
        <span className={styles.voiceOrbRing} aria-hidden="true" />
        <span className={styles.voiceOrbRing} aria-hidden="true" />
        <span className={styles.voiceOrbRing} aria-hidden="true" />
        <span className={styles.voiceOrbCore}>
          <Mic size={48} />
        </span>
      </div>
      <p className={styles.voiceStatus}>{m.voice_overlay_status_connecting()}</p>
    </div>
  );
}

function CenteredMessage({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className={styles.voiceCenter}>
      <h2 className={styles.voiceTitle}>{title}</h2>
      {subtitle && <p className={styles.voiceSubtitle}>{subtitle}</p>}
    </div>
  );
}
