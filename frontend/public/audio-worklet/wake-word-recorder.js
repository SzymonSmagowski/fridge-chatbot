/**
 * AudioWorklet processor for wake-word capture.
 *
 * Always emits exactly 1280-sample chunks at 16 kHz (= 80 ms windows),
 * regardless of the AudioContext's native sample rate. This is important:
 * Chrome respects the `new AudioContext({ sampleRate: 16000 })` hint on
 * most platforms but not all (and not in some Linux Chromium configs);
 * Safari often clamps to the device default (44.1 kHz / 48 kHz). If the
 * native rate isn't 16 kHz we decimate inside the worklet by an integer
 * ratio (48 kHz → 16 kHz = 3:1).
 *
 * Loaded as a static asset from `/audio-worklet/wake-word-recorder.js`.
 *
 * Debug: postMessage with `{ type: "stats" }` from the main thread to get a
 * one-shot dump of `{ nativeRate, decimation, chunksEmitted, lastRms }`.
 */

const TARGET_RATE_HZ = 16_000;
const TARGET_CHUNK_SAMPLES = 1280; // 80 ms at 16 kHz

class WakeWordRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    // `sampleRate` is a global available inside AudioWorkletProcessor,
    // representing the AudioContext's actual sample rate.
    this._nativeRate = sampleRate;
    this._decimation = Math.max(1, Math.round(this._nativeRate / TARGET_RATE_HZ));
    // Native samples we need to accumulate to produce one 80 ms output chunk
    // after decimation: TARGET_CHUNK_SAMPLES × decimation.
    this._nativeChunkSize = TARGET_CHUNK_SAMPLES * this._decimation;
    this._buffer = new Float32Array(this._nativeChunkSize);
    this._writeIndex = 0;
    this._chunksEmitted = 0;
    this._lastRms = 0;

    this.port.onmessage = (event) => {
      if (event.data?.type === "stats") {
        this.port.postMessage({
          type: "stats",
          nativeRate: this._nativeRate,
          decimation: this._decimation,
          chunksEmitted: this._chunksEmitted,
          lastRms: this._lastRms,
        });
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const samples = input[0];
    if (!samples || samples.length === 0) return true;

    for (let i = 0; i < samples.length; i++) {
      this._buffer[this._writeIndex++] = samples[i];
      if (this._writeIndex >= this._nativeChunkSize) {
        // Decimate by integer ratio. Naive (no anti-alias filter) — the
        // mel-spectrogram model is band-limited to ~8 kHz so high-frequency
        // aliasing has limited effect on detection. Sufficient for wake-word.
        const out = new Float32Array(TARGET_CHUNK_SAMPLES);
        let sumSq = 0;
        let peak = 0;
        for (let j = 0; j < TARGET_CHUNK_SAMPLES; j++) {
          const s = this._buffer[j * this._decimation];
          out[j] = s;
          sumSq += s * s;
          const a = Math.abs(s);
          if (a > peak) peak = a;
        }
        this._lastRms = Math.sqrt(sumSq / TARGET_CHUNK_SAMPLES);
        this._chunksEmitted++;
        this.port.postMessage({
          type: "chunk",
          samples: out,
          rms: this._lastRms,
          peak,
          chunkIndex: this._chunksEmitted,
        });
        this._writeIndex = 0;
      }
    }
    return true;
  }
}

registerProcessor("wake-word-recorder", WakeWordRecorder);
