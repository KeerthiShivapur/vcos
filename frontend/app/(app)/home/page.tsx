"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Building2,
  CheckCircle2,
  FileText,
  Link2,
  Plus,
  Search,
  UserPlus,
  Users,
  Zap,
} from "lucide-react";

import { api } from "@/lib/api";
import { DashboardSummary } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { useFetch } from "@/hooks/useFetch";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";

export default function HomePage() {
  const { user, organization } = useAuth();
  const { data, loading, error } = useFetch<DashboardSummary>("/dashboard/summary");

  if (error) return <ErrorState title="Could not load dashboard" message={error} />;
  if (loading || !data) return <div className="flex justify-center py-24"><Spinner label="Loading dashboard" /></div>;

  const firstName = user?.full_name?.split(" ")[0] ?? "there";
  const isFounder = user?.role === "ceo";

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}, ${firstName}.`}
        description={data.organization_name ? `${data.organization_name} — here is what happened since your last visit.` : undefined}
        actions={
          <>
            <Link href="/search">
              <button className="btn-ghost"><Search className="h-4 w-4" /> Search</button>
            </Link>
            <Link href="/workspace?new=note">
              <button className="btn-primary"><Plus className="h-4 w-4" /> New</button>
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Link href="/settings?tab=members">
          <StatCard
            icon={Users}
            label="Team members"
            value={String(data.total_users)}
            hint={`${data.active_users} active`}
          />
        </Link>
        <Link href="/settings?tab=audit">
          <StatCard
            icon={Activity}
            label="Recent activity"
            value={String(data.recent_activity.length)}
            hint="last 7 days"
          />
        </Link>
        <Link href="/notifications">
          <StatCard
            icon={CheckCircle2}
            label="Unread notifications"
            value={String(data.unread_notifications)}
          />
        </Link>
        <Link href="/settings?tab=roles">
          <StatCard
            icon={Users}
            label="Roles"
            value={String(data.roles_count)}
            hint={`${data.pending_invitations} pending invites`}
          />
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card className="border-brand/20 bg-brand/[0.04]">
            <div className="flex items-start gap-3 p-5">
              <div className="rounded-xl bg-brand p-2.5 text-white"><Zap className="h-4 w-4" /></div>
              <div>
                <p className="font-medium text-ink">Your company operating system is live</p>
                <p className="mt-0.5 text-[13px] leading-relaxed text-muted">
                  {isFounder ? (
                    <>
                      You founded <span className="font-semibold text-ink">{data.organization_name}</span>. Invite your first
                      teammate to unlock roles, notifications, and shared workspace.
                    </>
                  ) : (
                    <>
                      You are part of <span className="font-semibold text-ink">{data.organization_name}</span>. Start a note or
                      check what your team has been working on.
                    </>
                  )}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {isFounder && (
                    <Link href="/settings?tab=members">
                      <button className="btn-primary h-8 text-[13px]"><UserPlus className="h-3.5 w-3.5" /> Invite a teammate</button>
                    </Link>
                  )}
                  <Link href="/workspace">
                    <button className="btn-ghost h-8 text-[13px]">Open workspace <ArrowRight className="h-3.5 w-3.5" /></button>
                  </Link>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Activity className="h-4 w-4 text-brand" /> Recent activity
              </h2>
              <Link href="/settings?tab=audit" className="text-[13px] font-medium text-brand hover:underline">
                View all
              </Link>
            </div>
            {data.recent_activity.length === 0 ? (
              <EmptyState
                title="No activity yet"
                description="Activity from your team will appear here."
              />
            ) : (
              <ul className="divide-y divide-line">
                {data.recent_activity.slice(0, 6).map((item) => (
                  <li key={item.id} className="flex items-center gap-3 px-5 py-3">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${item.severity === "error" ? "bg-danger" : item.severity === "warn" ? "bg-warning" : "bg-brand"}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] text-ink">
                        <span className="font-medium">{item.actor_email ?? "System"}</span>{" "}
                        <span className="text-muted">{item.action}</span>
                      </p>
                    </div>
                    <span className="shrink-0 text-[12px] text-faint">{formatDate(item.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">Quick actions</h2>
            </div>
            <div className="space-y-1 p-2">
              <QuickAction href="/workspace?new=note" icon={<FileText className="h-4 w-4" />} label="New note" />
              <QuickAction href="/workspace?new=bookmark" icon={<Link2 className="h-4 w-4" />} label="Save a bookmark" />
              <QuickAction href="/workspace?new=shortcut" icon={<Zap className="h-4 w-4" />} label="Add a shortcut" />
              <QuickAction href="/settings?tab=members" icon={<UserPlus className="h-4 w-4" />} label="Invite a member" />
              <QuickAction href="/search" icon={<Search className="h-4 w-4" />} label="Search everything" />
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <div className="mb-2 flex items-center gap-2">
                <Building2 className="h-4 w-4 text-brand" />
                <h2 className="text-sm font-semibold text-ink">{data.organization_name}</h2>
                <Badge tone="brand">{isFounder ? "Owner" : "Member"}</Badge>
              </div>
              <p className="font-mono text-[12px] text-faint">{data.organization_slug}</p>
              {data.workspace && (
                <div className="mt-4 border-t border-line pt-4">
                  <p className="text-[12px] font-semibold uppercase tracking-wider text-faint">My workspace</p>
                  {data.workspace.items.length === 0 ? (
                    <p className="mt-2 text-[13px] text-muted">No items yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-1.5">
                      {data.workspace.items.slice(0, 4).map((item) => (
                        <li key={item.id} className="flex items-center gap-2 text-[13px] text-ink">
                          {item.kind === "note" ? <FileText className="h-3.5 w-3.5 shrink-0 text-faint" /> : item.kind === "bookmark" ? <Link2 className="h-3.5 w-3.5 shrink-0 text-faint" /> : <Zap className="h-3.5 w-3.5 shrink-0 text-faint" />}
                          <span className="truncate">{item.title}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function QuickAction({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] text-muted transition-colors hover:bg-brand/5 hover:text-ink"
    >
      <span className="text-faint">{icon}</span>
      {label}
      <ArrowRight className="ml-auto h-3.5 w-3.5 text-faint" />
    </Link>
  );
}
