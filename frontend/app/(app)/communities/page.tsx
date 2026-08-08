"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Users } from "lucide-react";

import { createCommunity, listCommunities } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Community } from "@/types";
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
import { formatDate } from "@/lib/utils";

const COMMUNITY_TYPES = ["general", "engineering", "product", "design", "social", "regional"];
const VISIBILITIES = ["public", "private", "hidden"];

export default function CommunitiesPage() {
  return (
    <Suspense fallback={null}>
      <CommunitiesContent />
    </Suspense>
  );
}

function CommunitiesContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.COMMUNICATION_MANAGE);
  const [communities, setCommunities] = useState<Community[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setCommunities(await listCommunities({ search: search || undefined, limit: 200 }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load communities");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Communities"
        description="Shared spaces for teams, interests, and initiatives."
        actions={canManage ? (
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> New community
          </Button>
        ) : undefined}
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-64">
          <Input
            placeholder="Search communities…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
        </div>
        <Button variant="secondary" size="sm" onClick={load}>Search</Button>
      </div>

      {error ? (
        <ErrorState title="Could not load communities" message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex justify-center py-24"><Spinner label="Loading communities" /></div>
      ) : communities.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No communities yet"
          description="Create a space for your team to share and collaborate."
          action={canManage ? (
            <Button size="sm" onClick={() => setCreateOpen(true)}><Plus className="h-4 w-4" /> New community</Button>
          ) : undefined}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {communities.map((community) => (
            <Link
              key={community.id}
              href={`/communities/${community.id}`}
              className="group rounded-lg border border-line bg-surface p-5 transition hover:border-brand/40 hover:bg-surface-muted"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-lg font-bold text-brand">
                  {community.icon ?? community.name.charAt(0).toUpperCase()}
                </div>
                <div className="flex gap-1.5">
                  <Badge tone="neutral">{community.type}</Badge>
                  {community.is_member && <Badge tone="brand">Joined</Badge>}
                </div>
              </div>
              <h3 className="mt-3 truncate text-[15px] font-semibold text-ink">{community.name}</h3>
              {community.description && (
                <p className="mt-1 line-clamp-2 text-[13px] text-muted">{community.description}</p>
              )}
              <div className="mt-3 flex items-center gap-3 text-[12px] text-faint">
                <span className="flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {community.member_count}</span>
                <span>{community.post_count} posts</span>
                <span className="ml-auto">{formatDate(community.created_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      <CreateCommunityModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreate={async (payload) => {
          setCreating(true);
          try {
            const created = await createCommunity(payload);
            setCommunities((prev) => [created, ...prev]);
            setCreateOpen(false);
          } finally {
            setCreating(false);
          }
        }}
        creating={creating}
      />
    </div>
  );
}

function CreateCommunityModal({
  open,
  onClose,
  onCreate,
  creating,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (payload: {
    name: string;
    description?: string;
    type?: string;
    visibility?: string;
    icon?: string;
  }) => Promise<void>;
  creating: boolean;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("general");
  const [visibility, setVisibility] = useState("public");
  const [icon, setIcon] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setName("");
    setDescription("");
    setType("general");
    setVisibility("public");
    setIcon("");
    setError(null);
  }

  async function submit() {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setError(null);
    try {
      await onCreate({
        name: name.trim(),
        description: description.trim() || undefined,
        type,
        visibility,
        icon: icon.trim() || undefined,
      });
      reset();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create community");
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose(); }}
      title="New community"
      description="Create a shared space for your team or initiative."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={creating}>Create</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Name" placeholder="e.g. Engineering Guild" value={name} onChange={(e) => setName(e.target.value)} />
        <Textarea label="Description" placeholder="What is this community about?" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Type"
            value={type}
            onChange={(e) => setType(e.target.value)}
            options={COMMUNITY_TYPES.map((t) => ({ value: t, label: t }))}
          />
          <Select
            label="Visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
            options={VISIBILITIES.map((v) => ({ value: v, label: v }))}
          />
        </div>
        <Input label="Icon (emoji)" placeholder="🎯" value={icon} onChange={(e) => setIcon(e.target.value)} />
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Modal>
  );
}
