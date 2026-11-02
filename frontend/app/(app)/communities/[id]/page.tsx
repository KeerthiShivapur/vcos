"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, LogIn, LogOut, UserPlus } from "lucide-react";

import {
  deleteCommunity,
  getCommunity,
  getMyEmployee,
  joinCommunity,
  leaveCommunity,
  listCommunityMembers,
  setCommunityRole,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { Community, CommunityMember } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/lib/utils";

export default function CommunityDetailPage() {
  return (
    <Suspense fallback={null}>
      <CommunityDetailContent />
    </Suspense>
  );
}

function CommunityDetailContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.COMMUNICATION_MANAGE);

  const [community, setCommunity] = useState<Community | null>(null);
  const [members, setMembers] = useState<CommunityMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [myEmployeeId, setMyEmployeeId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [communityData, membersData, me] = await Promise.all([
        getCommunity(params.id),
        listCommunityMembers(params.id),
        getMyEmployee().catch(() => null),
      ]);
      setCommunity(communityData);
      setMembers(membersData);
      setMyEmployeeId(me?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load community");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function toggleMembership() {
    if (!community) return;
    setBusy(true);
    try {
      if (community.is_member) {
        await leaveCommunity(community.id);
      } else {
        await joinCommunity(community.id);
      }
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to update membership",
      );
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(
    member: CommunityMember,
    role: "owner" | "moderator" | "member",
  ) {
    if (!community) return;
    setBusy(true);
    try {
      await setCommunityRole(community.id, member.employee_id, role);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update role");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!community) return;
    setBusy(true);
    try {
      await deleteCommunity(community.id);
      router.push("/communities");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to delete community",
      );
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner label="Loading community" />
      </div>
    );
  }

  if (error || !community) {
    return (
      <ErrorState
        title="Could not load community"
        message={error ?? "Not found"}
        onRetry={load}
      />
    );
  }

  const iAmOwner =
    community.my_role === "owner" ||
    (community.owner_id === myEmployeeId && community.is_member) ||
    canManage;

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/communities")}
      >
        <ArrowLeft className="h-4 w-4" /> All communities
      </Button>

      <PageHeader
        title={community.name}
        description={community.description ?? undefined}
        breadcrumb="Community"
        actions={
          <div className="flex gap-2">
            {!community.is_member ? (
              <Button size="sm" onClick={toggleMembership} loading={busy}>
                <LogIn className="h-4 w-4" /> Join
              </Button>
            ) : (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    router.push(`/feed?community_id=${community.id}`)
                  }
                >
                  View feed
                </Button>
                {iAmOwner && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => setDeleteOpen(true)}
                  >
                    Delete
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={toggleMembership}
                  loading={busy}
                >
                  <LogOut className="h-4 w-4" /> Leave
                </Button>
              </>
            )}
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-4 md:col-span-2">
          <div className="rounded-lg border border-line bg-surface p-5">
            <div className="flex flex-wrap gap-2">
              <Badge tone="brand">{community.type}</Badge>
              <Badge tone="neutral">{community.visibility}</Badge>
              {community.is_featured && <Badge tone="warning">Featured</Badge>}
              {community.is_archived && <Badge tone="danger">Archived</Badge>}
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-4 text-[13px] sm:grid-cols-3">
              <div>
                <dt className="text-faint">Members</dt>
                <dd className="mt-0.5 font-semibold text-ink">
                  {community.member_count}
                </dd>
              </div>
              <div>
                <dt className="text-faint">Posts</dt>
                <dd className="mt-0.5 font-semibold text-ink">
                  {community.post_count}
                </dd>
              </div>
              <div>
                <dt className="text-faint">Created</dt>
                <dd className="mt-0.5 font-semibold text-ink">
                  {formatDate(community.created_at)}
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-lg border border-line bg-surface">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <h3 className="text-sm font-semibold text-ink">
                Members ({members.length})
              </h3>
            </div>
            {members.length === 0 ? (
              <EmptyState
                icon={UserPlus}
                title="No members yet"
                description="Invite colleagues to join this community."
              />
            ) : (
              <ul className="divide-y divide-line">
                {members.map((member) => {
                  const isMe = member.employee_id === myEmployeeId;
                  return (
                    <li
                      key={member.id}
                      className="flex items-center gap-3 px-5 py-3"
                    >
                      <Avatar name={member.employee_name} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-semibold text-ink">
                          {member.employee_name ?? "Unknown"}
                          {isMe && (
                            <span className="ml-1.5 text-[11px] font-normal text-faint">
                              (you)
                            </span>
                          )}
                        </p>
                      </div>
                      <Badge
                        tone={
                          member.role === "owner"
                            ? "brand"
                            : member.role === "moderator"
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {member.role}
                      </Badge>
                      {iAmOwner && !isMe && member.role !== "owner" && (
                        <div className="flex gap-1">
                          {member.role === "moderator" ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={busy}
                              onClick={() => changeRole(member, "member")}
                            >
                              Demote
                            </Button>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={busy}
                              onClick={() => changeRole(member, "moderator")}
                            >
                              Make moderator
                            </Button>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>

      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete community"
        description="This will permanently delete the community and all of its posts. This cannot be undone."
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={remove} loading={busy}>
              Delete community
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-muted">
          Are you sure you want to delete{" "}
          <span className="font-semibold text-ink">{community.name}</span>?
        </p>
      </Modal>
    </div>
  );
}
