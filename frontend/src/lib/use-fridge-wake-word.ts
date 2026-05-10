"use client";

/**
 * Wake-word listener — passively listens to the kiosk microphone and fires
 * `onDetected` when the user says the activation phrase. Runs entirely
 * client-side via openWakeWord ONNX models (Apache-2.0): no API key, no
 * licence, no telemetry, no expiry. Mic audio never leaves the browser.
 *
 * Pipeline lives in `wake-word-pipeline.ts`. This hook is the React glue:
 * it owns one pipeline instance per mounted component and toggles its
 * `start`/`stop` based on the `enabled` prop (so the LiveKit voice overlay
 * can claim the mic without a fight).
 *
 * Failure mode: if model loading or mic-permission init fails, the hook
 * logs once and stays no-op. The kiosk falls back to mic-tap activation;
 * voice still works, just without the hands-free trigger.
 *
 * Setup: `dev.sh` runs `scripts/download-wake-word-models.sh` on first
 * start. That places three ONNX files in `public/wake-words/`. Nothing
 * else is required — no env vars, no accounts.
 */
import { useEffect, useRef } from "react";
import { WakeWordPipeline } from "./wake-word-pipeline";

type Options = {
  /** Called once per detection event. */
  onDetected: () => void;
  /**
   * Pass `false` while the voice overlay is open so the wake-word detector
   * releases the mic for LiveKit. Resumes automatically when this flips
   * back to `true`.
   */
  enabled: boolean;
};

export function useFridgeWakeWord({ onDetected, enabled }: Options): void {
  // Latest callback in a ref so the pipeline's detection listener doesn't
  // tear down on every render — `onDetected` is typically a fresh closure
  // each render, but the listener should survive across them.
  const callbackRef = useRef(onDetected);
  useEffect(() => {
    callbackRef.current = onDetected;
  }, [onDetected]);

  const pipelineRef = useRef<WakeWordPipeline | null>(null);

  // One mount-scoped effect creates the pipeline and tears it down. Tied to
  // [] so it doesn't churn on prop changes — model loading is expensive.
  useEffect(() => {
    const pipeline = new WakeWordPipeline();
    pipelineRef.current = pipeline;
    pipeline.onDetection(() => callbackRef.current());
    // Opt-in console logging — flip via devtools with
    //   localStorage.fridge_wake_word_debug = "1"
    // and reload. Logs cover: AudioContext rate + decimation, audio RMS
    // per ~second, wake probability per inference (when interesting), and
    // detection events. Acceptable in dev only — verbose in prod.
    if (typeof window !== "undefined" && window.localStorage?.getItem("fridge_wake_word_debug") === "1") {
      pipeline.setDebug(true);
      console.log(
        "[wake-word] debug mode ON. " +
          "Disable with `delete localStorage.fridge_wake_word_debug` then reload.",
      );
    }
    return () => {
      void pipeline.release();
      pipelineRef.current = null;
    };
  }, []);

  // Start/stop the audio capture in lockstep with `enabled`. Awaits init
  // internally — the pipeline caches a single in-flight init promise so
  // calling .init() repeatedly is a no-op after the first call.
  useEffect(() => {
    const pipeline = pipelineRef.current;
    if (!pipeline) return;
    let cancelled = false;
    void (async () => {
      try {
        await pipeline.init();
        if (cancelled) return;
        if (enabled) {
          await pipeline.start();
        } else {
          await pipeline.stop();
        }
      } catch (err) {
        if (!cancelled) {
          console.warn(
            "[wake-word] pipeline error — falling back to mic-tap:",
            err,
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);
}
