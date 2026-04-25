"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FridgeAppShell } from "@/components/fridge/app-shell";
import { getToken, setDeviceToken, useAuth } from "@/lib/auth";
import { m } from "@/paraglide/messages.js";

/**
 * Production home — the always-on fridge device shell.
 *
 * Boot sequence:
 *   1. If the URL carries `?token=` (the OAuth callback redirect lands here
 *      via Architect §4.1's `/settings?paired=1&token=…` shape), consume it
 *      into localStorage and strip it from the URL before rendering.
 *   2. If a device JWT exists in localStorage → render the 4-tab kiosk shell.
 *   3. Otherwise → redirect to `/pair` to start the first-time pairing flow.
 *
 * Legacy `/login` is still available as a developer escape hatch but is no
 * longer the default entry point.
 */
export default function HomePage() {
  return (
    <Suspense fallback={<Loading />}>
      <HomePageInner />
    </Suspense>
  );
}

function HomePageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { isLoading } = useAuth();
  const [tokenAccepted, setTokenAccepted] = useState(false);

  // Step 1: catch the OAuth callback's `?token=` and persist it before the
  // useAuth hook decides to redirect us to /pair. The setState lives behind
  // a guard branch and feeds a one-shot "accepted" flag so the second effect
  // doesn't bounce us to /pair while the first is settling — known false
  // positive of React 19's `react-hooks/set-state-in-effect` rule.
  useEffect(() => {
    const callbackToken = params.get("token");
    if (callbackToken && !getToken()) {
      setDeviceToken(callbackToken);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTokenAccepted(true);
      router.replace("/");
    }
  }, [params, router]);

  // Step 2 / 3: once the auth state has settled, send unpaired devices to /pair.
  useEffect(() => {
    if (isLoading) return;
    if (tokenAccepted) return;
    if (!getToken()) {
      router.replace("/pair");
    }
  }, [isLoading, router, tokenAccepted]);

  if (isLoading) {
    return <Loading />;
  }

  if (!getToken()) {
    return null;
  }

  return <FridgeAppShell />;
}

function Loading() {
  return (
    <main className="flex flex-1 items-center justify-center">
      <p className="text-sm text-muted-foreground">{m.common_loading()}</p>
    </main>
  );
}
