"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "./useAuth";

interface UseFetchOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
  requireAuth?: boolean;
}

export function useFetch<T = any>(url: string, options: UseFetchOptions = {}) {
  const { data, setData } = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { user, accessToken } = useAuth();

  const fetchData = useCallback(
    async (overrideOptions: UseFetchOptions = {}) => {
      const opts = { ...options, ...overrideOptions };
      setLoading(true);
      setError(null);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          ...opts.headers,
        };

        if (opts.requireAuth !== false && accessToken) {
          headers["Authorization"] = `Bearer ${accessToken}`;
        }

        const response = await fetch(url, {
          method: opts.method || "GET",
          headers,
          body: opts.body ? JSON.stringify(opts.body) : undefined,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        setData(data);
        return data;
      } catch (err) {
        const error = err instanceof Error ? err : new Error("Unknown error");
        setError(error.message);
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [url, accessToken, options],
  );

  return { data, loading, error, refetch: fetchData };
}

// Mutation hook
export function useMutation<T = any, TVariables = any>(
  url: string,
  options: {
    method?: string;
    onSuccess?: (data: T) => void;
    onError?: (error: Error) => void;
  } = {},
) {
  const { user, accessToken } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutate = useCallback(async (variables: TVariables) => {
    setLoading(true);
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify(variables),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (err) {
      const error = err instanceof Error ? err : new Error("Unknown error");
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  return { mutate, loading, error };
}
