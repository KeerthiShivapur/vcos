"use client";

import { useEffect, useState } from "react";
import { Bell, BellRing, Bookmark, BookmarkCheck } from "lucide-react";

import { listPresence, listWatchers, toggleFavorite, toggleWatch } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export function WatchBar({ kind, entityId }: { kind: string; entityId: string }) {
  const [watching, setWatching] = useState(false);
  const [favorited, setFavorited] = useState(false);
  const [watchers, setWatchers] = useState<{ user_name: string | null }[]>([]);
  const [present, setPresent] = useState<{ user_name: string | null; last_active_at: string }[]>([]);

  async function load() {
    try {
      const [watcherList, presenceList] = await Promise.all([
        listWatchers(kind, entityId).catch(() => []),
        listPresence(kind, entityId).catch(() => []),
      ]);
      setWatchers(watcherList);
      setPresent(presenceList);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, entityId]);

  async function watch() {
    const result = await toggleWatch(kind, entityId);
    setWatching(result.watching);
    toastSuccess(result.watching ? "Watching this item" : "No longer watching");
    await load();
  }

  async function favorite() {
    const result = await toggleFavorite(kind, entityId);
    setFavorited(result.favorited);
    toastSuccess(result.favorited ? "Added to favorites" : "Removed from favorites");
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant={watching ? "secondary" : "ghost"} onClick={watch}>
        {watching ? <BellRing className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
        {watching ? "Watching" : "Watch"}
      </Button>
      <Button size="sm" variant={favorited ? "secondary" : "ghost"} onClick={favorite}>
        {favorited ? <BookmarkCheck className="h-4 w-4" /> : <Bookmark className="h-4 w-4" />}
        {favorited ? "Favorited" : "Favorite"}
      </Button>

      {(watchers.length > 0 || present.length > 0) && (
        <div className="ml-2 flex items-center gap-4 text-[12px] text-faint">
          {watchers.length > 0 && (
            <span className="flex items-center -space-x-1.5">
              {watchers.slice(0, 4).map((w) => (
                <Avatar key={w.user_name ?? "w"} name={w.user_name ?? "?"} size="xs" />
              ))}
              <span className="ml-1.5">{watchers.length} watcher{watchers.length === 1 ? "" : "s"}</span>
            </span>
          )}
          {present.length > 0 && (
            <span>
              {present.length} viewing now
              {present[0].last_active_at ? ` · ${timeAgo(present[0].last_active_at)}` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
