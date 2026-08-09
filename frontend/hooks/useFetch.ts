"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface FetchState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export type UseFetchOptions = {
  query?: Record<string, string | number | boolean | undefined | null>;
  deps?: unknown[];
};

/**
 * Minimal data-fetching hook around the API client.
 * Query params and refetching supported. Auth/refresh handled by lib/api.
 *
 * Usage:
 *   useFetch<T>("/users")                      — plain GET
 *   useFetch<T>("/users", { query: {...} })    — with query params
 *   useFetch<T>("/users", [deps])              — legacy deps-array form
 *   useFetch<T>(null)                          — disabled
 */
export function useFetch<T>(
  path: string | null,
  options: UseFetchOptions | unknown[] = {}
): FetchState<T> & { refetch: () => void; refresh: () => void } {
  const { query, deps = [] } = Array.isArray(options) ? { deps: options } : options;
  const [state, setState] = useState<FetchState<T>>({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let active = true;
    let attempts = 0;
    // The backend answers in well under a second; a fetch that lingers past
    // this budget is stuck (cancelled by the browser during a navigation burst)
    // and gets retried instead of leaving the page on a permanent spinner.
    const SOFT_TIMEOUT_MS = 5_000;
    const load = async () => {
      setState((prev) => ({ ...prev, loading: true }));
      try {
        const data = await Promise.race([
          api<T>(path, { query }),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error("Request timed out, retrying")), SOFT_TIMEOUT_MS)
          ),
        ]);
        if (active) setState({ data, error: null, loading: false });
      } catch (error) {
        if (!active) return;
        if (attempts < 1) {
          attempts += 1;
          setTimeout(() => {
            if (active) void load();
          }, 400);
        } else {
          setState({
            data: null,
            error: error instanceof Error ? error.message : "Request failed",
            loading: false,
          });
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);

  const refresh = () => setTick((t) => t + 1);
  return { ...state, refetch: refresh, refresh };
}
