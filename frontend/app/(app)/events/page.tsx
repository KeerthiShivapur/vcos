"use client";

import { Suspense, useEffect, useState } from "react";
import { CalendarHeart, MapPin, Plus, Ticket, Video } from "lucide-react";

import {
  createCommunityEvent,
  getCommunityEventStats,
  listCommunityEvents,
  listCommunities,
  registerForEvent,
} from "@/lib/api";
import type { Community, CommunityEvent } from "@/types";
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
import { formatDateTime, titleCase } from "@/lib/utils";

const EVENT_TYPES = ["hackathon", "workshop", "town_hall", "social", "training", "conference", "other"];

export default function EventsPage() {
  return (
    <Suspense fallback={null}>
      <EventsContent />
    </Suspense>
  );
}

function EventsContent() {
  const { user } = useAuth();
  const [events, setEvents] = useState<CommunityEvent[]>([]);
  const [stats, setStats] = useState<{ total: number; upcoming: number; registrations: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [list, statsData] = await Promise.all([
        listCommunityEvents({ upcoming: true, limit: 200 }),
        getCommunityEventStats(),
      ]);
      setEvents(list);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load events");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function register(event: CommunityEvent) {
    try {
      await registerForEvent(event.id);
      await load();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Events"
        description="Workshops, hackathons, and get-togethers."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New event
          </Button>
        }
      />

      {stats && (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-line bg-surface p-4">
            <p className="text-[12px] text-faint">Upcoming</p>
            <p className="mt-1 text-2xl font-bold text-ink">{stats.upcoming}</p>
          </div>
          <div className="rounded-lg border border-line bg-surface p-4">
            <p className="text-[12px] text-faint">All time</p>
            <p className="mt-1 text-2xl font-bold text-ink">{stats.total}</p>
          </div>
          <div className="rounded-lg border border-line bg-surface p-4">
            <p className="text-[12px] text-faint">Registrations</p>
            <p className="mt-1 text-2xl font-bold text-brand">{stats.registrations}</p>
          </div>
        </div>
      )}

      {error ? (
        <ErrorState title="Could not load events" message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading events" /></div>
      ) : events.length === 0 ? (
        <EmptyState
          icon={CalendarHeart}
          title="No upcoming events"
          description="Plan a workshop, hackathon, or social gathering."
          action={<Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> New event</Button>}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {events.map((event) => (
            <div key={event.id} className="rounded-lg border border-line bg-surface p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[15px] font-semibold text-ink">{event.title}</h3>
                <Badge tone="brand">{event.type}</Badge>
                <Badge tone={event.status === "open" ? "success" : "neutral"}>{event.status}</Badge>
              </div>
              {event.description && <p className="mt-1 line-clamp-2 text-[13px] text-muted">{event.description}</p>}
              <div className="mt-3 flex flex-wrap items-center gap-3 text-[12px] text-faint">
                <span>{formatDateTime(event.starts_at)}</span>
                {event.location && <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {event.location}</span>}
                {event.virtual_url && <span className="flex items-center gap-1"><Video className="h-3.5 w-3.5" /> Virtual</span>}
                {event.community_name && <Badge tone="neutral">{event.community_name}</Badge>}
                <span className="flex items-center gap-1"><Ticket className="h-3.5 w-3.5" /> {event.registration_count}{event.capacity > 0 ? ` / ${event.capacity}` : ""}</span>
              </div>
              <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
                <span className="flex items-center gap-1.5 text-[12px] text-faint">
                  <Avatar name={event.creator_name} size="xs" /> {event.creator_name}
                </span>
                {event.status === "open" && (
                  event.registered ? (
                    <Badge tone="success">Registered</Badge>
                  ) : (
                    <Button size="sm" variant="secondary" onClick={() => register(event)}>
                      <Ticket className="h-4 w-4" /> Register
                    </Button>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateEventModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={async (payload) => {
          await createCommunityEvent(payload);
          setCreateOpen(false);
          load();
        }}
      />
    </div>
  );
}

function CreateEventModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (payload: {
    title: string;
    description?: string;
    type?: string;
    community_id?: string;
    starts_at: string;
    ends_at?: string;
    location?: string;
    virtual_url?: string;
    capacity?: number;
  }) => Promise<void>;
}) {
  const [communities, setCommunities] = useState<Community[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("workshop");
  const [communityId, setCommunityId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [location, setLocation] = useState("");
  const [virtualUrl, setVirtualUrl] = useState("");
  const [capacity, setCapacity] = useState("0");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    listCommunities({ limit: 500 })
      .then(setCommunities)
      .catch(() => undefined);
  }, [open]);

  async function submit() {
    if (!title.trim()) {
      setError("Title is required");
      return;
    }
    if (!startsAt) {
      setError("Start time is required");
      return;
    }
    setError(null);
    try {
      await onCreated({
        title: title.trim(),
        description: description.trim() || undefined,
        type,
        community_id: communityId || undefined,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: endsAt ? new Date(endsAt).toISOString() : undefined,
        location: location.trim() || undefined,
        virtual_url: virtualUrl.trim() || undefined,
        capacity: capacity ? Number(capacity) : 0,
      });
      setTitle("");
      setDescription("");
      setType("workshop");
      setCommunityId("");
      setStartsAt("");
      setEndsAt("");
      setLocation("");
      setVirtualUrl("");
      setCapacity("0");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create event");
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New event"
      description="Plan an event for your organization."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit}>Create event</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Title" placeholder="e.g. Q3 Hackathon" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea label="Description" placeholder="What should people expect?" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Type"
            value={type}
            onChange={(e) => setType(e.target.value)}
            options={EVENT_TYPES.map((t) => ({ value: t, label: titleCase(t) }))}
          />
          {communities.length > 0 && (
            <Select
              label="Community"
              value={communityId}
              onChange={(e) => setCommunityId(e.target.value)}
              placeholder="Organization-wide"
              options={communities.map((c) => ({ value: c.id, label: c.name }))}
            />
          )}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Starts at" type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          <Input label="Ends at" type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Location" placeholder="e.g. Main hall" value={location} onChange={(e) => setLocation(e.target.value)} />
          <Input label="Capacity" type="number" min={0} value={capacity} onChange={(e) => setCapacity(e.target.value)} />
        </div>
        <Input label="Virtual link (optional)" placeholder="https://meet.example.com/…" value={virtualUrl} onChange={(e) => setVirtualUrl(e.target.value)} />
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
