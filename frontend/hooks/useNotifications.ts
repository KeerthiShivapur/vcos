"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { notificationChannel } from "@/lib/websocket";
import type { Notification, NotificationStats } from "@/types";
import { useAuth } from "@/hooks/useAuth";

export interface NotificationsState {
  unread: number;
  stats: NotificationStats | null;
  recent: Notification[];
  refresh: () => Promise<void>;
  markAllRead: () => Promise<void>;
}

export function useNotifications(): NotificationsState {
  const { ready } = useAuth();
  const [unread, setUnread] = useState(0);
  const [stats, setStats] = useState<NotificationStats | null>(null);
  const [recent, setRecent] = useState<Notification[]>([]);

  const refresh = useCallback(async () => {
    if (!ready) return;
    try {
      const [statsData, listData] = await Promise.all([
        api<NotificationStats>("/notifications/stats"),
        api<{ items: Notification[] }>("/notifications?page_size=8"),
      ]);
      setStats(statsData);
      setUnread(statsData.total_unread);
      setRecent(listData.items);
    } catch {
      /* transient */
    }
  }, [ready]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const unsubscribe = notificationChannel.subscribe(() => void refresh());
    return unsubscribe;
  }, [refresh]);

  const markAllRead = useCallback(async () => {
    await api<{ message: string }>("/notifications/read", { method: "POST", body: { ids: null } });
    await refresh();
  }, [refresh]);

  return { unread, stats, recent, refresh, markAllRead };
}
