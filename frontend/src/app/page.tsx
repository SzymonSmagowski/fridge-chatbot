"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { FridgeAppShell } from "@/components/fridge/app-shell";
import { getToken, useAuth } from "@/lib/auth";
import { m } from "@/paraglide/messages.js";

/**
 * Production home — the always-on fridge device shell.
 * Single-route SPA with state-driven tabs (Chat / Notes / Calendar / Settings)
 * matching the design preview shape; no per-tab file route needed.
 *
 * Auth note: Architect §4 ships a device JWT via the pairing OAuth flow.
 * Until that lands, we accept the existing user JWT (issued by /auth/login)
 * which the backend will treat as the device token (§4.2 shadow user).
 */
export default function HomePage() {
  const router = useRouter();
  const { isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !getToken()) {
      router.replace("/login");
    }
  }, [isLoading, router]);

  if (isLoading) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-sm text-muted-foreground">{m.common_loading()}</p>
      </main>
    );
  }

  if (!getToken()) {
    return null;
  }

  return <FridgeAppShell />;
}
