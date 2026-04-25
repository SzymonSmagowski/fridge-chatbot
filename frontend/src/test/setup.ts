/**
 * Vitest setup — wires up jest-dom matchers and the MSW server.
 *
 * MSW intercepts fetch calls in the jsdom environment so component tests can
 * exercise the real api/* clients against deterministic Architect §5 shapes
 * without a backend.
 */
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { setLocale } from "@/paraglide/runtime.js";
import { server } from "./msw-server";

// Stable backend URL for tests — handlers register against this base.
process.env.NEXT_PUBLIC_BACKEND_URL = "http://localhost:8001";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  // localStorage carries the JWT used by api/http.ts — wipe between tests.
  if (typeof window !== "undefined") {
    window.localStorage.clear();
  }
  vi.useRealTimers();
});
afterAll(() => server.close());

// Some components touch matchMedia / IntersectionObserver — stub to avoid
// jsdom blowups on unrelated rendering paths.
beforeEach(() => {
  if (typeof window !== "undefined" && !window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  }

  // Pin Paraglide to English for every test. Component assertions check exact
  // English strings; without this, a test that flips the locale could leak the
  // setting into the next test via Paraglide's cached `_locale` global.
  if (typeof window !== "undefined") {
    window.localStorage.setItem("PARAGLIDE_LOCALE", "en");
  }
  setLocale("en", { reload: false });
});
