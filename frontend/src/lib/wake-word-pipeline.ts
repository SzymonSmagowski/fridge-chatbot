"use client";

/**
 * openWakeWord ONNX inference pipeline (browser, fully local).
 *
 * Three chained models, all running via onnxruntime-web (WASM). No vendor
 * SDK, no API key, no network call after the initial model fetch from
 * `public/wake-words/`.
 *
 *   raw 16 kHz audio (1280-sample chunks, 80 ms each)
 *      ↓ melspectrogram.onnx
 *   mel frames (8 new frames per 80 ms; rolling 76-frame window)
 *      ↓ embedding_model.onnx (Google speech_embedding)
 *   speech embedding (96-dim vector per 80 ms; rolling 16-vector buffer)
 *      ↓ hey_jarvis_v0.1.onnx
 *   wake probability ∈ [0, 1]; cross threshold → fire detection
 *
 * Cadence: ~12.5 inference passes per second. Each pass is well under 10 ms
 * on a modern laptop's WASM backend; comfortably real-time.
 *
 * Tensor shapes (from openWakeWord's Python source — verified at pin tag
 * v0.5.1; bumping the model tag in `download-wake-word-models.sh` requires
 * re-validating these):
 *   melspectrogram   in:  float32 [1, n_samples]            (n_samples=1280)
 *                    out: float32 [1, 1, n_mel_frames, 32]   (5 frames per 1280 samples)
 *   embedding_model  in:  float32 [1, 76, 32, 1]              (frames, mel_bins, channels)
 *                    out: float32 [1, 1, 1, 96]
 *   hey_jarvis       in:  float32 [1, 16, 96]
 *                    out: float32 [1, 1]
 *
 * Verified empirically against the v0.5.1 ONNX files via a Node smoke-test —
 * shapes do not match the dim spec given in openWakeWord's Python wrapper
 * (their Keras model is image-shaped HWC; the exported ONNX preserves that).
 *
 * The pipeline keeps two rolling buffers internally: `melBuffer` (last 76
 * frames; ~6 chunks worth) and `embeddingBuffer` (last 16 embeddings;
 * ~1.28 s of context). Both are dropped to zero after a detection so the
 * cooldown debounces consecutive triggers from the same utterance.
 */
import * as ort from "onnxruntime-web";

const MODEL_BASE = "/wake-words";
const SAMPLE_RATE_HZ = 16_000;
// Chunk size (80 ms at 16 kHz = 1280 samples) is hardcoded in the worklet
// processor at `public/audio-worklet/wake-word-recorder.js`; we accept
// whatever it posts.
const MEL_WINDOW = 76; // frames — embedding model expects exactly 76 × 32
const MEL_BINS = 32;
const EMBEDDING_DIM = 96;
const EMBEDDING_WINDOW = 16; // classifier expects sequence of 16 embeddings
const DEFAULT_THRESHOLD = 0.5;
const COOLDOWN_MS = 2_000; // suppress duplicate fires from a single utterance

type DetectionListener = (probability: number) => void;

export class WakeWordPipeline {
  private melSession: ort.InferenceSession | null = null;
  private embeddingSession: ort.InferenceSession | null = null;
  private classifierSession: ort.InferenceSession | null = null;
  // Cached init promise so concurrent callers (e.g. the React strict-mode
  // double-invocation of effects) don't race on model loading.
  private initPromise: Promise<void> | null = null;

  private audioContext: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private mediaStream: MediaStream | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;

  // Rolling mel-frame buffer. Each entry is one mel frame (32 floats).
  private melBuffer: Float32Array[] = [];
  // Rolling embedding buffer. Each entry is one 96-dim embedding.
  private embeddingBuffer: Float32Array[] = [];

  // The worklet handles native-rate → 16 kHz decimation internally and
  // always emits exactly TARGET_CHUNK_SAMPLES (1280) samples per message;
  // no main-thread downsampling needed.

  // Inference is async; if a chunk arrives while the previous one is still
  // running we drop it. Wake-word doesn't need every frame — missing one in
  // ten doesn't change detection latency in practice.
  private inferenceInFlight = false;
  private lastDetectionAt = 0;
  // Debug counters — surfaced via console.log when `setDebug(true)` so the
  // user can see whether audio is reaching the pipeline and what
  // probabilities the model is producing.
  private chunksReceived = 0;
  private inferencesRun = 0;
  private debug = false;

  private listeners = new Set<DetectionListener>();
  private threshold = DEFAULT_THRESHOLD;

  /** Fetch all three ONNX models. Idempotent + concurrent-safe — multiple
   * callers receive the same promise and only one model load actually runs.
   */
  init(): Promise<void> {
    if (this.initPromise) return this.initPromise;
    this.initPromise = (async () => {
      // onnxruntime-web auto-locates its `.wasm` runtime from the host page's
      // origin via a CDN by default. We pin threading to 1 — simpler,
      // deterministic, and wake-word inference is cheap enough not to need
      // it.
      ort.env.wasm.numThreads = 1;

      [this.melSession, this.embeddingSession, this.classifierSession] =
        await Promise.all([
          ort.InferenceSession.create(`${MODEL_BASE}/melspectrogram.onnx`),
          ort.InferenceSession.create(`${MODEL_BASE}/embedding_model.onnx`),
          ort.InferenceSession.create(`${MODEL_BASE}/hey_jarvis_v0.1.onnx`),
        ]);
    })();
    return this.initPromise;
  }

  /**
   * Open the mic and start the inference loop. Throws if `init()` hasn't
   * run successfully, or if the browser denies microphone permission.
   */
  async start(): Promise<void> {
    if (!this.melSession || !this.embeddingSession || !this.classifierSession) {
      throw new Error("WakeWordPipeline: must call init() before start()");
    }
    if (this.audioContext) return; // already running

    // Request 16 kHz directly. Chromium honours this on most platforms but
    // not all; the worklet decimates internally if the actual rate differs,
    // so the main-thread pipeline always sees 16 kHz chunks regardless.
    this.audioContext = new AudioContext({ sampleRate: SAMPLE_RATE_HZ });
    const actualRate = this.audioContext.sampleRate;
    if (actualRate !== SAMPLE_RATE_HZ) {
      if (actualRate % SAMPLE_RATE_HZ !== 0) {
        console.warn(
          `[wake-word] non-integer sample-rate ratio ` +
            `(${actualRate} → ${SAMPLE_RATE_HZ}); detection may be unreliable.`,
        );
      } else if (this.debug) {
        console.log(
          `[wake-word] AudioContext at ${actualRate} Hz; ` +
            `worklet will decimate ${actualRate / SAMPLE_RATE_HZ}:1 to 16 kHz.`,
        );
      }
    } else if (this.debug) {
      console.log(`[wake-word] AudioContext at native 16 kHz, no decimation`);
    }

    await this.audioContext.audioWorklet.addModule(
      "/audio-worklet/wake-word-recorder.js",
    );

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        // Disable Chrome's audio post-processing for the wake-word path:
        // - echoCancellation has been observed to over-suppress speech when
        //   no reference signal is playing back (no AEC reference → AEC
        //   treats everything as echo and ducks). Detection RMS dropped
        //   from ~0.05 (speech) to ~0.003 (noise floor) with it on.
        // - noiseSuppression aggressively gates anything below a learned
        //   threshold; whispered or distant speech gets killed.
        // - autoGainControl is left ON so the model sees comparable levels
        //   regardless of how close the user is to the mic.
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    if (this.debug) {
      const track = this.mediaStream.getAudioTracks()[0];
      const settings = track?.getSettings?.();
      console.log(
        `[wake-word] mic: "${track?.label ?? "?"}" ` +
          `settings=${JSON.stringify(settings ?? {})}`,
      );
    }
    this.sourceNode = this.audioContext.createMediaStreamSource(
      this.mediaStream,
    );
    this.workletNode = new AudioWorkletNode(
      this.audioContext,
      "wake-word-recorder",
    );
    this.sourceNode.connect(this.workletNode);
    // Worklet doesn't render audio out — just a one-way data tap, no
    // connection to `audioContext.destination` needed.

    this.workletNode.port.onmessage = (event: MessageEvent) => {
      if (event.data?.type !== "chunk") return;
      const samples = event.data.samples as Float32Array | undefined;
      const rms = event.data.rms as number | undefined;
      const peak = event.data.peak as number | undefined;
      if (!samples) return;
      this.chunksReceived++;
      // Log on a heartbeat AND on any chunk with non-trivial audio activity
      // so the user can see exactly which chunks captured their speech and
      // which were silent. RMS > 0.01 = clearly speech; peak > 0.05 = a
      // single loud sample. Both fire the "loud" tag.
      const heartbeat = this.chunksReceived % 12 === 1;
      const loud = (rms ?? 0) > 0.01 || (peak ?? 0) > 0.05;
      if (this.debug && (heartbeat || loud)) {
        console.log(
          `[wake-word] chunk #${this.chunksReceived}: ` +
            `rms=${rms?.toFixed(4)} peak=${peak?.toFixed(4)} ` +
            (loud ? "🔊 SPEECH" : "(quiet)"),
        );
      }
      void this.handleChunk(samples);
    };
  }

  /** Toggle debug-mode console logging. Reads `localStorage.fridge_wake_word_debug`
   * by default but can be flipped at runtime.
   */
  setDebug(value: boolean): void {
    this.debug = value;
  }

  /** Stop the mic and release WebAudio resources. ONNX sessions stay
   * loaded so a subsequent `start()` is fast.
   */
  async stop(): Promise<void> {
    if (this.workletNode) {
      this.workletNode.port.onmessage = null;
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.mediaStream) {
      for (const track of this.mediaStream.getTracks()) track.stop();
      this.mediaStream = null;
    }
    if (this.audioContext) {
      await this.audioContext.close();
      this.audioContext = null;
    }
    this.melBuffer = [];
    this.embeddingBuffer = [];
    this.inferenceInFlight = false;
  }

  /** Tear down everything including the loaded ONNX sessions. */
  async release(): Promise<void> {
    await this.stop();
    this.melSession?.release();
    this.embeddingSession?.release();
    this.classifierSession?.release();
    this.melSession = null;
    this.embeddingSession = null;
    this.classifierSession = null;
    this.initPromise = null;
  }

  onDetection(listener: DetectionListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setThreshold(value: number): void {
    this.threshold = value;
  }

  /** Run one chunk through the three ONNX sessions and update the rolling
   * buffers. Drops the chunk if a previous inference is still in flight —
   * wake-word doesn't need every frame.
   */
  private async handleChunk(samples: Float32Array): Promise<void> {
    if (this.inferenceInFlight) return;
    this.inferenceInFlight = true;
    try {
      const melFrames = await this.runMel(samples);
      this.appendMelFrames(melFrames);
      if (this.melBuffer.length < MEL_WINDOW) return;

      const embedding = await this.runEmbedding();
      this.appendEmbedding(embedding);
      if (this.embeddingBuffer.length < EMBEDDING_WINDOW) return;

      const probability = await this.runClassifier();
      this.inferencesRun++;

      // Debug: log probability whenever it's non-trivial (might be a near-
      // miss) and a heartbeat at low cadence so we know inference is alive.
      if (this.debug) {
        if (probability > 0.05 || this.inferencesRun % 24 === 1) {
          console.log(
            `[wake-word] inference #${this.inferencesRun}: ` +
              `prob=${probability.toFixed(4)} ` +
              `${probability >= this.threshold ? "🎯 FIRING" : ""}`,
          );
        }
      }

      if (probability >= this.threshold) {
        const now = Date.now();
        if (now - this.lastDetectionAt < COOLDOWN_MS) return;
        this.lastDetectionAt = now;
        // Reset rolling buffers post-detection so the next utterance starts
        // from a clean state and we don't immediately re-fire from the tail
        // of the wake phrase still sitting in the buffer.
        this.embeddingBuffer = [];
        for (const listener of this.listeners) listener(probability);
      }
    } catch (err) {
      console.warn("[wake-word] inference error:", err);
    } finally {
      this.inferenceInFlight = false;
    }
  }

  private async runMel(samples: Float32Array): Promise<Float32Array[]> {
    // openWakeWord's mel model was trained with int16 PCM cast to float32 —
    // i.e., a sample at half-amplitude is `16384.0`, not `0.5`. Web Audio
    // hands us [-1, 1] floats (audio-engineering convention), so we scale
    // by 32768 to match. Without this the model sees real speech as 30,000×
    // quieter than its training distribution and outputs near-zero for
    // everything.
    const scaled = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) scaled[i] = samples[i] * 32768;
    const tensor = new ort.Tensor("float32", scaled, [1, scaled.length]);
    const out = await this.melSession!.run({ input: tensor });
    const t = out.output as ort.Tensor;
    // openWakeWord's mel output: [1, 1, n_frames, 32]. Pull frames out and
    // apply the openWakeWord normalization `(x / 10) + 2` — this maps the
    // raw mel values into the distribution the embedding model expects.
    // Without this step the classifier sees random-looking embeddings and
    // outputs ~0 for any input, including correctly-pronounced wake words.
    // (Reference: openWakeWord/openwakeword/model.py — applied between the
    // melspec and embedding stages of every prediction.)
    const data = t.data as Float32Array;
    const nFrames = t.dims[2];
    const frames: Float32Array[] = [];
    for (let i = 0; i < nFrames; i++) {
      const frame = new Float32Array(MEL_BINS);
      for (let j = 0; j < MEL_BINS; j++) {
        frame[j] = data[i * MEL_BINS + j] / 10 + 2;
      }
      frames.push(frame);
    }
    return frames;
  }

  private appendMelFrames(frames: Float32Array[]): void {
    for (const f of frames) this.melBuffer.push(f);
    while (this.melBuffer.length > MEL_WINDOW) this.melBuffer.shift();
  }

  private async runEmbedding(): Promise<Float32Array> {
    const flat = new Float32Array(MEL_WINDOW * MEL_BINS);
    for (let i = 0; i < MEL_WINDOW; i++) {
      flat.set(this.melBuffer[i], i * MEL_BINS);
    }
    // Embedding model expects `[1, 76, 32, 1]` (frames, mel_bins, channels=1).
    // Our packed `flat` is row-major frames × bins, which matches this layout
    // because the trailing channel dim has size 1 — no reshape needed.
    const tensor = new ort.Tensor("float32", flat, [1, MEL_WINDOW, MEL_BINS, 1]);
    const out = await this.embeddingSession!.run({ input_1: tensor });
    // Output shape is [1, 1, 1, 96] — the embedding is just 96 floats.
    const t = out.conv2d_19 as ort.Tensor;
    return new Float32Array(t.data as Float32Array);
  }

  private appendEmbedding(emb: Float32Array): void {
    this.embeddingBuffer.push(emb);
    while (this.embeddingBuffer.length > EMBEDDING_WINDOW) {
      this.embeddingBuffer.shift();
    }
  }

  private async runClassifier(): Promise<number> {
    const flat = new Float32Array(EMBEDDING_WINDOW * EMBEDDING_DIM);
    for (let i = 0; i < EMBEDDING_WINDOW; i++) {
      flat.set(this.embeddingBuffer[i], i * EMBEDDING_DIM);
    }
    const tensor = new ort.Tensor("float32", flat, [
      1,
      EMBEDDING_WINDOW,
      EMBEDDING_DIM,
    ]);
    const out = await this.classifierSession!.run({ "x.1": tensor });
    // openWakeWord's hey_jarvis classifier outputs a tensor named "53"
    // (PyTorch auto-numbered) shaped [1, 1] containing the wake probability.
    const t = out["53"] as ort.Tensor;
    return (t.data as Float32Array)[0];
  }
}
