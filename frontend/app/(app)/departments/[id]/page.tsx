"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Building2, Users, UserSquare2 } from "lucide-react";

import {
  getDepartment,
  getDepartmentStats,
  listEmployees,
  listTeams,
} from "@/lib/api";
import type {
  Department,
  DepartmentStats,
  EmployeeSummary,
  Team,
} from "@/types";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate } from "@/lib/utils";

export default function DepartmentDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailContent />
    </Suspense>
  );
}

function DetailContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [department, setDepartment] = useState<Department | null>(null);
  const [stats, setStats] = useState<DepartmentStats | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [members, setMembers] = useState<EmployeeSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [dep, deptStats, allTeams, allEmployees] = await Promise.all([
          getDepartment(id),
          getDepartmentStats(id).catch(() => null),
          listTeams(),
          listEmployees({ page_size: 200 }),
        ]);
        setDepartment(dep);
        setStats(deptStats);
        setTeams(allTeams.filter((t) => t.department_id === id));
        setMembers(allEmployees.filter((e) => e.department_id === id));
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load department",
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader title="Department" breadcrumb="Departments" />
        <ErrorState title="Could not load department" message={error} />
      </div>
    );
  }

  if (loading || !department) {
    return (
      <div className="space-y-6">
        <PageHeader title="Department" breadcrumb="Departments" />
        <div className="flex justify-center py-24">
          <Spinner label="Loading department" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={department.name}
        breadcrumb="Departments"
        description={department.description ?? "No description provided."}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Members"
          value={department.members_count}
          icon={Users}
        />
        <StatCard
          label="Teams"
          value={department.teams_count}
          icon={UserSquare2}
        />
        <StatCard
          label="Avg expertise"
          value={stats ? Math.round(stats.avg_expertise) : "—"}
          icon={Building2}
          hint="Across the department"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Overview" className="lg:col-span-1">
          <dl className="space-y-3 text-[13px]">
            <div className="flex justify-between gap-2">
              <dt className="text-faint">Code</dt>
              <dd className="font-medium text-ink">{department.code}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-faint">Parent</dt>
              <dd className="font-medium text-ink">
                {department.parent_name || "—"}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-faint">Location</dt>
              <dd className="font-medium text-ink">
                {department.location_name || "—"}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-faint">Head</dt>
              <dd className="font-medium text-ink">
                {department.head_id ? (
                  <Link
                    href={`/people/${department.head_id}`}
                    className="hover:text-brand"
                  >
                    {department.head_name}
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
            </div>
          </dl>
          {stats && stats.skills.length > 0 && (
            <div className="mt-5 border-t border-line pt-4">
              <p className="text-[12px] font-semibold uppercase tracking-wide text-faint">
                Top skills
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {stats.skills.slice(0, 8).map((skill) => (
                  <Badge key={skill.skill} tone="brand">
                    {skill.skill} · {skill.count}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card
          title="Teams"
          subtitle={`${teams.length} teams`}
          className="lg:col-span-1"
        >
          {teams.length === 0 ? (
            <EmptyState
              icon={UserSquare2}
              title="No teams yet"
              description="Teams linked to this department will appear here."
            />
          ) : (
            <ul className="space-y-2.5">
              {teams.map((team) => (
                <li key={team.id}>
                  <Link
                    href={`/teams/${team.id}`}
                    className="flex items-center justify-between rounded-lg p-2 transition-colors hover:bg-canvas"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-ink">
                        {team.name}
                      </p>
                      <p className="truncate text-[11px] text-faint">
                        {team.code} · lead: {team.lead_name || "—"}
                      </p>
                    </div>
                    <Badge tone="neutral">{team.members_count}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Members"
          subtitle={`${members.length} people`}
          className="lg:col-span-1"
        >
          {members.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No members"
              description="Employees assigned to this department will appear here."
            />
          ) : (
            <ul className="space-y-2.5">
              {members.map((member) => (
                <li key={member.id}>
                  <Link
                    href={`/people/${member.id}`}
                    className="flex items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-canvas"
                  >
                    <Avatar
                      name={member.full_name}
                      src={member.avatar_url}
                      size="sm"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-ink">
                        {member.full_name}
                      </p>
                      <p className="truncate text-[11px] text-faint">
                        {member.designation || "Employee"}
                      </p>
                    </div>
                    <span className="text-[11px] text-faint">
                      {formatDate(member.joining_date)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
