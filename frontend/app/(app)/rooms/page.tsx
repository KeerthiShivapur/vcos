"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { Building2, DoorOpen, Plus, Radio, Users } from "lucide-react";

import {
  createMeetingRoom,
  deleteMeetingRoom,
  listMeetingRooms,
  roomAvailability,
  updateMeetingRoom,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { MeetingRoom } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { toastSuccess, toastError } from "@/components/ui/Toaster";

export default function RoomsPage() {
  return (
    <Suspense fallback={null}>
      <RoomsContent />
    </Suspense>
  );
}

const ROOM_TYPES = ["meeting", "virtual_office", "project", "department", "team", "event", "standup"];

const ROOM_TYPE_META: Record<string, { label: string; hint: string }> = {
  meeting: { label: "Meeting", hint: "Ad-hoc meetings and calls" },
  virtual_office: { label: "Virtual office", hint: "Drop-in hangout space" },
  project: { label: "Project", hint: "Project war room" },
  department: { label: "Department", hint: "Department floor" },
  team: { label: "Team", hint: "Team room" },
  event: { label: "Event", hint: "Town halls and events" },
  standup: { label: "Standup", hint: "Daily standups" },
};

function RoomsContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.MEETINGS_MANAGE);

  const [rooms, setRooms] = useState<MeetingRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [availabilityByRoom, setAvailabilityByRoom] = useState<Record<string, unknown[]>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const roomList = await listMeetingRooms({ room_type: typeFilter || undefined });
      setRooms(roomList);
      const avail: Record<string, unknown[]> = {};
      for (const room of roomList.slice(0, 12)) {
        try {
          avail[room.id] = await roomAvailability(room.id);
        } catch {
          avail[room.id] = [];
        }
      }
      setAvailabilityByRoom(avail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load rooms");
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFormError(null);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      setFormError("Room name is required.");
      return;
    }
    setSaving(true);
    try {
      await createMeetingRoom({
        name,
        room_type: String(form.get("room_type") ?? "meeting"),
        description: String(form.get("description") ?? "").trim() || undefined,
        capacity: form.get("capacity") ? Number(form.get("capacity")) : 8,
        location: String(form.get("location") ?? "").trim() || undefined,
        allow_recording: String(form.get("allow_recording") ?? "true") !== "false",
      });
      toastSuccess("Room created");
      setShowCreate(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create room");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleStatus(room: MeetingRoom) {
    const next = room.status === "available" ? "occupied" : "available";
    try {
      await updateMeetingRoom(room.id, { status: next });
      toastSuccess(`${room.name} marked ${next}`);
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to update room");
    }
  }

  async function handleDelete(room: MeetingRoom) {
    if (!window.confirm(`Delete room "${room.name}"?`)) return;
    try {
      await deleteMeetingRoom(room.id);
      toastSuccess("Room deleted");
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete room");
    }
  }

  const occupied = rooms.filter((r) => r.status === "occupied" || r.status === "scheduled");
  const available = rooms.filter((r) => r.status === "available");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Virtual Office"
        description="Rooms your organization can meet in — drop in when they're open."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> Create room
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Select
          className="h-9 w-44"
          aria-label="Room type"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          options={ROOM_TYPES.map((t) => ({ value: t, label: ROOM_TYPE_META[t].label }))}
          placeholder="All room types"
        />
        <div className="ml-auto flex items-center gap-3 text-[12px] font-medium">
          <span className="flex items-center gap-1.5 text-muted"><span className="h-2 w-2 rounded-full bg-success" /> {available.length} available</span>
          <span className="flex items-center gap-1.5 text-muted"><span className="h-2 w-2 rounded-full bg-danger" /> {occupied.length} in use</span>
        </div>
      </div>

      {error ? (
        <ErrorState title="Could not load rooms" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading rooms" /></div>
      ) : rooms.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No rooms"
          description="Create rooms where people can meet, hang out and collaborate."
          action={canManage ? <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" /> Create room</Button> : undefined}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {rooms.map((room) => {
            const meta = ROOM_TYPE_META[room.room_type] ?? ROOM_TYPE_META.meeting;
            const busy = room.status === "occupied" || room.status === "scheduled";
            const upcoming = (availabilityByRoom[room.id] ?? [])
              .filter((item: unknown) => {
                const it = item as { status?: string; start_at?: string | null };
                return it.status !== "cancelled" && it.status !== "completed";
              })
              .slice(0, 2);
            return (
              <div key={room.id} className="card p-5">
                <div className="flex items-start justify-between gap-2">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${busy ? "bg-danger/10 text-danger" : "bg-brand-soft text-brand"}`}>
                    {busy ? <Radio className="h-5 w-5" /> : <DoorOpen className="h-5 w-5" />}
                  </div>
                  <Badge tone={busy ? "danger" : room.status === "maintenance" ? "warning" : "success"}>{room.status}</Badge>
                </div>
                <h3 className="mt-3 truncate font-semibold text-ink">{room.name}</h3>
                <p className="text-[12px] text-faint">{meta.label} · {meta.hint}</p>
                <p className="mt-2 flex items-center gap-1.5 text-[12px] text-muted">
                  <Users className="h-3.5 w-3.5" /> {room.capacity} capacity
                  {room.location ? ` · ${room.location}` : ""}
                </p>
                {room.description && <p className="mt-1 line-clamp-2 text-[12px] text-faint">{room.description}</p>}
                {upcoming.length > 0 && (
                  <div className="mt-3 rounded-lg border border-line bg-canvas p-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Next in this room</p>
                    {upcoming.map((item, index) => {
                      const it = item as { title: string; start_at: string | null };
                      return (
                        <p key={index} className="mt-1 truncate text-[12px] text-muted">
                          {it.title}
                          {it.start_at ? ` · ${new Date(it.start_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : ""}
                        </p>
                      );
                    })}
                  </div>
                )}
                {canManage && (
                  <div className="mt-4 flex items-center gap-2">
                    <Button size="sm" variant="secondary" onClick={() => handleToggleStatus(room)}>
                      {busy ? "Mark available" : "Mark in use"}
                    </Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => handleDelete(room)}>
                      Delete
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create room" description="Add a place where people can meet and collaborate.">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Name" name="name" required placeholder="Design Studio" />
          <Select
            label="Type"
            name="room_type"
            defaultValue="meeting"
            options={ROOM_TYPES.map((t) => ({ value: t, label: ROOM_TYPE_META[t].label }))}
          />
          <Textarea label="Description" name="description" rows={2} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Capacity" name="capacity" type="number" min={1} defaultValue={8} />
            <Input label="Location" name="location" placeholder="Virtual / Room 1" />
          </div>
          <Select
            label="Recording allowed"
            name="allow_recording"
            defaultValue="true"
            options={[{ value: "true", label: "Yes" }, { value: "false", label: "No" }]}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create room</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
