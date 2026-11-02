"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CornerDownLeft, Search, Users } from "lucide-react";
import type { SearchResponse } from "@/types";
import { api } from "@/lib/api";
import { Avatar } from "@/components/ui/Avatar";
import { classNames } from "@/lib/utils";

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults(null);
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    let active = true;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const data = await api<SearchResponse>(
          `/search?q=${encodeURIComponent(query)}&limit=8`,
        );
        if (active) setResults(data);
      } catch {
        if (active) setResults({ query, results: [], total: 0, took_ms: 0 });
      } finally {
        if (active) setLoading(false);
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query, open]);

  if (!open) return null;

  const go = (url: string) => {
    onClose();
    router.push(url);
  };

  const typeIcon: Record<string, React.ReactNode> = {
    user: <Users className="h-4 w-4 text-faint" />,
    role: <Users className="h-4 w-4 text-faint" />,
    organization: <Users className="h-4 w-4 text-faint" />,
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-start justify-center p-4 pt-[12vh]">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-xl animate-pop overflow-hidden rounded-xl border border-line bg-elevated shadow-popover">
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search className="h-4 w-4 shrink-0 text-faint" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query.trim())
                go(`/search?q=${encodeURIComponent(query)}`);
            }}
            placeholder="Search employees, roles, anything in the company…"
            className="h-12 w-full bg-transparent text-sm text-ink outline-none placeholder:text-faint"
          />
          <kbd className="hidden items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-[10px] font-medium text-faint sm:flex">
            <CornerDownLeft className="h-3 w-3" />
            enter
          </kbd>
        </div>
        <div className="max-h-80 overflow-y-auto p-2">
          {query.trim().length < 2 && (
            <p className="px-3 py-6 text-center text-xs text-faint">
              Type at least 2 characters to search your company.
            </p>
          )}
          {loading && (
            <p className="px-3 py-6 text-center text-xs text-faint">
              Searching…
            </p>
          )}
          {!loading && results && results.results.length === 0 && (
            <p className="px-3 py-6 text-center text-xs text-faint">
              No results for “{query}”.
            </p>
          )}
          {results?.results.map((result) => (
            <button
              key={`${result.type}-${result.id}`}
              onClick={() => go(result.url)}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-canvas"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-canvas">
                {result.type === "user" ? (
                  <Avatar name={result.title} size="xs" className="h-8 w-8" />
                ) : (
                  (typeIcon[result.type] ?? (
                    <Search className="h-4 w-4 text-faint" />
                  ))
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={classNames(
                    "block truncate text-sm font-medium text-ink",
                  )}
                >
                  {result.title}
                </span>
                <span className="block truncate text-xs text-faint">
                  {result.subtitle}
                </span>
              </span>
              <span className="shrink-0 rounded-full bg-canvas px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-faint">
                {result.type.replace("_", " ")}
              </span>
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 border-t border-line px-4 py-2 text-[10px] text-faint">
          <span>
            <kbd className="font-medium text-muted">Esc</kbd> close
          </span>
          <span>
            <kbd className="font-medium text-muted">Enter</kbd> open results
          </span>
          <span className="ml-auto">VCOS universal search</span>
        </div>
      </div>
    </div>
  );
}
