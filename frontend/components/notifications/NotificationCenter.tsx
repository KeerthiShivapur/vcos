"use client";

import { useRouter } from "next/navigation";
import { Bell, CheckCheck } from "lucide-react";
import type { Notification } from "@/types";
import { timeAgo } from "@/lib/utils";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Dropdown } from "@/components/ui/Dropdown";
import { EmptyState } from "@/components/ui/EmptyState";
import { useNotifications } from "@/hooks/useNotifications";
import { statusTone } from "@/components/ui/Badge";

export function NotificationBell() {
  const router = useRouter();
  const { unread, recent, markAllRead } = useNotifications();

  return (
    <Dropdown
      width="w-[360px]"
      trigger={(open) => (
        <span
          className={`relative flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${
            open
              ? "bg-canvas text-ink"
              : "text-muted hover:bg-canvas hover:text-ink"
          }`}
        >
          <Bell className="h-4.5 w-4.5 h-[18px] w-[18px]" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </span>
      )}
    >
      {(close) => (
        <>
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <p className="text-sm font-semibold text-ink">Notifications</p>
            {unread > 0 && (
              <button
                onClick={() => void markAllRead()}
                className="flex items-center gap-1 text-xs font-medium text-brand hover:underline"
              >
                <CheckCheck className="h-3.5 w-3.5" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[340px] overflow-y-auto">
            {recent.length === 0 && (
              <EmptyState
                title="No notifications"
                description="You're all caught up."
              />
            )}
            {recent.map((notification: Notification) => (
              <button
                key={notification.id}
                onClick={() => {
                  close();
                  router.push("/notifications");
                }}
                className="flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left transition-colors last:border-0 hover:bg-canvas"
              >
                <span className="mt-0.5">
                  <Badge
                    tone={
                      notification.is_read
                        ? "neutral"
                        : statusTone(notification.type)
                    }
                  >
                    {notification.type}
                  </Badge>
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className={`block truncate text-[13px] font-medium text-ink ${notification.is_read ? "font-normal text-muted" : ""}`}
                  >
                    {notification.title}
                  </span>
                  {notification.body && (
                    <span className="mt-0.5 line-clamp-2 block text-xs text-faint">
                      {notification.body}
                    </span>
                  )}
                  <span className="mt-1 block text-[10px] text-faint">
                    {timeAgo(notification.created_at)}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <div className="border-t border-line p-2">
            <button
              onClick={() => {
                close();
                router.push("/notifications");
              }}
              className="w-full rounded-lg py-2 text-center text-xs font-semibold text-brand hover:bg-brand-soft"
            >
              View all notifications
            </button>
          </div>
        </>
      )}
    </Dropdown>
  );
}
