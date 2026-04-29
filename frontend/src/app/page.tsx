"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { FridgeAppShell } from "@/components/fridge/app-shell";
import { getToken, useAuth } from "@/lib/auth";
import { m } from "@/paraglide/messages.js";

/**
 * Production home — the always-on fridge device shell.
 *
 * Boot sequence (Architect §4.1):
 *   1. If a device JWT exists in localStorage → render the 4-tab kiosk shell.
 *   2. Otherwise → redirect to `/pair` to start the first-time pairing flow.
 *
 * The OAuth callback now redirects directly to `/pair/complete?token=<jwt>`,
 * which is the sole token-handling surface — no token-catching shim lives here.
 */
export default function HomePage() {
  const router = useRouter();
  const { isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (!getToken()) {
      router.replace("/pair");
    }
  }, [isLoading, router]);

  if (isLoading) {
    return <Loading />;
  }

  if (!getToken()) {
    return null;
  }

  return <FridgeAppShell />;
}

function Loading() {
  // Paraglide reads locale from localStorage, which is unavailable during SSR.
  // Server renders the base-locale text; client hydrates with the user's locale
  // → text mismatch. suppressHydrationWarning is the documented fix for the
  // narrow case of a single SSR-only-then-replaced string.
  return (
    <main className="flex flex-1 items-center justify-center">
      <p
        className="text-sm text-muted-foreground"
        suppressHydrationWarning
      >
        {m.common_loading()}
      </p>
    </main>
  );
}
