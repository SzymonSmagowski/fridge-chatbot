"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import styles from "./fridge.module.css";
import { ApiError, oauthApi } from "@/lib/api";
import { useFamilyEvents, type FamilyEventPayload } from "@/lib/use-family-events";
import { m } from "@/paraglide/messages.js";

export interface ConnectGoogleModalProps {
  open: boolean;
  memberId: string | null;
  memberName: string | null;
  onClose: () => void;
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; authorizeUrl: string }
  | { kind: "error"; message: string };

/**
 * Phone-friendly OAuth onboarding for a member's Google Calendar. Renders the
 * server-issued authorize URL as a QR code so the family member can scan with
 * their phone — they then sign in to Google in their phone's browser without
 * typing on the kiosk. The kiosk learns the connection succeeded via the
 * family-events WebSocket (`member.google_connected`) and dismisses itself.
 *
 * The fallback link below the QR opens the same URL on the kiosk's own
 * browser — useful when no phone is handy or the kiosk isn't on a network the
 * phone can reach (e.g. local-dev `localhost:8001`).
 */
export function ConnectGoogleModal({
  open,
  memberId,
  memberName,
  onClose,
}: ConnectGoogleModalProps) {
  const [state, setState] = useState<State>({ kind: "loading" });

  // Fetch the authorize URL once per open + memberId. Re-running on `open`
  // toggle gives the user a fresh URL if they reopen after the first expired.
  useEffect(() => {
    if (!open || !memberId) return;
    let cancelled = false;
    setState({ kind: "loading" });
    oauthApi
      .authorize(memberId)
      .then((res) => {
        if (cancelled) return;
        setState({ kind: "ready", authorizeUrl: res.authorize_url });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError ? err.message : m.connect_google_modal_error();
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [open, memberId]);

  // Hold live values in a ref so the listener can keep `[]` deps and a stable
  // identity. Without this, `onClose`/`memberName` (often inline arrow funcs
  // in the parent) would change identity each render → useFamilyEvents would
  // re-subscribe each render → render storm under load.
  const liveProps = useRef({ open, memberId, memberName, onClose });
  liveProps.current = { open, memberId, memberName, onClose };

  const onFamilyEvent = useCallback((payload?: FamilyEventPayload) => {
    const { open: o, memberId: mid, memberName: mname, onClose: close } =
      liveProps.current;
    if (!o || !mid) return;
    if (
      payload?.type === "member.google_connected" &&
      payload?.id === mid
    ) {
      toast.success(
        mname
          ? m.connect_google_success_with_name({ name: mname })
          : m.connect_google_success_generic(),
      );
      close();
    }
  }, []);
  useFamilyEvents(onFamilyEvent);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !memberId) return null;

  return (
    <div
      className={styles.confirmDialogBackdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="connect-google-title"
      onClick={onClose}
    >
      <div
        className={styles.confirmDialog}
        style={{ maxWidth: 460 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="connect-google-title">
          {memberName
            ? m.connect_google_modal_title_with_name({ name: memberName })
            : m.connect_google_modal_title_generic()}
        </h3>
        <p style={{ marginBottom: 8 }}>{m.connect_google_modal_subtitle()}</p>

        <div
          style={{
            display: "flex",
            justifyContent: "center",
            padding: "16px 0 12px",
            minHeight: 240,
            alignItems: "center",
          }}
        >
          {state.kind === "loading" ? (
            <div style={{ color: "var(--muted-fg)", fontSize: 14 }}>
              {m.connect_google_modal_loading()}
            </div>
          ) : state.kind === "error" ? (
            <div
              role="alert"
              style={{
                color: "var(--destructive)",
                fontSize: 14,
                textAlign: "center",
              }}
            >
              {state.message}
            </div>
          ) : (
            <div
              style={{
                background: "#fff",
                padding: 16,
                borderRadius: "var(--fridge-radius)",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <QRCodeSVG
                value={state.authorizeUrl}
                size={216}
                level="M"
                marginSize={0}
              />
            </div>
          )}
        </div>

        {state.kind === "ready" ? (
          <p
            style={{
              fontSize: 13,
              color: "var(--muted-fg)",
              textAlign: "center",
              margin: "4px 0 16px",
            }}
          >
            <a
              href={state.authorizeUrl}
              target="_self"
              rel="noopener"
              style={{
                color: "var(--accent)",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              {m.connect_google_modal_use_this_device()}
            </a>
          </p>
        ) : null}

        <div className={styles.confirmActions}>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnGhost} ${styles.btnSmall}`}
            onClick={onClose}
          >
            {m.common_cancel()}
          </button>
        </div>
      </div>
    </div>
  );
}
