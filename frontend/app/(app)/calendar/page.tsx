"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, ListOrdered, Plus } from "lucide-react";

import { createCalendarEvent, deleteCalendarEvent, getCalendarFeed } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { CalendarFeedItem } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { classNames, formatDate, formatDateTime } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function CalendarPage() {
  return (
    <Suspense fallback={null}>
      <CalendarContent />
    </Suspense>
  );
}

const SCOPE_OPTIONS = ["personal", "team", "department", "project", "company"];
const EVENT_TYPES = ["event", "meeting", "deadline", "reminder", "holiday", "milestone"];

type Tone = "neutral" | "brand" | "success" | "warning" | "danger";

const SOURCE_META: Record<string, { label: string; tone: Tone }> = {
  event: { label: "Event", tone: "brand" },
  meeting: { label: "Meeting", tone: "warning" },
  task: { label: "Task deadline", tone: "danger" },
  leave: { label: "Leave", tone: "success" },
  holiday: { label: "Holiday", tone: "neutral" },
};

type CalendarView = "week" | "month" | "agenda";

function startOfWeek(date: Date): Date {
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const result = new Date(date);
  result.setDate(date.getDate() + diff);
  result.setHours(0, 0, 0, 0);
  return result;
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function itemStart(item: CalendarFeedItem): Date | null {
  if (item.start_at) return new Date(item.start_at);
  if (item.due_date) return new Date(`${item.due_date}T00:00:00`);
  return null;
}

function itemDayKey(item: CalendarFeedItem): string | null {
  const start = itemStart(item);
  return start ? start.toDateString() : null;
}

function CalendarContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.CALENDAR_MANAGE);

  const [items, setItems] = useState<CalendarFeedItem[]>([]);
  const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(new Date()));
  const [monthStart, setMonthStart] = useState<Date>(() => startOfMonth(new Date()));
  const [view, setView] = useState<CalendarView>("week");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const range = useMemo<{ start: Date; end: Date }>(() => {
    if (view === "week") {
      const end = new Date(weekStart);
      end.setDate(weekStart.getDate() + 7);
      return { start: weekStart, end };
    }
    if (view === "month") {
      const end = new Date(monthStart);
      end.setMonth(monthStart.getMonth() + 1);
      return { start: monthStart, end };
    }
    const start = startOfWeek(new Date());
    const end = new Date(start);
    end.setDate(start.getDate() + 30);
    return { start, end };
  }, [view, weekStart, monthStart]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const feed = await getCalendarFeed({
        start: range.start.toISOString(),
        end: range.end.toISOString(),
      });
      setItems(feed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load calendar");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range]);

  function navigate(direction: -1 | 1) {
    if (view === "week") {
      setWeekStart((d) => {
        const n = new Date(d);
        n.setDate(d.getDate() + direction * 7);
        return n;
      });
    } else if (view === "month") {
      setMonthStart((d) => new Date(d.getFullYear(), d.getMonth() + direction, 1));
    } else {
      setWeekStart((d) => {
        const n = new Date(d);
        n.setDate(d.getDate() + direction * 7);
        return n;
      });
    }
  }

  function goToday() {
    setWeekStart(startOfWeek(new Date()));
    setMonthStart(startOfMonth(new Date()));
  }

  const visibleItems = useMemo(() => {
    return items.filter((item) => {
      if (sourceFilter && item.source !== sourceFilter) return false;
      if (scopeFilter && item.scope && item.scope !== scopeFilter) return false;
      return true;
    });
  }, [items, sourceFilter, scopeFilter]);

  const weekDays = useMemo(() => {
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(weekStart);
      date.setDate(weekStart.getDate() + index);
      return date;
    });
  }, [weekStart]);

  const monthDays = useMemo(() => {
    const first = startOfMonth(monthStart);
    const leading = first.getDay() === 0 ? 6 : first.getDay() - 1;
    const gridStart = new Date(first);
    gridStart.setDate(first.getDate() - leading);
    return Array.from({ length: 42 }, (_, index) => {
      const date = new Date(gridStart);
      date.setDate(gridStart.getDate() + index);
      return date;
    });
  }, [monthStart]);

  const itemsByDay = useMemo(() => {
    const map = new Map<string, CalendarFeedItem[]>();
    for (const item of visibleItems) {
      const key = itemDayKey(item);
      if (!key) continue;
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    }
    return map;
  }, [visibleItems]);

  const sortedItems = useMemo(
    () => [...visibleItems].sort((a, b) => (itemStart(a)?.getTime() ?? 0) - (itemStart(b)?.getTime() ?? 0)),
    [visibleItems]
  );

  const label =
    view === "week"
      ? `${weekDays[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${weekDays[6].toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`
      : view === "month"
        ? monthStart.toLocaleDateString(undefined, { month: "long", year: "numeric" })
        : `Next 30 days from ${startOfWeek(new Date()).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) return;
    setSaving(true);
    setFormError(null);
    try {
      const startAt = String(form.get("start_at") ?? "");
      await createCalendarEvent({
        title,
        description: String(form.get("description") ?? "").trim() || undefined,
        event_type: String(form.get("event_type") ?? "event"),
        calendar_scope: String(form.get("calendar_scope") ?? "personal"),
        location: String(form.get("location") ?? "").trim() || undefined,
        start_at: startAt ? new Date(startAt).toISOString() : undefined,
        end_at: startAt ? new Date(new Date(startAt).getTime() + 60 * 60 * 1000).toISOString() : undefined,
        all_day: form.get("all_day") === "on",
        status: "confirmed",
      });
      toastSuccess("Event created");
      setShowCreate(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create event");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(eventId: string) {
    try {
      await deleteCalendarEvent(eventId);
      toastSuccess("Event deleted");
      await load();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete event");
    }
  }

  const renderItem = (item: CalendarFeedItem) => {
    const meta = SOURCE_META[item.source] ?? SOURCE_META.event;
    const start = itemStart(item);
    return (
      <div key={`${item.source}-${item.id}`} className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-ink">{item.title}</p>
        <p className="text-[12px] text-faint">
          {item.all_day || !start ? "All day" : formatDateTime(start.toISOString())}
          {item.source === "event" && item.scope ? ` · ${item.scope}` : ""}
        </p>
        <div className="mt-1.5 flex gap-1.5">
          <Badge tone={meta.tone}>{meta.label}</Badge>
          {item.source === "event" && item.event_type ? <Badge tone="brand">{item.event_type}</Badge> : null}
          {item.source !== "event" && item.status ? <Badge tone="neutral">{item.status}</Badge> : null}
        </div>
      </div>
    );
  };

  const renderView = () => {
    if (error) return <ErrorState title="Could not load calendar" message={error} />;
    if (loading) return <div className="flex justify-center py-24"><Spinner label="Loading calendar" /></div>;
    if (view === "week") {
      return (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card bodyClassName="p-3">
              <div className="grid grid-cols-7 gap-1">
                {weekDays.map((day) => {
                  const key = day.toDateString();
                  const dayItems = itemsByDay.get(key) ?? [];
                  const isToday = day.toDateString() === new Date().toDateString();
                  return (
                    <div key={key} className={classNames("flex min-h-32 flex-col rounded-lg border p-1.5", isToday ? "border-brand bg-brand-soft/40" : "border-line")}>
                      <p className="text-center text-[11px] font-semibold text-faint">
                        {day.toLocaleDateString(undefined, { weekday: "short" })}
                        <span className={classNames("ml-1", isToday ? "text-brand" : "")}>{day.getDate()}</span>
                      </p>
                      <div className="mt-1 space-y-0.5">
                        {dayItems.slice(0, 4).map((item) => {
                          const meta = SOURCE_META[item.source] ?? SOURCE_META.event;
                          return (
                            <div
                              key={`${item.source}-${item.id}`}
                              className={classNames(
                                "truncate rounded px-1.5 py-0.5 text-[10px] font-medium",
                                item.source === "event" ? "bg-brand-soft text-brand" : "bg-surface-strong text-ink"
                              )}
                              title={`${item.title}${item.start_at ? ` · ${formatDateTime(item.start_at)}` : ""}`}
                            >
                              <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-current opacity-60" />
                              {item.title}
                            </div>
                          );
                        })}
                        {dayItems.length > 4 && <p className="px-1 text-[10px] text-faint">+{dayItems.length - 4} more</p>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
          <Card title="This week" subtitle={`${sortedItems.length} items`}>
            {sortedItems.length === 0 ? (
              <EmptyState icon={CalendarDays} title="Nothing scheduled" description="Create an event to get started." />
            ) : (
              <ul className="space-y-3">
                {sortedItems.map((item) => (
                  <li key={`${item.source}-${item.id}`} className="group flex items-start gap-3 rounded-lg border border-line p-3">
                    {renderItem(item)}
                    {canManage && item.source === "event" && (
                      <button onClick={() => handleDelete(item.id)} className="hidden rounded-lg p-1 text-faint hover:bg-danger/10 hover:text-danger group-hover:block" title="Delete event">
                        <Plus className="h-3.5 w-3.5 rotate-45" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      );
    }
    if (view === "month") {
      return (
        <Card bodyClassName="p-3">
          <div className="grid grid-cols-7 gap-1">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((weekday) => (
              <p key={weekday} className="py-1 text-center text-[11px] font-semibold uppercase tracking-wide text-faint">
                {weekday}
              </p>
            ))}
            {monthDays.map((day) => {
              const inMonth = day.getMonth() === monthStart.getMonth();
              const key = day.toDateString();
              const dayItems = itemsByDay.get(key) ?? [];
              return (
                <div
                  key={key}
                  className={classNames(
                    "flex min-h-24 flex-col rounded-lg border p-1.5",
                    inMonth ? "border-line" : "border-line/40 opacity-40",
                    day.toDateString() === new Date().toDateString() ? "border-brand bg-brand-soft/40 opacity-100" : ""
                  )}
                >
                  <p className={classNames("text-[11px] font-semibold", day.toDateString() === new Date().toDateString() ? "text-brand" : "text-faint")}>
                    {day.getDate()}
                  </p>
                  <div className="mt-1 space-y-0.5">
                    {dayItems.slice(0, 3).map((item) => (
                      <div
                        key={`${item.source}-${item.id}`}
                        className={classNames(
                          "truncate rounded px-1.5 py-0.5 text-[10px] font-medium",
                          item.source === "event" ? "bg-brand-soft text-brand" : "bg-surface-strong text-ink"
                        )}
                        title={`${item.title}${item.start_at ? ` · ${formatDateTime(item.start_at)}` : ""}`}
                      >
                        {item.title}
                      </div>
                    ))}
                    {dayItems.length > 3 && <p className="px-1 text-[10px] text-faint">+{dayItems.length - 3} more</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      );
    }
    return (
      <Card title="Agenda" subtitle={`${sortedItems.length} items in the next 30 days`}>
        {sortedItems.length === 0 ? (
          <EmptyState icon={CalendarDays} title="Nothing scheduled" description="Create an event to get started." />
        ) : (
          <div className="space-y-6">
            {Array.from(itemsByDay.entries())
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([dayKey, dayItems]) => (
                <div key={dayKey}>
                  <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-faint">
                    {formatDate(dayKey)} · {dayItems.length} item(s)
                  </p>
                  <ul className="space-y-2">
                    {dayItems.map((item) => (
                      <li key={`${item.source}-${item.id}`} className="group flex items-center gap-3 rounded-lg border border-line px-3 py-2.5">
                        <span className="w-24 shrink-0 text-[12px] font-medium text-muted">
                          {item.all_day || !itemStart(item) ? "All day" : formatDateTime(item.start_at ?? "")}
                        </span>
                        {renderItem(item)}
                        {canManage && item.source === "event" && (
                          <button onClick={() => handleDelete(item.id)} className="hidden rounded-lg p-1 text-faint hover:bg-danger/10 hover:text-danger group-hover:block" title="Delete event">
                            <Plus className="h-3.5 w-3.5 rotate-45" />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Calendar"
        description="The organization's time — events, deadlines and meetings."
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> New event
            </Button>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => navigate(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="secondary" onClick={goToday}>Today</Button>
          <Button size="sm" variant="secondary" onClick={() => navigate(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <span className="text-sm font-semibold text-ink">{label}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap items-center gap-1 rounded-lg border border-line bg-surface p-0.5">
            {(["", "event", "meeting", "task", "leave", "holiday"] as const).map((source) => (
              <button
                key={source || "all"}
                onClick={() => setSourceFilter(source)}
                className={classNames(
                  "rounded-md px-2.5 py-1.5 text-[12px] font-medium",
                  sourceFilter === source ? "bg-brand text-white" : "text-muted hover:text-ink"
                )}
              >
                {source ? SOURCE_META[source].label : "All"}
              </button>
            ))}
          </div>
          <Select className="h-9 w-40" aria-label="Scope" options={SCOPE_OPTIONS.map((s) => ({ value: s, label: s }))}
            value={scopeFilter} onChange={(e) => setScopeFilter(e.target.value)} placeholder="All scopes" />
          <div className="flex items-center rounded-lg border border-line bg-surface p-0.5">
            {([
              ["week", "Week", CalendarDays],
              ["month", "Month", CalendarDays],
              ["agenda", "Agenda", ListOrdered],
            ] as const).map(([value, viewLabel, Icon]) => (
              <button
                key={value}
                onClick={() => setView(value)}
                className={classNames(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium",
                  view === value ? "bg-brand text-white" : "text-muted hover:text-ink"
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {viewLabel}
              </button>
            ))}
          </div>
        </div>
      </div>

      {renderView()}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="New event" description="Put something on the calendar.">
        <form onSubmit={handleCreate} className="space-y-4">
          {formError && <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>}
          <Input label="Title" name="title" required placeholder="Design review" />
          <Input label="Description" name="description" placeholder="What is this about?" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Start" name="start_at" type="datetime-local" required />
            <Input label="Location" name="location" placeholder="Room 4 / Zoom" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Type" name="event_type" defaultValue="event" options={EVENT_TYPES.map((t) => ({ value: t, label: t }))} />
            <Select label="Scope" name="calendar_scope" defaultValue="personal" options={SCOPE_OPTIONS.map((s) => ({ value: s, label: s }))} />
          </div>
          <label className="flex items-center gap-2 text-[13px] font-medium text-muted">
            <input type="checkbox" name="all_day" className="h-4 w-4 rounded border-line accent-brand" />
            All day
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button type="submit" loading={saving}>Create event</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
