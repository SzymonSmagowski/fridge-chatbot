"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { PairingScreen } from "@/components/fridge/pairing-screen";
import { getToken } from "@/lib/auth";

/**
 * First-boot pairing route. If a device JWT already exists in localStorage
 * (the user is already paired), bounce straight to the home shell — there's
 * nothing to pair from this device.
 */
export default function PairPage() {
  const router = useRouter();

  useEffect(() => {
    if (getToken()) {
      router.replace("/");
    }
  }, [router]);

  return <PairingScreen />;
}
