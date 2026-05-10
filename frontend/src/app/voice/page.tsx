"use client";

/**
 * /voice — kiosk voice route.
 *
 * Mints a LiveKit JWT (POST /api/livekit/token), connects the browser to the
 * dev LiveKit server, publishes the local mic track, and plays back the
 * voice_worker's TTS via <RoomAudioRenderer />. The actual STT → LangGraph
 * → TTS loop runs in the voice_worker process — this page is just transport.
 *
 * Design: mic-tap activation per the design pass decision (always-on listening
 * deferred until we've dogfooded the kitchen acoustic environment). The big
 * mic button toggles `setMicrophoneEnabled`; idle state shows the agent
 * status pill so it's obvious the room is connected even when muted.
 *
 * Backwards-compat: this page is a leaf route, code-split by App Router. The
 * @livekit/components-react bundle (~150KB gzip) is only loaded when the user
 * navigates here, so the main kiosk shell stays unaffected.
 */
import { useCallback, useEffect, useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";

import { livekitApi, type LiveKitTokenResponse, ApiError } from "@/lib/api";
import { getToken } from "@/lib/auth";
import styles from "@/components/fridge/fridge.module.css";
import { AmbientLayer } from "@/components/fridge/ambient-layer";

type Status =
  | { kind: "loading" }
  | { kind: "no-auth" }
  | { kind: "error"; message: string }
  | { kind: "ready"; cred: LiveKitTokenResponse };

export default function VoicePage() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
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
  }, []);

  return (
    <div className={styles.fridgeRoot}>
      <AmbientLayer />
      {status.kind === "loading" && <CenteredCard title="Connecting voice…" />}
      {status.kind === "no-auth" && (
        <CenteredCard
          title="Pair this fridge first"
          subtitle="The voice channel needs a paired device. Open the kiosk shell and run pairing, then come back."
        />
      )}
      {status.kind === "error" && (
        <CenteredCard title="Voice unavailable" subtitle={status.message} />
      )}
      {status.kind === "ready" && (
        <LiveKitRoom
          serverUrl={status.cred.url}
          token={status.cred.token}
          // We turn on the mic via the toggle button (mic-tap), so default
          // connect with mic disabled. RoomAudioRenderer handles inbound audio.
          connect
          audio={false}
          video={false}
          options={{
            // adaptiveStream + dynacast cut bandwidth on idle — fine for one
            // mic stream but no harm enabling defaults.
            publishDefaults: { dtx: true },
          }}
          onError={(err) =>
            setStatus({ kind: "error", message: err.message })
          }
        >
          <VoiceShell />
          <RoomAudioRenderer />
        </LiveKitRoom>
      )}
    </div>
  );
}

function VoiceShell() {
  const { state: agentState, agent } = useVoiceAssistant();
  const { localParticipant } = useLocalParticipant();
  const [micOn, setMicOn] = useState(false);

  const toggleMic = useCallback(async () => {
    const next = !micOn;
    try {
      await localParticipant.setMicrophoneEnabled(next);
      setMicOn(next);
    } catch (err) {
      console.error("Mic toggle failed:", err);
    }
  }, [micOn, localParticipant]);

  return (
    <main
      style={{
        position: "relative",
        zIndex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.5rem",
        height: "100dvh",
        padding: "2rem",
      }}
    >
      <StatusPill agent={!!agent} state={agentState} micOn={micOn} />

      <button
        type="button"
        onClick={toggleMic}
        aria-pressed={micOn}
        aria-label={micOn ? "Mute microphone" : "Unmute microphone — talk to the fridge"}
        style={{
          width: "min(48vmin, 280px)",
          height: "min(48vmin, 280px)",
          borderRadius: "9999px",
          border: "none",
          cursor: "pointer",
          background: micOn
            ? "radial-gradient(circle at 30% 30%, #34d399 0%, #047857 100%)"
            : "radial-gradient(circle at 30% 30%, #94a3b8 0%, #334155 100%)",
          color: "white",
          fontSize: "1.25rem",
          fontWeight: 600,
          boxShadow: micOn
            ? "0 0 60px rgba(52, 211, 153, 0.55), 0 12px 40px rgba(0,0,0,0.25)"
            : "0 8px 30px rgba(0,0,0,0.3)",
          transition: "transform 120ms ease, box-shadow 200ms ease",
        }}
      >
        {micOn ? "Listening" : "Tap to talk"}
      </button>

      <p
        style={{
          maxWidth: "32rem",
          textAlign: "center",
          fontSize: "0.95rem",
          opacity: 0.75,
          color: "#1e293b",
        }}
      >
        Try: <em>“Add milk to the shopping list.”</em> ·{" "}
        <em>“What’s on the calendar today?”</em> ·{" "}
        <em>“What can I make with chicken and rice?”</em>
      </p>
    </main>
  );
}

function StatusPill({
  agent,
  state,
  micOn,
}: {
  agent: boolean;
  state: string;
  micOn: boolean;
}) {
  // Surface the most useful piece of info for whoever's standing at the fridge.
  // Agent state ("listening" / "thinking" / "speaking") wins when the agent is
  // present; otherwise show the mic state.
  let label = "Connected";
  if (!agent) label = "Waiting for the assistant to join…";
  else if (!micOn) label = "Tap the mic to talk";
  else if (state === "listening") label = "Listening";
  else if (state === "thinking") label = "Thinking…";
  else if (state === "speaking") label = "Speaking";
  return (
    <div
      style={{
        padding: "0.4rem 1rem",
        borderRadius: "9999px",
        background: "rgba(255,255,255,0.6)",
        backdropFilter: "blur(12px)",
        fontSize: "0.85rem",
        color: "#0f172a",
        boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
      }}
    >
      {label}
    </div>
  );
}

function CenteredCard({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <main
      style={{
        position: "relative",
        zIndex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.75rem",
        height: "100dvh",
        padding: "2rem",
      }}
    >
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600, color: "#0f172a" }}>
        {title}
      </h1>
      {subtitle && (
        <p
          style={{
            maxWidth: "32rem",
            textAlign: "center",
            color: "#475569",
          }}
        >
          {subtitle}
        </p>
      )}
    </main>
  );
}
