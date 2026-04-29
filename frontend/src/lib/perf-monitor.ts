"use client";

/**
 * Local-dev FPS + heap-size logger. Logs once every `intervalMs` to the
 * console, plus current FPS sampled over a rolling 1s window.
 *
 * Activate by setting `localStorage.perfMonitor = "1"` in DevTools, then
 * reload. Survives reloads. Off by default — adds zero overhead in production
 * because the module is imported lazily by `enablePerfMonitor()` only.
 */

interface ChromePerformance extends Performance {
  memory?: {
    usedJSHeapSize: number;
    totalJSHeapSize: number;
    jsHeapSizeLimit: number;
  };
}

const FLAG_KEY = "perfMonitor";
const DEFAULT_INTERVAL_MS = 5_000;

let started = false;

export function maybeStartPerfMonitor(): void {
  if (started || typeof window === "undefined") return;
  if (window.localStorage?.getItem(FLAG_KEY) !== "1") return;
  started = true;

  const intervalMs = DEFAULT_INTERVAL_MS;

  // Rolling FPS window — count rAF ticks over the last 1000ms.
  let frameTimestamps: number[] = [];
  const onFrame = (t: number) => {
    frameTimestamps.push(t);
    const cutoff = t - 1000;
    while (frameTimestamps.length && frameTimestamps[0] < cutoff) {
      frameTimestamps.shift();
    }
    requestAnimationFrame(onFrame);
  };
  requestAnimationFrame(onFrame);

  setInterval(() => {
    const fps = frameTimestamps.length;
    const perfWithMemory = performance as ChromePerformance;
    const heapMib = perfWithMemory.memory
      ? (perfWithMemory.memory.usedJSHeapSize / (1024 * 1024)).toFixed(0)
      : "n/a";
    const heapLimitMib = perfWithMemory.memory
      ? (perfWithMemory.memory.jsHeapSizeLimit / (1024 * 1024)).toFixed(0)
      : "n/a";

    console.info(
      `[perf] fps=${fps} heap=${heapMib}MiB / ${heapLimitMib}MiB ` +
        `path=${window.location.pathname}`,
    );
  }, intervalMs);

  console.info(
    "[perf] monitor on — disable with `localStorage.removeItem('perfMonitor')` + reload",
  );
}
