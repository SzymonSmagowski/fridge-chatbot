"use client";

import { Mic } from "lucide-react";
import type { Metadata } from "next";

import styles from "@/components/fridge/fridge.module.css";

/**
 * Static preview of the voice overlay — sandboxed under /design-preview so the
 * screenshot tooling can capture the green "listening" orb without standing
 * up LiveKit, OpenAI, the voice_worker, or a paired device.
 *
 * Production behaviour lives in `src/components/fridge/voice-overlay.tsx`;
 * this file reuses the exact same CSS module so the visual output is identical.
 */
export default function VoicePreviewPage() {
  return (
    <div
      className={styles.voiceOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="Voice overlay preview"
    >
      <div className={styles.voiceCenter}>
        <div className={styles.voiceOrb} data-state="listening">
          <span className={styles.voiceOrbRing} aria-hidden="true" />
          <span className={styles.voiceOrbRing} aria-hidden="true" />
          <span className={styles.voiceOrbRing} aria-hidden="true" />
          <span className={styles.voiceOrbCore}>
            <Mic size={64} strokeWidth={2} />
          </span>
        </div>
        <p className={styles.voiceStatus}>Listening…</p>
        <p className={styles.voiceSubtitle}>
          Say &ldquo;Hey Jarvis, add eggs to the shopping list&rdquo;
        </p>
      </div>
    </div>
  );
}
