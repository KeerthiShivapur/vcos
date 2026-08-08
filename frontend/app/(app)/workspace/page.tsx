"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  FileText,
  Link2,
  Pencil,
  Plus,
  Search,
  Trash2,
  Zap,
} from "lucide-react";

import { api } from "@/lib/api";
import { Paginated, WorkspaceItem } from "@/types";
import { useFetch } from "@/hooks/useFetch";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Tabs } from "@/components/ui/Tabs";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

type ItemKind = "note" | "bookmark" | "shortcut";

const KIND_META: Record<ItemKind, { label: string; icon: React.ReactNode; createLabel: string }> = {
  note: { label: "Note", icon: <FileText className="h-4 w-4" />, createLabel: "Create note" },
  bookmark: { label: "Bookmark", icon: <Link2 className="h-4 w-4" />, createLabel: "Save bookmark" },
  shortcut: { label: "Shortcut", icon: <Zap className="h-4 w-4" />, createLabel: "Add shortcut" },
};

const TABS: { id: string; label: string }[] = [
  { id: "all", label: "All" },
  { id: "note", label: "Notes" },
  { id: "bookmark", label: "Bookmarks" },
  { id: "shortcut", label: "Shortcuts" },
];

export default function WorkspacePage() {
  return (
    <Suspense fallback={null}>
      <WorkspaceContent />
    </Suspense>
  );
}

function WorkspaceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedNew = searchParams.get("new");

  const [items, setItems] = useState<WorkspaceItem[]>([]);
  const [kind, setKind] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createType, setCreateType] = useState<ItemKind | null>(null);
  const [formTitle, setFormTitle] = useState("");
  const [formContent, setFormContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [editing, setEditing] = useState<WorkspaceItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<Paginated<WorkspaceItem>>("/workspace/items", {
        query: { kind: kind ?? undefined, page_size: 200 },
      });
      const filtered = query.trim()
        ? data.items.filter(
            (i) =>
              i.title.toLowerCase().includes(query.trim().toLowerCase()) ||
              (i.content ?? "").toLowerCase().includes(query.trim().toLowerCase())
          )
        : data.items;
      setItems(filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load workspace");
    } finally {
      setLoading(false);
    }
  }, [kind, query]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (requestedNew && ["note", "bookmark", "shortcut"].includes(requestedNew)) {
      setCreateType(requestedNew as ItemKind);
      setFormTitle("");
      setFormContent("");
      router.replace("/workspace");
    }
  }, [requestedNew]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!createType) return;
    setFormError(null);
    if (!formTitle.trim()) {
      setFormError("Title is required.");
      return;
    }
    setSaving(true);
    try {
      await api<WorkspaceItem>("/workspace/items", {
        method: "POST",
        body: {
          kind: createType,
          title: formTitle.trim(),
          content: createType === "note" ? formContent : formContent.trim() || undefined,
        },
      });
      toastSuccess(`${KIND_META[createType].label} created`);
      setCreateType(null);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to create item");
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdate() {
    if (!editing) return;
    setSaving(true);
    try {
      await api<WorkspaceItem>(`/workspace/items/${editing.id}`, {
        method: "PATCH",
        body: {
          title: editing.title,
          content: editing.content ?? undefined,
          pinned: editing.pinned,
        },
      });
      toastSuccess("Item updated");
      setEditing(null);
      await load();
    } catch (err) {
      toastError("Update failed", err instanceof Error ? err.message : undefined);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: WorkspaceItem) {
    if (!confirm(`Delete "${item.title}"? This cannot be undone.`)) return;
    try {
      await api(`/workspace/items/${item.id}`, { method: "DELETE" });
      toastSuccess("Deleted");
      await load();
    } catch (err) {
      toastError("Delete failed", err instanceof Error ? err.message : undefined);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workspace"
        description="Your personal notes, bookmarks, and shortcuts."
        actions={
          <DropdownNew
            onCreate={(kind) => {
              setCreateType(kind);
              setFormTitle("");
              setFormContent("");
            }}
          />
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-sm flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <Input
            className="pl-9"
            placeholder="Filter items..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <Tabs
          tabs={TABS}
          active={kind ?? "all"}
          onChange={(id) => setKind(id === "all" ? null : id)}
        />
      </div>

      {error ? (
        <ErrorState title="Could not load workspace" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading workspace" /></div>
      ) : items.length === 0 ? (
        <EmptyState
          title="Your workspace is empty"
          description="Create a note, save a bookmark, or add a shortcut to get started."
          action={
            <Button size="sm" onClick={() => { setCreateType("note"); setFormTitle(""); setFormContent(""); }}>
              <Plus className="h-4 w-4" /> Create a note
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <WorkspaceCard
              key={item.id}
              item={item}
              onEdit={() => setEditing(item)}
              onDelete={() => handleDelete(item)}
            />
          ))}
        </div>
      )}

      <Modal
        open={Boolean(createType)}
        onClose={() => setCreateType(null)}
        title={createType ? `New ${KIND_META[createType].label.toLowerCase()}` : ""}
        description="Saved to your personal workspace."
      >
        {createType && (
          <form onSubmit={handleCreate} className="space-y-4">
            {formError && (
              <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">{formError}</div>
            )}
            <Input label="Title" required autoFocus placeholder={createType === "note" ? "Weekly planning" : "Nova Labs website"} value={formTitle} onChange={(e) => setFormTitle(e.target.value)} />
            {createType === "note" ? (
              <Textarea label="Content" rows={6} placeholder="Write a note..." value={formContent} onChange={(e) => setFormContent(e.target.value)} />
            ) : (
              <Input label="URL" type="url" placeholder="https://..." value={formContent} onChange={(e) => setFormContent(e.target.value)} />
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setCreateType(null)}>Cancel</Button>
              <Button type="submit" loading={saving}>{KIND_META[createType].createLabel}</Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title="Edit item">
        {editing && (
          <div className="space-y-4">
            <Input label="Title" value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
            {editing.kind === "note" ? (
              <Textarea label="Content" rows={6} value={editing.content ?? ""} onChange={(e) => setEditing({ ...editing, content: e.target.value })} />
            ) : (
              <Input label="URL" type="url" value={editing.content ?? ""} onChange={(e) => setEditing({ ...editing, content: e.target.value })} />
            )}
            <label className="flex items-center gap-2 text-[13px] text-muted">
              <input
                type="checkbox"
                checked={editing.pinned}
                onChange={(e) => setEditing({ ...editing, pinned: e.target.checked })}
                className="h-3.5 w-3.5 rounded border-line accent-brand"
              />
              Pin to the top of my workspace
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button loading={saving} onClick={handleUpdate}>Save changes</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

function DropdownNew({ onCreate }: { onCreate: (kind: ItemKind) => void }) {
  return (
    <div className="flex gap-2">
      <Button size="sm" onClick={() => onCreate("note")}>
        <FileText className="h-4 w-4" /> Note
      </Button>
      <Button size="sm" variant="secondary" onClick={() => onCreate("bookmark")}>
        <Link2 className="h-4 w-4" /> Bookmark
      </Button>
      <Button size="sm" variant="secondary" onClick={() => onCreate("shortcut")}>
        <Zap className="h-4 w-4" /> Shortcut
      </Button>
    </div>
  );
}

function WorkspaceCard({
  item,
  onEdit,
  onDelete,
}: {
  item: WorkspaceItem;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const meta = KIND_META[item.kind as ItemKind] ?? KIND_META.note;
  const isLink = item.kind !== "note" && Boolean(item.content?.startsWith("http"));

  return (
    <Card className="group flex flex-col transition-shadow hover:shadow-popover">
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <Badge tone={item.kind === "note" ? "brand" : item.kind === "bookmark" ? "warning" : "neutral"}>
            {meta.icon} {meta.label}
          </Badge>
          <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <button className="icon-btn" onClick={onEdit} aria-label="Edit"><Pencil className="h-3.5 w-3.5" /></button>
            <button className="icon-btn hover:!text-danger" onClick={onDelete} aria-label="Delete"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        </div>
        {isLink ? (
          <a href={item.content!} target="_blank" rel="noreferrer" className="font-medium text-ink hover:text-brand hover:underline">
            {item.title}
          </a>
        ) : (
          <h3 className="font-medium text-ink">{item.title}</h3>
        )}
        {item.kind === "note" && item.content ? (
          <p className="line-clamp-3 text-[13px] leading-relaxed text-muted whitespace-pre-wrap">{item.content}</p>
        ) : isLink ? (
          <p className="line-clamp-1 text-[13px] text-faint">{item.content}</p>
        ) : null}
      </div>
      <div className="flex items-center justify-between border-t border-line px-4 py-2.5">
        <span className="text-[12px] text-faint">{formatDate(item.created_at)}</span>
        {item.pinned && <Badge tone="brand">Pinned</Badge>}
      </div>
    </Card>
  );
}
