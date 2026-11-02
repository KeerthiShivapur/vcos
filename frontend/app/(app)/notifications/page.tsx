"use client";

import { Bell, CheckCheck } from "lucide-react";

import { useFetch } from "@/hooks/useFetch";
import { Notification, Paginated } from "@/types";
import { useNotifications } from "@/hooks/useNotifications";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { toastSuccess } from "@/components/ui/Toaster";

export default function NotificationsPage() {
  const { data, loading, error, refetch } =
    useFetch<Paginated<Notification>>("/notifications");
  const { unreadCount, refresh: refreshCount, markAllAsRead } = useNotifications();

  async function markAll() {
    try {
      await markAllAsRead();
      toastSuccess("All notifications marked as read");
      refetch();
    } catch {
      /* toast handled by interceptor */
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notifications"
        description={
          unreadCount > 0
            ? `You have ${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}.`
            : "You are all caught up."
        }
        actions={
          (data?.items.length ?? 0) > 0 ? (
            <Button variant="ghost" size="sm" onClick={markAll}>
              <CheckCheck className="h-4 w-4" /> Mark all read
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState title="Could not load notifications" message={error} />
      ) : loading || !data ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading notifications" />
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No notifications yet"
          description="Invitations, mentions, approvals, and system messages will appear here."
        />
      ) : (
        <div className="space-y-3">
          {data.items.map((n: Notification) => (
            <Card
              key={n.id}
              className={`flex items-start gap-3 p-4 ${n.is_read ? "opacity-70" : "border-brand/30 bg-brand/[0.03]"}`}
            >
              <div
                className={`mt-0.5 rounded-lg p-2 text-white ${n.is_read ? "bg-muted/60" : "bg-brand"}`}
              >
                <Bell className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{n.type}</Badge>
                  {n.priority === "high" && (
                    <Badge tone="warning">High priority</Badge>
                  )}
                  {!n.is_read && <Badge tone="brand">New</Badge>}
                  <span className="ml-auto text-[12px] text-faint">
                    {formatDate(n.created_at)}
                  </span>
                </div>
                <p className="mt-1.5 text-[13px] font-medium text-ink">
                  {n.title}
                </p>
                {n.body ? (
                  <p className="mt-0.5 text-[13px] leading-relaxed text-muted">
                    {n.body}
                  </p>
                ) : null}
                {n.link ? (
                  <a
                    href={n.link}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-[13px] font-medium text-brand hover:underline"
                  >
                    Open related item
                  </a>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
