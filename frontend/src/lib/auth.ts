"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiError, type UserPublic } from "@/lib/api";
import { m } from "@/paraglide/messages.js";

const TOKEN_KEY = "fridge-chatbot-token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function saveToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

/**
 * Stores the device JWT issued by the pairing OAuth callback (Architect §4.2).
 * Clears any stale legacy user-JWT first so the next request reads the
 * fresh device token. Same storage slot as `saveToken()` — there is one
 * Authorization header, one localStorage key.
 */
export function setDeviceToken(token: string): void {
  clearToken();
  saveToken(token);
}

type AuthState = {
  user: UserPublic | null;
  isLoading: boolean;
  error: string | null;
};

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    error: null,
  });

  const reload = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setState({ user: null, isLoading: false, error: null });
      return;
    }
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const user = await apiClient.me();
      setState({ user, isLoading: false, error: null });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
      }
      setState({
        user: null,
        isLoading: false,
        error: err instanceof Error ? err.message : m.errors_load_user_failed(),
      });
    }
  }, []);

  useEffect(() => {
    // setState happens inside the awaited callback, not in the effect body —
    // known false positive of the React 19 `react-hooks/set-state-in-effect` rule.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  const logout = useCallback(() => {
    clearToken();
    setState({ user: null, isLoading: false, error: null });
  }, []);

  return { ...state, reload, logout };
}
