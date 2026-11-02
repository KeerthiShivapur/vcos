"use client";

import { Suspense, useEffect, useState } from "react";
import { CheckCheck, Eye, Megaphone, Pin, Plus } from "lucide-react";

import {
  acknowledgeAnnouncement,
  createAnnouncement,
  getMyEmployee,
  listAnnouncementReceipts,
  listAnnouncements,
  markAnnouncementRead,
  publishAnnouncement,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Announcement, AnnouncementReceipt } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { timeAgo } from "@/lib/utils";

const TYPES = ["general", "company", "policy", "system", "urgent"];
const PRIORITIES = ["low", "normal", "high", "urgent"];

export default function AnnouncementsPage() {
  return (
    <Suspense fallback={null}>
      <AnnouncementsContent />
    </Suspense>
  );
}

function AnnouncementsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.COMMUNICATION_MANAGE);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("published");
  const [createOpen, setCreateOpen] = useState(false);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, me] = await Promise.all([
        listAnnouncements({ status: filter || undefined, limit: 200 }),
        getMyEmployee().catch(() => null),
      ]);
      setAnnouncements(list);
      setMyEmployeeId(me?.id ?? null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load announcements",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function markRead(announcement: Announcement) {
    if (!announcement.read_by_me) {
      try {
        await markAnnouncementRead(announcement.id);
        setAnnouncements((prev) =>
          prev.map((a) =>
            a.id === announcement.id
              ? { ...a, read_by_me: true, read_count: a.read_count + 1 }
              : a,
          ),
        );
      } catch {
        /* ignore */
      }
    }
  }

  async function acknowledge(announcement: Announcement) {
    try {
      await acknowledgeAnnouncement(announcement.id);
      setAnnouncements((prev) =>
        prev.map((a) =>
          a.id === announcement.id
            ? {
                ...a,
                acknowledged_by_me: true,
                acknowledged_count: a.acknowledged_count + 1,
              }
            : a,
        ),
      );
    } catch {
      /* ignore */
    }
  }

  async function publish(announcement: Announcement) {
    try {
      await publishAnnouncement(announcement.id);
      load();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Announcements"
        description="Company-wide news, policies, and important updates."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> New announcement
            </Button>
          ) : undefined
        }
      />

      <div className="w-44">
        <Select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="All statuses"
          options={[
            { value: "", label: "All statuses" },
            { value: "published", label: "Published" },
            { value: "draft", label: "Drafts" },
            { value: "scheduled", label: "Scheduled" },
          ]}
        />
      </div>

      {error ? (
        <ErrorState
          title="Could not load announcements"
          message={error}
          onRetry={load}
        />
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading announcements" />
        </div>
      ) : announcements.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="No announcements"
          description="Important updates will appear here."
          action={
            canManage ? (
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4" /> New announcement
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="space-y-4">
          {announcements.map((announcement) => (
            <AnnouncementCard
              key={announcement.id}
              announcement={announcement}
              isMine={announcement.author_id === myEmployeeId}
              canManage={canManage}
              onRead={() => markRead(announcement)}
              onAcknowledge={() => acknowledge(announcement)}
              onPublish={() => publish(announcement)}
            />
          ))}
        </div>
      )}

      <CreateAnnouncementModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={async (payload) => {
          await createAnnouncement(payload);
          setCreateOpen(false);
          load();
        }}
      />
    </div>
  );
}

function AnnouncementCard({
  announcement,
  isMine,
  canManage,
  onRead,
  onAcknowledge,
  onPublish,
}: {
  announcement: Announcement;
  isMine: boolean;
  canManage: boolean;
  onRead: () => void;
  onAcknowledge: () => void;
  onPublish: () => void;
}) {
  const [receiptsOpen, setReceiptsOpen] = useState(false);
  const [receipts, setReceipts] = useState<AnnouncementReceipt[]>([]);

  async function showReceipts() {
    setReceiptsOpen(true);
    try {
      setReceipts(await listAnnouncementReceipts(announcement.id));
    } catch {
      setReceipts([]);
    }
  }

  const priorityTone =
    announcement.priority === "urgent"
      ? "danger"
      : announcement.priority === "high"
        ? "warning"
        : announcement.priority === "low"
          ? "neutral"
          : "brand";

  return (
    <article
      className={`rounded-lg border bg-surface p-5 ${announcement.pinned ? "border-brand/40" : "border-line"}`}
      onClick={onRead}
    >
      <div className="flex items-start gap-3">
        <Avatar name={announcement.author_name} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold text-ink">
              {announcement.title}
            </h3>
            <Badge tone={priorityTone}>{announcement.priority}</Badge>
            <Badge tone="neutral">{announcement.type}</Badge>
            {announcement.pinned && (
              <Badge tone="brand">
                <Pin className="h-3 w-3" /> Pinned
              </Badge>
            )}
            {announcement.status === "draft" && (
              <Badge tone="warning">Draft</Badge>
            )}
          </div>
          <p className="mt-0.5 text-[12px] text-faint">
            {announcement.author_name} · {timeAgo(announcement.created_at)}
            {announcement.department_name &&
              ` · ${announcement.department_name}`}
            {announcement.team_id && " · Team"}
          </p>
          {announcement.body && (
            <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">
              {announcement.body}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3 text-[12px] text-faint">
            <span className="flex items-center gap-1">
              <Eye className="h-3.5 w-3.5" /> {announcement.read_count}
            </span>
            {announcement.acknowledge_required && (
              <span className="flex items-center gap-1">
                <CheckCheck className="h-3.5 w-3.5" />{" "}
                {announcement.acknowledged_count}
              </span>
            )}
            {announcement.status === "published" &&
              !announcement.read_by_me &&
              !isMine && <span className="text-brand">New</span>}
            {announcement.acknowledge_required &&
              !announcement.acknowledged_by_me &&
              !isMine && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAcknowledge();
                  }}
                >
                  Acknowledge
                </Button>
              )}
            {isMine && announcement.status === "draft" && (
              <Button
                size="sm"
                variant="secondary"
                onClick={(e) => {
                  e.stopPropagation();
                  onPublish();
                }}
              >
                Publish
              </Button>
            )}
            {canManage && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  showReceipts();
                }}
              >
                Receipts
              </Button>
            )}
          </div>
        </div>
      </div>

      <Modal
        open={receiptsOpen}
        onClose={() => setReceiptsOpen(false)}
        title={`Receipts · ${announcement.title}`}
        size="lg"
      >
        <div className="space-y-2">
          {receipts.length === 0 ? (
            <p className="text-[13px] text-muted">No reads recorded yet.</p>
          ) : (
            receipts.map((receipt) => (
              <div
                key={receipt.id}
                className="flex items-center justify-between rounded-md bg-surface-muted px-3 py-2"
              >
                <span className="text-[13px] font-medium text-ink">
                  {receipt.employee_name ?? "Unknown"}
                </span>
                <div className="flex gap-3 text-[12px] text-faint">
                  <span className="flex items-center gap-1">
                    <Eye className="h-3.5 w-3.5" />
                    {receipt.read_at
                      ? new Date(receipt.read_at).toLocaleString()
                      : "not read"}
                  </span>
                  {announcement.acknowledge_required && (
                    <span className="flex items-center gap-1">
                      <CheckCheck className="h-3.5 w-3.5" />
                      {receipt.acknowledged_at
                        ? new Date(receipt.acknowledged_at).toLocaleString()
                        : "not acknowledged"}
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </Modal>
    </article>
  );
}

function CreateAnnouncementModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (payload: {
    title: string;
    body?: string;
    type?: string;
    priority?: string;
    status?: string;
    pinned?: boolean;
    acknowledge_required?: boolean;
  }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [type, setType] = useState("general");
  const [priority, setPriority] = useState("normal");
  const [status, setStatus] = useState("published");
  const [pinned, setPinned] = useState(false);
  const [acknowledge, setAcknowledge] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    setError(null);
    try {
      await onCreated({
        title: title.trim(),
        body: body.trim() || undefined,
        type,
        priority,
        status,
        pinned,
        acknowledge_required: acknowledge,
      });
      setTitle("");
      setBody("");
      setType("general");
      setPriority("normal");
      setStatus("published");
      setPinned(false);
      setAcknowledge(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to create announcement",
      );
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New announcement"
      description="Publish an update to your organization."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit}>Create</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input
          label="Title"
          placeholder="e.g. New office hours"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Textarea
          label="Body"
          placeholder="Details of the announcement…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={5}
        />
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Type"
            value={type}
            onChange={(e) => setType(e.target.value)}
            options={TYPES.map((t) => ({ value: t, label: t }))}
          />
          <Select
            label="Priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            options={PRIORITIES.map((p) => ({ value: p, label: p }))}
          />
          <Select
            label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={[
              { value: "published", label: "Published" },
              { value: "draft", label: "Draft" },
              { value: "scheduled", label: "Scheduled" },
            ]}
          />
        </div>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <input
            type="checkbox"
            checked={pinned}
            onChange={(e) => setPinned(e.target.checked)}
          />
          Pin this announcement
        </label>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <input
            type="checkbox"
            checked={acknowledge}
            onChange={(e) => setAcknowledge(e.target.checked)}
          />
          Require acknowledgement
        </label>
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
