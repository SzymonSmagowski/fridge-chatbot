"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useLocalParticipant,
  useVoiceAssistant,
} from "@livekit/components-react";
import "@livekit/components-styles";
import { Mic, MicOff } from "lucide-react";

import { m } from "@/paraglide/messages.js";
import styles from "./fridge.module.css";

/**
 * LiveKit-dependent inner shell for the voice overlay. Imported dynamically
 * (`next/dynamic`) by `voice-overlay.tsx` so the ~150 KB
 * `@livekit/components-react` bundle is only paid for when the user actually
 * opens the overlay — the chat tab's first-paint stays unaffected.
 *
 * Visual state machine (data-state on the orb):
 *   idle       — agent connected, mic muted (start state, or after user mute)
 *   connecting — LK room joining or agent worker not yet spawned
 *   listening  — mic hot, agent.state === "listening"
 *   thinking   — agent.state === "thinking" (LLM/tool turn)
 *   speaking   — agent.state === "speaking" (TTS playing)
 *
 * `useVoiceAssistant().state` already emits these phases from the worker side,
 * so we just mirror them onto a CSS attribute and let `fridge.module.css`
 * drive the animation. Mic-on is tracked separately because the room can be
 * connected with the local mic disabled (mute affordance).
 */

type Props = {
  credUrl: string;
  credToken: string;
  /** Hard error from the LiveKit room or our agent-join timeout. */
  onError: (message: string) => void;
  /**
   * Called when the conversation has naturally ended (sustained silence after
   * the user has had at least one turn). The parent overlay closes itself.
   */
  onClose: () => void;
};

/**
 * Time we'll wait for the voice_worker Agent to join the room after we
 * connect. If it doesn't (worker not running, OPENAI_API_KEY missing, etc.)
 * we surface a friendly error instead of wedging on "Waking up…".
 */
const AGENT_JOIN_TIMEOUT_MS = 15_000;

/**
 * After at least one *complete* turn (state has cycled through `speaking`,
 * meaning the agent actually replied), if the session stays in `listening`
 * this long with no follow-up, treat the conversation as over and
 * auto-close. Re-open by tapping the mic button or saying the wake word.
 *
 * Why we gate on `speaking` — not `thinking`: if the LLM runs but the TTS
 * pipeline is broken, the state cycles `listening → thinking → listening`
 * with no audible reply. Closing then would dismiss the overlay before the
 * user realised the agent was stuck. Requiring `speaking` means we only
 * auto-dismiss after a verifiably-completed exchange.
 */
const IDLE_AUTO_CLOSE_MS = 30_000;

export function VoiceSession({ credUrl, credToken, onError, onClose }: Props) {
  return (
    <LiveKitRoom
      serverUrl={credUrl}
      token={credToken}
      connect
      audio={false}
      video={false}
      options={{ publishDefaults: { dtx: true } }}
      onError={(err) => onError(err.message)}
      // `onDisconnected` only fires when the *local* participant drops
      // (network blip, manual unmount). When `voice_worker` calls
      // `session.aclose()` after the `end_session` tool, only the
      // **agent participant** leaves the room — the kiosk client stays
      // connected to a now-empty room, so this callback never runs in
      // the typical end-of-session flow. The agent-departure case is
      // handled inside VoiceShell via `useVoiceAssistant().agent`
      // transitioning from non-null back to null.
    >
      <VoiceShell onError={onError} onClose={onClose} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function VoiceShell({
  onError,
  onClose,
}: {
  onError: (message: string) => void;
  onClose: () => void;
}) {
  const { state: agentState, agent } = useVoiceAssistant();
  const { localParticipant } = useLocalParticipant();
  const [micOn, setMicOn] = useState(false);
  // These latches are render-irrelevant — keeping them in refs avoids tripping
  // `react-hooks/set-state-in-effect` and avoids superfluous re-renders.
  const autoEnabledRef = useRef(false);
  const hadFirstTurnRef = useRef(false);
  // Tracks whether we ever saw the agent participant present. Used to
  // distinguish "agent hasn't joined yet" (initial connect) from "agent
  // was here and left" (server-initiated end_session, worker crash, etc.).
  const everSawAgentRef = useRef(false);

  // Auto-enable mic the moment the agent worker joins. The user clicked the
  // mic button to open the overlay — we treat that as "I want to talk now,"
  // so don't make them tap again.
  useEffect(() => {
    if (!agent || autoEnabledRef.current) return;
    autoEnabledRef.current = true;
    void localParticipant
      .setMicrophoneEnabled(true)
      .then(() => setMicOn(true))
      .catch((err) => console.error("Auto-enable mic failed:", err));
  }, [agent, localParticipant]);

  // Agent-join timeout: if no Agent joins the room within AGENT_JOIN_TIMEOUT_MS
  // (worker not running, OPENAI_API_KEY missing, dispatch failed) surface a
  // clear error instead of leaving the user stuck on the "Waking up…" pill.
  useEffect(() => {
    if (agent) return;
    const id = setTimeout(() => {
      onError(m.voice_overlay_agent_timeout());
    }, AGENT_JOIN_TIMEOUT_MS);
    return () => clearTimeout(id);
  }, [agent, onError]);

  // Agent-departure watcher. When the voice_worker calls `session.aclose()`
  // (typically after the LLM uses the `end_session` tool), only the
  // **agent participant** leaves the room — the kiosk client stays
  // connected. `useVoiceAssistant().agent` flips from a Participant back
  // to `null`. We use that transition as the close signal: once we've seen
  // the agent (everSawAgentRef = true), any subsequent null means they
  // left, so dismiss the overlay. Without this, the overlay would freeze
  // on the green "Listening" orb indefinitely after a `to tyle` close.
  useEffect(() => {
    if (agent) {
      everSawAgentRef.current = true;
      return;
    }
    if (everSawAgentRef.current) {
      onClose();
    }
  }, [agent, onClose]);

  // Auto-close on sustained idle. The agent state cycles
  // listening → thinking → speaking → listening… so once `speaking` has
  // fired once (= the user spoke and the agent *audibly* replied) we know
  // a full exchange has completed. From then on, any time the state
  // settles back to `listening` we start an idle timer; any state change
  // resets it (the effect cleanup clears the previous timer). If the
  // timer reaches IDLE_AUTO_CLOSE_MS without a transition, the
  // conversation is considered over and we close the overlay.
  //
  // Gating on `speaking` (not `thinking`) is deliberate: if the LLM runs
  // but TTS produces no audio, the cycle `listening → thinking → listening`
  // would otherwise mark the session "complete" and auto-dismiss before
  // the user notices the agent never replied.
  useEffect(() => {
    if (agentState === "speaking") {
      hadFirstTurnRef.current = true;
    }
    if (!hadFirstTurnRef.current || agentState !== "listening") return;
    const id = setTimeout(onClose, IDLE_AUTO_CLOSE_MS);
    return () => clearTimeout(id);
  }, [agentState, onClose]);

  const toggleMic = useCallback(async () => {
    const next = !micOn;
    try {
      await localParticipant.setMicrophoneEnabled(next);
      setMicOn(next);
    } catch (err) {
      console.error("Mic toggle failed:", err);
    }
  }, [micOn, localParticipant]);

  const visualState: "idle" | "connecting" | "listening" | "thinking" | "speaking" =
    !agent
      ? "connecting"
      : !micOn
        ? "idle"
        : agentState === "thinking"
          ? "thinking"
          : agentState === "speaking"
            ? "speaking"
            : "listening";

  let label: string;
  if (!agent) label = m.voice_overlay_status_waking();
  else if (!micOn) label = m.voice_overlay_status_idle();
  else if (visualState === "thinking") label = m.voice_overlay_status_thinking();
  else if (visualState === "speaking") label = m.voice_overlay_status_speaking();
  else label = m.voice_overlay_status_listening();

  return (
    <div className={styles.voiceCenter}>
      <button
        type="button"
        onClick={toggleMic}
        aria-pressed={micOn}
        aria-label={
          micOn ? m.voice_overlay_mic_mute_aria() : m.voice_overlay_mic_unmute_aria()
        }
        className={styles.voiceOrb}
        data-state={visualState}
      >
        <span className={styles.voiceOrbRing} aria-hidden="true" />
        <span className={styles.voiceOrbRing} aria-hidden="true" />
        <span className={styles.voiceOrbRing} aria-hidden="true" />
        <span className={styles.voiceOrbCore}>
          {micOn ? <Mic size={48} /> : <MicOff size={48} />}
        </span>
      </button>
      <p className={styles.voiceStatus} aria-live="polite">
        {label}
      </p>
    </div>
  );
}
