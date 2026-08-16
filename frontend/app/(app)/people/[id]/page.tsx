"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Award, Briefcase, GraduationCap, Mail, MapPin, Phone, Star, Users, History } from "lucide-react";

import {
  addFavorite,
  getColleagues,
  getDirectReports,
  getEmployee,
  getEmployeeExpertise,
  getEmployeeTimeline,
  getMentors,
  getSuccessors,
  removeFavorite,
} from "@/lib/api";
import { PERMISSIONS } from "@/lib/permissions";
import type { Employee, EmployeeSummary, ExpertiseScore, Mentor, Successor, TimelineEntry } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { Avatar } from "@/components/ui/Avatar";
import ExpertiseEvidencePanel from "@/components/people/ExpertiseEvidencePanel";
import { ResponsibilitiesCard } from "@/components/people/ResponsibilitiesPanel";
import { formatDate, timeAgo } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

function presenceTone(status: string | null | undefined, online: boolean) {
  if (online || status === "online") return { label: "Online", cls: "text-emerald-600" };
  if (status === "busy") return { label: "Busy", cls: "text-amber-600" };
  if (status === "away") return { label: "Away", cls: "text-amber-500" };
  return { label: "Offline", cls: "text-gray-400" };
}

export default function EmployeeProfilePage() {
  return (
    <Suspense fallback={null}>
      <ProfileContent />
    </Suspense>
  );
}

function ProfileContent() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { can } = useAuth();
  const canFavorite = can(PERMISSIONS.FAVORITES_MANAGE);

  const [employee, setEmployee] = useState<Employee | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [reports, setReports] = useState<EmployeeSummary[]>([]);
  const [colleagues, setColleagues] = useState<EmployeeSummary[]>([]);
  const [scores, setScores] = useState<ExpertiseScore[]>([]);
  const [successors, setSuccessors] = useState<Successor[]>([]);
  const [mentors, setMentors] = useState<Mentor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [emp, tl, reps, colls, exp] = await Promise.all([
          getEmployee(id),
          getEmployeeTimeline(id),
          getDirectReports(id),
          getColleagues(id),
          getEmployeeExpertise(id).catch(() => [] as ExpertiseScore[]),
        ]);
        if (!active) return;
        setEmployee(emp);
        setTimeline(tl);
        setReports(reps);
        setColleagues(colls);
        setScores(exp);
        getSuccessors(id).then(setSuccessors).catch(() => undefined);
        getMentors(id).then(setMentors).catch(() => undefined);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Unable to load profile");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [id]);

  async function toggleFavorite() {
    if (!employee) return;
    try {
      if (employee.is_favorite) {
        await removeFavorite(employee.id);
      } else {
        await addFavorite(employee.id);
      }
      setEmployee({ ...employee, is_favorite: !employee.is_favorite });
      toastSuccess(employee.is_favorite ? "Removed from favorites" : "Added to favorites");
    } catch (err) {
      toastError("Failed to update favorite", err instanceof Error ? err.message : undefined);
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader title="Employee profile" breadcrumb="People" />
        <ErrorState title="Could not load profile" message={error} />
      </div>
    );
  }

  if (loading || !employee) {
    return (
      <div className="space-y-6">
        <PageHeader title="Employee profile" breadcrumb="People" />
        <div className="flex justify-center py-24"><Spinner label="Loading profile" /></div>
      </div>
    );
  }

  const presence = presenceTone(employee.presence_status, employee.is_online);
  const maxScore = Math.max(10, ...scores.map((s) => s.score));

  return (
    <div className="space-y-6">
      <PageHeader
        title={employee.full_name}
        breadcrumb="People"
        description={`${employee.designation || "Employee"} Â· ${employee.employee_number}`}
        actions={
          canFavorite ? (
            <Button size="sm" variant={employee.is_favorite ? "secondary" : "primary"} onClick={toggleFavorite}>
              <Star className="h-4 w-4" /> {employee.is_favorite ? "Favorited" : "Favorite"}
            </Button>
          ) : undefined
        }
      />

      <Card className="!p-0">
        <div className="flex flex-wrap items-start gap-5 p-6">
          <Avatar name={employee.full_name} src={employee.avatar_url} size="lg" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-ink">{employee.full_name}</h2>
              <span className={`text-sm font-medium ${presence.cls}`}>â— {presence.label}</span>
              <Badge tone={employee.status === "active" ? "success" : employee.status === "probation" ? "warning" : "neutral"}>
                {employee.status}
              </Badge>
              {employee.availability_status && employee.availability_status !== "available" && (
                <Badge tone={employee.availability_status === "leave" ? "warning" : "neutral"}>
                  {employee.availability_status}
                </Badge>
              )}
            </div>
            <p className="mt-1 text-sm text-muted">{employee.designation || "No designation"}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {employee.department_name && <Badge tone="brand">{employee.department_name}</Badge>}
              {employee.team_name && <Badge>{employee.team_name}</Badge>}
              {employee.location_name && <Badge><MapPin className="mr-1 h-3 w-3" /> {employee.location_name}</Badge>}
            </div>
            <div className="mt-4 grid gap-2 text-[13px] text-muted sm:grid-cols-2">
              <span className="flex items-center gap-2"><Mail className="h-3.5 w-3.5 text-faint" /> {employee.email}</span>
              {employee.phone && <span className="flex items-center gap-2"><Phone className="h-3.5 w-3.5 text-faint" /> {employee.phone}</span>}
              {employee.manager_name && (
                <Link href={`/people/${employee.manager_id}`} className="flex items-center gap-2 hover:text-brand">
                  <Briefcase className="h-3.5 w-3.5 text-faint" /> Reports to {employee.manager_name}
                </Link>
              )}
              <span className="flex items-center gap-2"><Users className="h-3.5 w-3.5 text-faint" /> {employee.reports_count} direct reports</span>
              <span className="flex items-center gap-2"><History className="h-3.5 w-3.5 text-faint" /> Joined {formatDate(employee.joining_date)}</span>
              <span className="flex items-center gap-2"><MapPin className="h-3.5 w-3.5 text-faint" /> {employee.timezone}</span>
            </div>
            <div className="mt-4 flex flex-wrap gap-4">
              <ProfileMetric label="Expertise" value={employee.expertise_score} />
              <ProfileMetric label="Profile completion" value={`${employee.profile_completion}%`} />
            </div>
          </div>
        </div>
        {employee.ai_summary && (
          <div className="border-t border-line px-6 py-4">
            <p className="text-[12px] font-semibold uppercase tracking-wide text-faint">AI summary</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{employee.ai_summary}</p>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {employee.bio && (
            <Card title="About">
              <p className="text-[13px] leading-relaxed text-muted whitespace-pre-wrap">{employee.bio}</p>
              <div className="mt-4 grid grid-cols-2 gap-3 text-[13px]">
                <Info label="Employment type" value={employee.employment_type} />
                <Info label="Language" value={employee.language} />
                <Info label="Business unit" value={employee.business_unit_name} />
                <Info label="Employee number" value={employee.employee_number} />
              </div>
            </Card>
          )}

          <Card
            title="Skills & expertise"
            subtitle="Scored by the expertise engine from experience, level, and usage."
            actions={
              employee.expertise_score > 0 ? (
                <Badge tone="brand">{employee.expertise_score}/100</Badge>
              ) : undefined
            }
          >
            {scores.length === 0 ? (
              <EmptyState
                icon={GraduationCap}
                title="No expertise scores yet"
                description="Skills and experience will be scored automatically as the profile evolves."
              />
            ) : (
              <div className="space-y-4">
                {scores.map((score) => (
                  <div key={score.id}>
                    <div className="flex items-center justify-between text-[13px]">
                      <span className="font-medium text-ink">{score.skill_name}</span>
                      <span className="text-muted">
                        L{score.level} Â· {Math.round(score.years_experience)}y Â· {score.score}/100
                      </span>
                    </div>
                    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-canvas">
                      <div
                        className="h-full rounded-full bg-brand"
                        style={{ width: `${Math.round((score.score / maxScore) * 100)}%` }}
                      />
                    </div>
                    <ExpertiseEvidencePanel personId={id} skill={score} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Responsibilities" subtitle="Declared and observed ownership — never assumed.">
            <ResponsibilitiesCard personId={id} personName={employee.full_name} />
          </Card>

          <Card title="Timeline" subtitle="Every milestone â€” nothing lost.">
            {timeline.length === 0 ? (
              <EmptyState icon={History} title="No timeline events yet" description="Joins, promotions, transfers, and recognition will appear here." />
            ) : (
              <ol className="space-y-0">
                {timeline.map((entry) => (
                  <li key={entry.id} className="relative flex gap-4 pb-5 last:pb-0">
                    <span className="absolute left-[5px] top-5 h-full w-px bg-line" />
                    <span className="relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-2 border-brand bg-elevated" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <p className="text-[13px] font-semibold text-ink">{entry.title}</p>
                        <span className="text-[11px] text-faint">{formatDate(entry.occurred_at)}</span>
                      </div>
                      {entry.description && (
                        <p className="mt-0.5 text-[12px] leading-relaxed text-muted">{entry.description}</p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Team" subtitle={`${employee.team_name ?? "No team assigned"}`}>
            {reports.length === 0 ? (
              <p className="text-[13px] text-faint">No direct reports.</p>
            ) : (
              <ul className="space-y-2.5">
                {reports.map((report) => (
                  <li key={report.id}>
                    <Link href={`/people/${report.id}`} className="flex items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-canvas">
                      <Avatar name={report.full_name} src={report.avatar_url} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-ink">{report.full_name}</p>
                        <p className="truncate text-[11px] text-faint">{report.designation || "Employee"}</p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Certifications">
            {employee.certifications.length === 0 ? (
              <p className="text-[13px] text-faint">No certifications listed.</p>
            ) : (
              <ul className="space-y-3">
                {employee.certifications.map((cert) => (
                  <li key={cert.id} className="flex items-start gap-2.5">
                    <Award className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-ink">{cert.name}</p>
                      <p className="text-[11px] text-faint">
                        {[cert.issuer, cert.issue_date ? formatDate(cert.issue_date) : null]
                          .filter(Boolean)
                          .join(" Â· ") || "No details"}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Achievements">
            {employee.achievements.length === 0 ? (
              <p className="text-[13px] text-faint">No achievements yet.</p>
            ) : (
              <ul className="space-y-3">
                {employee.achievements.map((achievement) => (
                  <li key={achievement.id} className="flex items-start gap-2.5">
                    <Star className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-ink">{achievement.title}</p>
                      {achievement.description && (
                        <p className="text-[12px] text-muted">{achievement.description}</p>
                      )}
                      <p className="mt-0.5 text-[11px] text-faint">{achievement.kind}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {colleagues.length > 0 && (
            <Card title="Colleagues" subtitle="Same team or department">
              <ul className="space-y-2.5">
                {colleagues.slice(0, 6).map((colleague) => (
                  <li key={colleague.id}>
                    <Link href={`/people/${colleague.id}`} className="flex items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-canvas">
                      <Avatar name={colleague.full_name} src={colleague.avatar_url} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-ink">{colleague.full_name}</p>
                        <p className="truncate text-[11px] text-faint">{colleague.designation || "Employee"}</p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {successors.length > 0 && (
            <Card title="Potential successors" subtitle="AI-ranked by skills, leadership, and experience">
              <ul className="space-y-3">
                {successors.map((successor) => (
                  <li key={successor.employee_id}>
                    <Link href={`/people/${successor.employee_id}`} className="block rounded-lg p-2 transition-colors hover:bg-canvas">
                      <div className="flex items-center gap-2.5">
                        <Avatar name={successor.name} src={successor.avatar_url} size="sm" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-ink">{successor.name}</p>
                          <p className="truncate text-[11px] text-faint">{successor.designation || "Employee"}</p>
                        </div>
                        <Badge tone="brand">{successor.score}%</Badge>
                      </div>
                      <p className="mt-1.5 text-[11px] leading-relaxed text-faint">{successor.reasons.join(" Â· ")}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {mentors.length > 0 && (
            <Card title="Suggested mentors">
              <ul className="space-y-2.5">
                {mentors.map((mentor) => (
                  <li key={`${mentor.employee_id}-${mentor.skill}`}>
                    <Link href={`/people/${mentor.employee_id}`} className="flex items-center gap-2.5 rounded-lg p-1.5 transition-colors hover:bg-canvas">
                      <Avatar name={mentor.name} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-ink">{mentor.name}</p>
                        <p className="truncate text-[11px] text-faint">{mentor.skill} Â· {Math.round(mentor.years_experience)}y exp</p>
                      </div>
                      <Badge tone="neutral">{mentor.score}%</Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function ProfileMetric({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <p className="text-lg font-semibold text-ink">{value}</p>
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">{label}</p>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">{label}</p>
      <p className="mt-0.5 text-[13px] text-ink">{value || "â€”"}</p>
    </div>
  );
}
