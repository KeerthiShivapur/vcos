"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Brain,
  Building2,
  CheckCircle2,
  CheckSquare2,
  Clock,
  GraduationCap,
  LayoutDashboard,
  Lightbulb,
  Map,
  RefreshCw,
  Rocket,
  Send,
  Sparkles,
  Target,
  Trophy,
  UserRound,
  Users,
} from "lucide-react";

import {
  addMentorshipSession,
  askLearningAi,
  assignAssessment,
  closeSkillGap,
  completeOnboardingTask,
  createOnboardingPlan,
  detectPromotionSignal,
  enrollCourse,
  enrollLearningPath,
  getLearningDashboard,
  getLearningHistory,
  getLearningProfile,
  getLearningRecommendations,
  getMentorProfile,
  getMyCareerProgress,
  getMySkillGaps,
  getMySkillGraph,
  getOnboardingPlan,
  getOrgSkillMap,
  joinAcademy,
  leaveAcademy,
  listAcademies,
  listAssessments,
  listCareerPaths,
  listCertifications,
  listCourses,
  listLearningPaths,
  listMentors,
  listMentorshipRequests,
  listOnboardingPlans,
  listPromotionSignals,
  myAcademies,
  myAssessmentAttempts,
  myCourseEnrollments,
  myEarnedCertifications,
  myLearningPathEnrollments,
  refreshLearningRecommendations,
  refreshSkillGaps,
  refreshSkillSnapshot,
  requestMentorship,
  respondToMentorship,
  reviewPromotionSignal,
  setLearningRecommendationStatus,
  startCertificationAttempt,
  upsertMentorProfile,
} from "@/lib/api";
import type {
  Academy,
  AiLearningAnswer,
  Assessment,
  AssessmentAttempt,
  CareerPath,
  CareerProgress,
  Certification,
  Course,
  EarnedCertification,
  LearningDashboard,
  LearningHistoryEntry,
  LearningPath,
  LearningRecommendationItem,
  LearningSkillGap,
  MentorMatch,
  MentorProfile,
  MentorshipRequest,
  OnboardingPlan,
  PromotionSignal,
  SkillGraphEntry,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs } from "@/components/ui/Tabs";
import { Input } from "@/components/ui/Input";

export default function LearningPage() {
  return (
    <Suspense fallback={null}>
      <LearningContent />
    </Suspense>
  );
}

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "courses", label: "Courses", icon: BookOpen },
  { id: "paths", label: "Paths", icon: Map },
  { id: "skills", label: "Skills", icon: Brain },
  { id: "assessments", label: "Assessments", icon: CheckSquare2 },
  { id: "certifications", label: "Certifications", icon: Trophy },
  { id: "mentorship", label: "Mentorship", icon: Users },
  { id: "career", label: "Career", icon: Target },
  { id: "academies", label: "Academies", icon: Building2 },
  { id: "onboarding", label: "Onboarding", icon: Rocket },
  { id: "ai", label: "AI Coach", icon: Sparkles },
];

function LearningContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.LEARNING_MANAGE);

  const tab = searchParams.get("tab") ?? "overview";
  const setTab = (id: string) => router.replace(`/learning?tab=${id}`);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // shared state
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof getLearningProfile>> | null>(null);
  const [history, setHistory] = useState<LearningHistoryEntry[]>([]);
  const [dashboard, setDashboard] = useState<LearningDashboard | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [myEnrollments, setMyEnrollments] = useState<Awaited<ReturnType<typeof myCourseEnrollments>>>([]);
  const [paths, setPaths] = useState<LearningPath[]>([]);
  const [myPaths, setMyPaths] = useState<Awaited<ReturnType<typeof myLearningPathEnrollments>>>([]);
  const [graph, setGraph] = useState<SkillGraphEntry[]>([]);
  const [gaps, setGaps] = useState<LearningSkillGap[]>([]);
  const [orgMap, setOrgMap] = useState<Awaited<ReturnType<typeof getOrgSkillMap>> | null>(null);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [attempts, setAttempts] = useState<AssessmentAttempt[]>([]);
  const [certs, setCerts] = useState<Certification[]>([]);
  const [earned, setEarned] = useState<EarnedCertification[]>([]);
  const [mentorProfile, setMentorProfile] = useState<MentorProfile | null>(null);
  const [mentors, setMentors] = useState<MentorMatch[]>([]);
  const [mentorRequests, setMentorRequests] = useState<MentorshipRequest[]>([]);
  const [careerPaths, setCareerPaths] = useState<CareerPath[]>([]);
  const [careerProgress, setCareerProgress] = useState<CareerProgress | null>(null);
  const [signals, setSignals] = useState<PromotionSignal[]>([]);
  const [academies, setAcademies] = useState<Academy[]>([]);
  const [myAcademyList, setMyAcademyList] = useState<Academy[]>([]);
  const [onboarding, setOnboarding] = useState<OnboardingPlan | null>(null);
  const [feed, setFeed] = useState<LearningRecommendationItem[]>([]);
  const [ai, setAi] = useState<AiLearningAnswer | null>(null);
  const [aiQuestion, setAiQuestion] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const loadAll = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    setError(null);
    try {
      const [
        profileRes,
        dash,
        coursesRes,
        enrollments,
        pathsRes,
        pathEnrollments,
        graphRes,
        gapsRes,
        orgMapRes,
        assessmentsRes,
        attemptsRes,
        certsRes,
        earnedRes,
        mentorProfileRes,
        mentorsRes,
        requestsRes,
        careerPathsRes,
        careerRes,
        signalsRes,
        academiesRes,
        myAcads,
        feedRes,
      ] = await Promise.allSettled([
        getLearningProfile(),
        getLearningDashboard(),
        listCourses({}),
        myCourseEnrollments(),
        listLearningPaths({}),
        myLearningPathEnrollments(),
        getMySkillGraph(),
        getMySkillGaps(),
        getOrgSkillMap(),
        listAssessments({}),
        myAssessmentAttempts(),
        listCertifications({}),
        myEarnedCertifications(),
        getMentorProfile(),
        listMentors({}),
        listMentorshipRequests("mentee"),
        listCareerPaths(),
        getMyCareerProgress(),
        listPromotionSignals("open"),
        listAcademies({}),
        myAcademies(),
        getLearningRecommendations(30),
      ]);
      const ok = <T,>(r: PromiseSettledResult<T>): T | null => (r.status === "fulfilled" ? r.value : null);
      setProfile(ok(profileRes));
      setDashboard(ok(dash));
      setCourses(ok(coursesRes) ?? []);
      setMyEnrollments(ok(enrollments) ?? []);
      setPaths(ok(pathsRes) ?? []);
      setMyPaths(ok(pathEnrollments) ?? []);
      setGraph(ok(graphRes) ?? []);
      setGaps(ok(gapsRes) ?? []);
      setOrgMap(ok(orgMapRes));
      setAssessments(ok(assessmentsRes) ?? []);
      setAttempts(ok(attemptsRes) ?? []);
      setCerts(ok(certsRes) ?? []);
      setEarned(ok(earnedRes) ?? []);
      setMentorProfile(ok(mentorProfileRes));
      setMentors(ok(mentorsRes) ?? []);
      setMentorRequests(ok(requestsRes) ?? []);
      setCareerPaths(ok(careerPathsRes) ?? []);
      setCareerProgress(ok(careerRes));
      setSignals(ok(signalsRes) ?? []);
      setAcademies(ok(academiesRes) ?? []);
      setMyAcademyList(ok(myAcads) ?? []);
      setFeed(ok(feedRes) ?? []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll(true);
  }, [loadAll]);

  const loadOnboarding = useCallback(async () => {
    try {
      const plans = await listOnboardingPlans("active");
      if (plans.length > 0) {
        const detail = await getOnboardingPlan(plans[0].id);
        setOnboarding(detail);
      } else {
        setOnboarding(null);
      }
    } catch {
      setOnboarding(null);
    }
  }, []);

  useEffect(() => {
    if (tab === "onboarding") loadOnboarding();
  }, [tab, loadOnboarding]);

  useEffect(() => {
    const t = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(t);
  }, [notice]);

  const run = async (fn: () => Promise<unknown>, okMessage: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(okMessage);
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const askAi = async () => {
    if (!aiQuestion.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await askLearningAi(aiQuestion);
      setAi(res);
      setAiQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Spinner label="Loading Learning Center" />;
  if (error && !dashboard && !courses.length) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <PageHeader title="Learning Center" description="Grow skills, earn certifications and advance your career." />
        <ErrorState message={error} onRetry={loadAll} />
      </div>
    );
  }

  const p = dashboard?.profile;
  const levelLabel = (n: number) => ["", "Beginner", "Developing", "Proficient", "Advanced", "Expert"][n] ?? "Expert";

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <PageHeader
        title="Learning Center"
        description="Your learning & growth operating system — courses, skills, certifications and career growth in one place."
        breadcrumb="Learning"
        actions={
          <div className="flex items-center gap-2">
            {canManage && <Badge tone="brand">Admin</Badge>}
            <Button variant="secondary" size="sm" loading={busy} onClick={() => loadAll()}>
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
        }
      />

      {error && !notice && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger/5 px-4 py-2.5 text-[13px] text-danger">{error}</div>
      )}
      {notice && (
        <div className="mb-4 rounded-lg border border-success/20 bg-success/5 px-4 py-2.5 text-[13px] text-success">{notice}</div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Learning Score" value={p?.learning_score ?? 0} hint={`Level: ${p?.level ?? "—"}`} icon={Brain} />
        <StatCard label="Courses Completed" value={p?.completed_courses ?? 0} hint={`${myEnrollments.filter((e) => e.status === "completed").length} in progress/completed`} icon={BookOpen} />
        <StatCard label="Certifications" value={p?.certifications ?? 0} hint={`${earned.filter((c) => c.status === "valid").length} valid`} icon={Trophy} />
        <StatCard label="Weekly Hours" value={p?.weekly_learning_hours ?? 0} hint={p?.career_stage ?? "Growth"} icon={Clock} />
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      <div className="mt-6">
        {tab === "overview" && <OverviewTab data={dashboard} feed={feed} history={history} profile={profile} onRefreshFeed={() => run(async () => { await refreshLearningRecommendations(); }, "Recommendations refreshed")} onAccept={(id) => run(async () => { await setLearningRecommendationStatus(id, "accepted"); }, "Recommendation accepted")} onDismiss={(id) => run(async () => { await setLearningRecommendationStatus(id, "dismissed"); }, "Recommendation dismissed")} />}
        {tab === "courses" && (
          <CoursesTab
            courses={courses}
            myEnrollments={myEnrollments}
            canManage={canManage}
            busy={busy}
            onEnroll={(id) => run(async () => { await enrollCourse(id); }, "Enrolled in course")}
            onRefresh={() => loadAll()}
          />
        )}
        {tab === "paths" && (
          <PathsTab paths={paths} myPaths={myPaths} busy={busy} onEnroll={(id) => run(async () => { await enrollLearningPath(id); }, "Enrolled in path")} />
        )}
        {tab === "skills" && (
          <SkillsTab graph={graph} gaps={gaps} orgMap={orgMap} busy={busy} onRefreshGaps={() => run(async () => { await refreshSkillGaps(); setGaps(await getMySkillGaps()); }, "Skill gap analysis complete")} onRefreshSnapshot={() => run(async () => { await refreshSkillSnapshot(); setOrgMap(await getOrgSkillMap()); }, "Org skill snapshot refreshed")} onCloseGap={(id) => run(async () => { await closeSkillGap(id); setGaps(await getMySkillGaps()); }, "Skill gap closed")} />
        )}
        {tab === "assessments" && (
          <AssessmentsTab assessments={assessments} attempts={attempts} busy={busy} onAssign={(id) => run(async () => { await assignAssessment(id); await loadAll(); }, "Assessment assigned")} />
        )}
        {tab === "certifications" && (
          <CertificationsTab certs={certs} earned={earned} busy={busy} onStart={(id) => run(async () => { await startCertificationAttempt(id); await loadAll(); }, "Certification attempt started")} />
        )}
        {tab === "mentorship" && (
          <MentorshipTab
            profile={mentorProfile}
            mentors={mentors}
            requests={mentorRequests}
            busy={busy}
            onSaveProfile={(payload) => run(async () => { await upsertMentorProfile(payload); setMentorProfile(await getMentorProfile()); }, "Mentor profile saved")}
            onRequest={(id, topic) => run(async () => { await requestMentorship(id, { topic }); await loadAll(); }, "Mentorship request sent")}
            onRespond={(id, accept) => run(async () => { await respondToMentorship(id, accept); await loadAll(); }, accept ? "Request accepted" : "Request declined")}
            onSession={(id) => run(async () => { await addMentorshipSession(id, { title: "1:1 session", kind: "session" }); await loadAll(); }, "Session logged")}
          />
        )}
        {tab === "career" && (
          <CareerTab paths={careerPaths} progress={careerProgress} signals={signals} busy={busy} onReview={(id, status) => run(async () => { await reviewPromotionSignal(id, status); setSignals(await listPromotionSignals("open")); }, "Signal reviewed")} onDetect={() => run(async () => { await detectPromotionSignal(); await loadAll(); }, "Promotion signal detected")} />
        )}
        {tab === "academies" && (
          <AcademiesTab academies={academies} myAcademies={myAcademyList} busy={busy} onJoin={(id) => run(async () => { await joinAcademy(id); setMyAcademyList(await myAcademies()); }, "Joined academy")} onLeave={(id) => run(async () => { await leaveAcademy(id); setMyAcademyList(await myAcademies()); }, "Left academy")} />
        )}
        {tab === "onboarding" && (
          <OnboardingTab
            plan={onboarding}
            busy={busy}
            onComplete={(taskId) => run(async () => { if (!onboarding) return; await completeOnboardingTask(onboarding.id, taskId); await loadOnboarding(); }, "Task completed")}
            onCreate={() => {
              const empId = profile?.employee_id;
              if (!empId) {
                setError("Could not determine your employee profile — create the plan from admin instead.");
                return;
              }
              run(async () => { await createOnboardingPlan(empId, 14); await loadOnboarding(); }, "Onboarding plan created");
            }}
          />
        )}
        {tab === "ai" && <AiTab answer={ai} question={aiQuestion} setQuestion={setAiQuestion} busy={busy} onAsk={askAi} />}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Overview

function OverviewTab({ data, feed, history, profile, onRefreshFeed, onAccept, onDismiss }: {
  data: LearningDashboard | null;
  feed: LearningRecommendationItem[];
  history: LearningHistoryEntry[];
  profile: { learning_score: number; level?: string } | null;
  onRefreshFeed: () => void;
  onAccept: (id: string) => void;
  onDismiss: (id: string) => void;
}) {
  if (!data) return <EmptyState title="No dashboard data yet" description="Enroll in a course or complete an assessment to see your learning overview." />;
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <Card title="My Courses" subtitle="Continue where you left off" actions={<Link href="/learning?tab=courses" className="btn-ghost btn-sm">View all</Link>}>
          {data.my_courses.length === 0 ? (
            <EmptyState title="No enrollments yet" description="Browse the course catalog and start your first course." action={<Link href="/learning?tab=courses" className="btn-primary btn-sm">Browse courses</Link>} />
          ) : (
            <div className="space-y-3">
              {data.my_courses.map((c) => (
                <Link key={c.enrollment_id} href={`/learning/courses/${c.id}`} className="block rounded-xl border border-line p-3.5 transition-colors hover:border-brand/40">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-ink">{c.title}</p>
                      <p className="mt-0.5 text-xs text-faint">{c.category ?? "General"} · {c.difficulty ?? "Any level"} · {c.duration_minutes ?? 0} min</p>
                    </div>
                    <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                  </div>
                  <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${c.progress}%` }} />
                  </div>
                  <p className="mt-1 text-[11px] text-faint">{c.progress}% complete</p>
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recommended for you" subtitle="Based on your skill gaps and goals">
          {data.recommended_courses.length === 0 ? (
            <EmptyState title="No recommendations yet" description="Complete your skill profile to get personalized course recommendations." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {data.recommended_courses.map((c) => (
                <Link key={c.id} href={`/learning/courses/${c.id}`} className="flex items-start justify-between gap-3 rounded-xl border border-line p-3.5 transition-colors hover:border-brand/40">
                  <div>
                    <p className="text-sm font-medium text-ink">{c.title}</p>
                    <p className="mt-0.5 text-xs text-faint">{c.category ?? "General"} · {c.difficulty ?? "Any level"}</p>
                  </div>
                  <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-faint" />
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recent activity" subtitle="Your learning history">
          {history.length === 0 ? (
            <EmptyState title="No activity yet" description="Completed courses, assessments and certifications will appear here." />
          ) : (
            <div className="space-y-2">
              {history.slice(0, 8).map((h) => (
                <div key={h.id} className="flex items-center justify-between gap-3 border-b border-line pb-2 last:border-0 last:pb-0">
                  <div className="flex items-center gap-2.5">
                    {h.kind === "course" ? <BookOpen className="h-4 w-4 text-brand" /> : h.kind === "certification" ? <Trophy className="h-4 w-4 text-brand" /> : <CheckCircle2 className="h-4 w-4 text-brand" />}
                    <div>
                      <p className="text-[13px] font-medium text-ink">{h.title}</p>
                      <p className="text-[11px] text-faint">{h.kind} · {new Date(h.occurred_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  {h.score != null && <Badge tone="brand">+{h.score}</Badge>}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-5">
        <Card title="AI Recommendations" actions={<button onClick={onRefreshFeed} className="btn-ghost btn-sm"><RefreshCw className="h-3.5 w-3.5" /> Refresh</button>}>
          {feed.length === 0 ? (
            <EmptyState title="No recommendations" description="Refresh to generate personalized learning recommendations." />
          ) : (
            <div className="space-y-3">
              {feed.map((r) => (
                <div key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-start justify-between gap-2">
                    <Badge tone={statusTone(r.kind)}>{r.kind}</Badge>
                    <span className="text-[11px] font-semibold text-brand">{Math.round(r.score * 100)}%</span>
                  </div>
                  <p className="mt-2 text-[13px] font-semibold text-ink">{r.title}</p>
                  {r.description && <p className="mt-1 text-xs text-faint line-clamp-2">{r.description}</p>}
                  {r.reason && <p className="mt-1.5 text-[11px] italic text-faint">{r.reason}</p>}
                  <div className="mt-2.5 flex gap-2">
                    {r.status === "pending" && (
                      <>
                        <Button size="sm" variant="primary" onClick={() => onAccept(r.id)}>Accept</Button>
                        <Button size="sm" variant="ghost" onClick={() => onDismiss(r.id)}>Dismiss</Button>
                      </>
                    )}
                    <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="My Paths" subtitle="Learning path progress">
          {data.learning_paths.length === 0 ? (
            <p className="text-[13px] text-faint">No active learning paths.</p>
          ) : (
            <div className="space-y-3">
              {data.learning_paths.map((lp) => (
                <Link key={lp.path_id} href={`/learning/paths/${lp.path_id}`} className="block rounded-xl border border-line p-3 transition-colors hover:border-brand/40">
                  <p className="text-[13px] font-medium text-ink">{lp.title ?? "Learning path"}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${lp.progress}%` }} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>

        <Card title="Skill Gaps" subtitle="Prioritized growth areas">
          {data.skill_gaps.length === 0 ? (
            <p className="text-[13px] text-faint">No skill gaps detected.</p>
          ) : (
            <div className="space-y-2">
              {data.skill_gaps.map((g, i) => (
                <div key={`${g.skill}-${i}`} className="flex items-center justify-between gap-2">
                  <span className="text-[13px] text-ink">{g.skill}</span>
                  <Badge tone={statusTone(g.priority)}>{g.priority}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Certificates" subtitle="Earned credentials">
          {data.certificates.length === 0 ? (
            <p className="text-[13px] text-faint">No certificates yet.</p>
          ) : (
            <div className="space-y-2">
              {data.certificates.slice(0, 5).map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-2">
                  <span className="text-[13px] text-ink">{c.name}</span>
                  <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        {data.mentor && (
          <Card title="Your Mentor">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-soft text-brand">
                <UserRound className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">{data.mentor.name}</p>
                <p className="text-xs text-faint">{data.mentor.designation ?? "Mentor"}</p>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Courses

function CoursesTab({ courses, myEnrollments, canManage, busy, onEnroll, onRefresh }: {
  courses: Course[];
  myEnrollments: Awaited<ReturnType<typeof myCourseEnrollments>>;
  canManage: boolean;
  busy: boolean;
  onEnroll: (id: string) => void;
  onRefresh: () => void;
}) {
  const enrolled = new Set(myEnrollments.map((e) => e.course_id));
  return (
    <div className="space-y-5">
      <Card title={`Course Catalog (${courses.length})`} subtitle={canManage ? "You can create and manage courses" : "Browse and enroll in courses"} actions={canManage ? <Button size="sm" variant="secondary" onClick={onRefresh}><RefreshCw className="h-3.5 w-3.5" /> Sync</Button> : undefined}>
        {courses.length === 0 ? (
          <EmptyState title="No courses yet" description="Courses will appear here once the learning catalog is populated." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {courses.map((c) => (
              <div key={c.id} className="flex flex-col rounded-xl border border-line p-4 transition-colors hover:border-brand/40">
                <div className="flex items-start justify-between gap-2">
                  <Badge tone={statusTone(c.category ?? "general")}>{c.category ?? "General"}</Badge>
                  <Badge tone="neutral">{c.difficulty ?? "Any"}</Badge>
                </div>
                <Link href={`/learning/courses/${c.id}`} className="mt-3 text-sm font-semibold text-ink hover:text-brand">{c.title}</Link>
                <p className="mt-1 line-clamp-2 text-xs text-faint">{c.description ?? "No description"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {c.skills.slice(0, 3).map((s) => <Badge key={s} tone="brand">{s}</Badge>)}
                  {c.skills.length > 3 && <Badge tone="neutral">+{c.skills.length - 3}</Badge>}
                </div>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="flex items-center gap-1 text-[11px] text-faint"><Clock className="h-3 w-3" /> {c.duration_minutes ?? 0} min</span>
                  {enrolled.has(c.id) ? (
                    <Badge tone="success">Enrolled</Badge>
                  ) : (
                    <Button size="sm" loading={busy} onClick={() => onEnroll(c.id)}>Enroll</Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="My Enrollments" subtitle="Track your progress">
        {myEnrollments.length === 0 ? (
          <EmptyState title="Nothing enrolled" description="Enroll in a course above to start learning." />
        ) : (
          <div className="space-y-3">
            {myEnrollments.map((e) => (
              <Link key={e.id} href={`/learning/courses/${e.course_id}`} className="block rounded-xl border border-line p-3.5 transition-colors hover:border-brand/40">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-ink">{e.title}</p>
                    <p className="mt-0.5 text-xs text-faint">Enrolled {new Date(e.enrolled_at).toLocaleDateString()}</p>
                  </div>
                  <Badge tone={statusTone(e.status)}>{e.status}</Badge>
                </div>
                <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${e.progress}%` }} />
                </div>
                <p className="mt-1 text-[11px] text-faint">{e.progress}% complete</p>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Paths

function PathsTab({ paths, myPaths, busy, onEnroll }: {
  paths: LearningPath[];
  myPaths: Awaited<ReturnType<typeof myLearningPathEnrollments>>;
  busy: boolean;
  onEnroll: (id: string) => void;
}) {
  const enrolled = new Set(myPaths.map((p) => p.path_id));
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {paths.length === 0 && (
        <div className="md:col-span-2 xl:col-span-3">
          <Card><EmptyState title="No learning paths" description="Curated learning paths will appear here — from individual contributor to leadership tracks." /></Card>
        </div>
      )}
      {paths.map((p) => (
        <div key={p.id} className="flex flex-col rounded-xl border border-line p-4 transition-colors hover:border-brand/40">
          <div className="flex items-start justify-between gap-2">
            <Badge tone={statusTone(p.difficulty ?? "general")}>{p.difficulty ?? "Any"}</Badge>
            <Badge tone="neutral">{p.step_count ?? 0} steps</Badge>
          </div>
          <Link href={`/learning/paths/${p.id}`} className="mt-3 text-sm font-semibold text-ink hover:text-brand">{p.title}</Link>
          <p className="mt-1 line-clamp-2 text-xs text-faint">{p.description ?? "No description"}</p>
          {p.target_role && <p className="mt-2 text-[11px] font-medium text-brand">→ {p.target_role}</p>}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {p.tags.slice(0, 4).map((t) => <Badge key={t} tone="neutral">{t}</Badge>)}
          </div>
          <div className="mt-auto flex items-center justify-between pt-4">
            <span className="text-[11px] text-faint">{p.estimated_days ?? 0} days est.</span>
            {enrolled.has(p.id) ? (
              <Badge tone="success">Enrolled</Badge>
            ) : (
              <Button size="sm" loading={busy} onClick={() => onEnroll(p.id)}>Start Path</Button>
            )}
          </div>
        </div>
      ))}
      {myPaths.length > 0 && (
        <div className="md:col-span-2 xl:col-span-3">
          <Card title="My Path Progress">
            <div className="space-y-3">
              {myPaths.map((mp) => (
                <div key={mp.id} className="flex items-center justify-between gap-4">
                  <div className="flex-1">
                    <p className="text-[13px] font-medium text-ink">{mp.title}</p>
                    <p className="text-[11px] text-faint">{mp.completed_step_ids.length} steps completed</p>
                  </div>
                  <div className="w-40">
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface">
                      <div className="h-full rounded-full bg-brand" style={{ width: `${mp.progress}%` }} />
                    </div>
                  </div>
                  <Badge tone={statusTone(mp.status)}>{mp.status}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Skills

function SkillsTab({ graph, gaps, orgMap, busy, onRefreshGaps, onRefreshSnapshot, onCloseGap }: {
  graph: SkillGraphEntry[];
  gaps: LearningSkillGap[];
  orgMap: Awaited<ReturnType<typeof getOrgSkillMap>> | null;
  busy: boolean;
  onRefreshGaps: () => void;
  onRefreshSnapshot: () => void;
  onCloseGap: (id: string) => void;
}) {
  const topSkills = [...graph].sort((a, b) => b.level - a.level).slice(0, 8);
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="My Skill Graph" subtitle="Verified skills from courses, assessments and experience" actions={<Button size="sm" variant="secondary" loading={busy} onClick={onRefreshSnapshot}><RefreshCw className="h-3.5 w-3.5" /> Refresh snapshot</Button>}>
        {graph.length === 0 ? (
          <EmptyState title="No skills yet" description="Complete courses and assessments to build your skill graph." />
        ) : (
          <div className="space-y-3">
            {topSkills.map((s) => (
              <div key={s.skill_id} className="flex items-center gap-3">
                <div className="w-36 shrink-0">
                  <p className="truncate text-[13px] font-medium text-ink">{s.name}</p>
                  <p className="text-[10px] text-faint">{s.category ?? "skill"}</p>
                </div>
                <div className="flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-surface">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${(s.level / 5) * 100}%` }} />
                  </div>
                </div>
                <div className="w-20 shrink-0 text-right">
                  <Badge tone={s.verified ? "success" : "neutral"}>{s.label}</Badge>
                </div>
              </div>
            ))}
            {graph.length > 8 && <p className="text-[11px] text-faint">+{graph.length - 8} more skills</p>}
          </div>
        )}
      </Card>

      <Card title="Skill Gaps" subtitle="Priority growth areas for your next role" actions={<Button size="sm" variant="secondary" loading={busy} onClick={onRefreshGaps}><RefreshCw className="h-3.5 w-3.5" /> Re-analyze</Button>}>
        {gaps.length === 0 ? (
          <EmptyState title="No gaps detected" description="Your skills are on track. Complete courses to keep it that way." />
        ) : (
          <div className="space-y-3">
            {gaps.map((g) => (
              <div key={g.id ?? `${g.skill_name}-${g.priority}`} className="rounded-xl border border-line p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-semibold text-ink">{g.skill_name}</p>
                  <Badge tone={statusTone(g.priority)}>{g.priority}</Badge>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-[11px] text-faint">You</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${(g.current_level / g.required_level) * 100}%` }} />
                  </div>
                  <span className="text-[11px] text-faint">Target {g.required_level}</span>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <p className="text-[11px] text-faint">{g.current_level} → {g.required_level} (gap {g.gap})</p>
                  <Button size="sm" variant="ghost" loading={busy} onClick={() => onCloseGap(g.id ?? g.skill_name)}>Close</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Organization Skill Map" subtitle="Company-wide skill coverage" className="lg:col-span-2">
        {!orgMap?.skills?.length ? (
          <EmptyState title="No organization snapshot" description="Refresh the snapshot to build the company skill map." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {orgMap.skills.slice(0, 12).map((s) => (
              <div key={s.name} className="rounded-xl border border-line p-3.5">
                <p className="text-[13px] font-medium text-ink">{s.name}</p>
                <p className="text-[11px] text-faint">{s.total_employees} people</p>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${(s.average_level / 5) * 100}%` }} />
                  </div>
                  <span className="text-[11px] font-medium text-brand">{s.average_level.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Assessments

function AssessmentsTab({ assessments, attempts, busy, onAssign }: {
  assessments: Assessment[];
  attempts: AssessmentAttempt[];
  busy: boolean;
  onAssign: (id: string) => void;
}) {
  return (
    <div className="space-y-5">
      <Card title="Assessments" subtitle="Measure and verify your skills">
        {assessments.length === 0 ? (
          <EmptyState title="No assessments" description="Assessments will appear here when the catalog is populated." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {assessments.map((a) => (
              <div key={a.id} className="flex flex-col rounded-xl border border-line p-4 transition-colors hover:border-brand/40">
                <div className="flex items-start justify-between gap-2">
                  <Badge tone="brand">{a.kind}</Badge>
                  <Badge tone="neutral">{a.difficulty ?? "Any"}</Badge>
                </div>
                <p className="mt-3 text-sm font-semibold text-ink">{a.title}</p>
                <p className="mt-1 line-clamp-2 text-xs text-faint">{a.description ?? "No description"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {a.skills.slice(0, 3).map((s) => <Badge key={s} tone="neutral">{s}</Badge>)}
                </div>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="text-[11px] text-faint">{a.question_count} questions · pass {a.passing_score}%</span>
                  <Button size="sm" loading={busy} onClick={() => onAssign(a.id)}>Assign to me</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="My Attempts" subtitle="Your assessment history">
        {attempts.length === 0 ? (
          <EmptyState title="No attempts" description="Assign an assessment above to get started." />
        ) : (
          <div className="space-y-2.5">
            {attempts.map((a) => (
              <div key={a.id} className="flex items-center justify-between gap-3 rounded-xl border border-line p-3.5">
                <div>
                  <p className="text-[13px] font-medium text-ink">{a.assessment_title ?? "Assessment"}</p>
                  <p className="text-[11px] text-faint">{a.kind ?? "—"} · submitted {a.submitted_at ? new Date(a.submitted_at).toLocaleDateString() : "not yet"}</p>
                </div>
                <div className="flex items-center gap-3">
                  {a.score != null && <Badge tone="brand">{a.score}%</Badge>}
                  {a.passed != null && <Badge tone={a.passed ? "success" : "danger"}>{a.passed ? "Passed" : "Failed"}</Badge>}
                  <Badge tone={statusTone(a.status)}>{a.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Certifications

function CertificationsTab({ certs, earned, busy, onStart }: {
  certs: Certification[];
  earned: EarnedCertification[];
  busy: boolean;
  onStart: (id: string) => void;
}) {
  return (
    <div className="space-y-5">
      <Card title="Certification Catalog" subtitle="Industry-recognized credentials">
        {certs.length === 0 ? (
          <EmptyState title="No certifications" description="Certification programs will appear here." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {certs.map((c) => (
              <div key={c.id} className="flex flex-col rounded-xl border border-line p-4 transition-colors hover:border-brand/40">
                <div className="flex items-start justify-between gap-2">
                  <Trophy className="h-4 w-4 text-brand" />
                  <Badge tone="neutral">{c.issuer ?? "Industry"}</Badge>
                </div>
                <p className="mt-3 text-sm font-semibold text-ink">{c.name}</p>
                <p className="mt-1 line-clamp-2 text-xs text-faint">{c.description ?? "No description"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {c.skills.slice(0, 3).map((s) => <Badge key={s} tone="neutral">{s}</Badge>)}
                </div>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="text-[11px] text-faint">Valid {c.validity_years ?? 0} yrs</span>
                  <Button size="sm" loading={busy} onClick={() => onStart(c.id)}>Start attempt</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="My Credentials" subtitle="Earned certifications">
        {earned.length === 0 ? (
          <EmptyState title="No credentials yet" description="Start a certification attempt above to earn your first credential." />
        ) : (
          <div className="space-y-2.5">
            {earned.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-3 rounded-xl border border-line p-3.5">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
                    <Trophy className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-[13px] font-medium text-ink">{c.name}</p>
                    <p className="text-[11px] text-faint">{c.issuer ?? "—"} · earned {c.earned_at ? new Date(c.earned_at).toLocaleDateString() : "—"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {c.expiry_date && <span className="text-[11px] text-faint">expires {new Date(c.expiry_date).toLocaleDateString()}</span>}
                  <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Mentorship

function MentorshipTab({ profile, mentors, requests, busy, onSaveProfile, onRequest, onRespond, onSession }: {
  profile: MentorProfile | null;
  mentors: MentorMatch[];
  requests: MentorshipRequest[];
  busy: boolean;
  onSaveProfile: (payload: Record<string, unknown>) => void;
  onRequest: (mentorId: string, topic: string) => void;
  onRespond: (id: string, accept: boolean) => void;
  onSession: (id: string) => void;
}) {
  const [topic, setTopic] = useState("");
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="My Mentor Profile" subtitle="Offer your guidance to others">
          {profile?.exists ? (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {profile.topics?.map((t) => <Badge key={t} tone="brand">{t}</Badge>)}
              </div>
              <p className="text-[13px] text-muted">{profile.bio ?? "No bio yet"}</p>
              <div className="flex flex-wrap gap-3 text-[12px] text-faint">
                <span>Availability: <b className="text-ink">{profile.availability}</b></span>
                <span>Max mentees: <b className="text-ink">{profile.max_mentees}</b></span>
                <Badge tone={profile.is_active ? "success" : "neutral"}>{profile.is_active ? "Active" : "Inactive"}</Badge>
              </div>
              <Button size="sm" variant="secondary" loading={busy} onClick={() => onSaveProfile({ is_active: !profile.is_active })}>
                {profile.is_active ? "Pause mentoring" : "Resume mentoring"}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-[13px] text-faint">You don't have a mentor profile yet. Create one to start helping colleagues grow.</p>
              <div className="flex gap-2">
                <Input placeholder="Topic (e.g. Leadership)" value={topic} onChange={(e) => setTopic(e.target.value)} className="flex-1" />
                <Button size="sm" loading={busy} onClick={() => onSaveProfile({ topics: [topic || "Leadership"], is_active: true })}>Create profile</Button>
              </div>
            </div>
          )}
        </Card>

        <Card title="Mentor Requests" subtitle="Pending mentorship requests">
          {requests.length === 0 ? (
            <EmptyState title="No requests" description="Requests you send and receive will appear here." />
          ) : (
            <div className="space-y-3">
              {requests.map((r) => (
                <div key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">{r.other_name ?? "Colleague"} · {r.topic}</p>
                    <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                  </div>
                  {r.goals?.length ? <p className="mt-1 text-xs text-faint line-clamp-1">{r.goals.join(", ")}</p> : null}
                  {r.status === "pending" && (
                    <div className="mt-2.5 flex gap-2">
                      <Button size="sm" loading={busy} onClick={() => onRespond(r.id, true)}>Accept</Button>
                      <Button size="sm" variant="ghost" loading={busy} onClick={() => onRespond(r.id, false)}>Decline</Button>
                    </div>
                  )}
                  {r.status === "active" && (
                    <Button size="sm" variant="secondary" className="mt-2.5" loading={busy} onClick={() => onSession(r.id)}>Log session</Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Find a Mentor" subtitle="Colleagues ready to guide you">
        {mentors.length === 0 ? (
          <EmptyState title="No mentors available" description="Colleagues who opt into mentoring will appear here." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {mentors.map((m) => (
              <div key={m.id} className="flex flex-col rounded-xl border border-line p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-soft text-brand">
                    <UserRound className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-[13px] font-semibold text-ink">{m.name}</p>
                    <p className="text-[11px] text-faint">{m.designation ?? "Mentor"}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {m.topics.slice(0, 3).map((t) => <Badge key={t} tone="brand">{t}</Badge>)}
                </div>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="text-[11px] text-faint">{m.active_mentees}/{m.max_mentees} mentees</span>
                  <Button size="sm" loading={busy} onClick={() => onRequest(m.id, m.topics[0] ?? "Career growth")}>Request</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Career

function CareerTab({ paths, progress, signals, busy, onReview, onDetect }: {
  paths: CareerPath[];
  progress: CareerProgress | null;
  signals: PromotionSignal[];
  busy: boolean;
  onReview: (id: string, status: string) => void;
  onDetect: () => void;
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="My Career Progress" subtitle="Your position on the career path" actions={<Button size="sm" variant="secondary" loading={busy} onClick={onDetect}>Detect promotion signal</Button>}>
          {progress ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-faint">Current</p>
                  <p className="text-sm font-semibold text-ink">{progress.current_role ?? progress.current?.title ?? "—"}</p>
                </div>
                <ArrowRight className="h-4 w-4 text-faint" />
                <div className="text-right">
                  <p className="text-[11px] uppercase tracking-wide text-faint">Next</p>
                  <p className="text-sm font-semibold text-brand">{progress.next_role ?? progress.next?.title ?? "—"}</p>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between text-[11px] text-faint">
                  <span>Readiness</span>
                  <span className="font-semibold text-ink">{progress.readiness}%</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${progress.readiness}%` }} />
                </div>
              </div>
              {progress.promotion_ready && <Badge tone="success">Promotion ready — talk to your manager</Badge>}
              <div className="space-y-2">
                {progress.evidence.map((ev, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2">
                    <div>
                      <p className="text-[12px] font-medium text-ink">{ev.label}</p>
                      <p className="text-[11px] text-faint">{ev.value}</p>
                    </div>
                    {ev.met ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Clock className="h-4 w-4 text-faint" />}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title="No career progress yet" description="Enroll in a career path to track your growth." />
          )}
        </Card>

        <Card title="Promotion Signals" subtitle="Evidence of readiness for review">
          {signals.length === 0 ? (
            <EmptyState title="No signals" description="Detect a promotion signal to start the conversation with your manager." />
          ) : (
            <div className="space-y-3">
              {signals.map((s) => (
                <div key={s.id ?? `${s.employee_id}-${s.score}`} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">{s.employee_name ?? "Employee"} {s.designation ? `· ${s.designation}` : ""}</p>
                    <Badge tone={s.score != null && s.score >= 70 ? "success" : "warning"}>{s.score != null ? `${s.score}%` : s.status}</Badge>
                  </div>
                  {s.target_role && <p className="mt-1 text-xs text-faint">Target: {s.target_role}</p>}
                  <div className="mt-2.5 flex gap-2">
                    <Button size="sm" variant="primary" loading={busy} onClick={() => onReview(s.id ?? "", "accepted")}>Approve</Button>
                    <Button size="sm" variant="ghost" loading={busy} onClick={() => onReview(s.id ?? "", "closed")}>Close</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Career Paths" subtitle="Explore structured career progression">
        {paths.length === 0 ? (
          <EmptyState title="No career paths" description="Career frameworks will appear here." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {paths.map((p) => (
              <Link key={p.id} href={`/learning/paths/${p.id}?career=1`} className="rounded-xl border border-line p-4 transition-colors hover:border-brand/40">
                <p className="text-sm font-semibold text-ink">{p.title}</p>
                <p className="mt-1 line-clamp-2 text-xs text-faint">{p.description ?? "No description"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {p.levels.slice(0, 3).map((l) => <Badge key={l} tone="neutral">{l}</Badge>)}
                </div>
                <p className="mt-3 text-[11px] text-faint">{p.step_count ?? 0} steps · {p.department ?? "All departments"}</p>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Academies

function AcademiesTab({ academies, myAcademies, busy, onJoin, onLeave }: {
  academies: Academy[];
  myAcademies: Academy[];
  busy: boolean;
  onJoin: (id: string) => void;
  onLeave: (id: string) => void;
}) {
  const joined = new Set(myAcademies.map((a) => a.id));
  return (
    <div className="space-y-5">
      <Card title={`Academies (${academies.length})`} subtitle="Specialized learning communities">
        {academies.length === 0 ? (
          <EmptyState title="No academies yet" description="Academies bring together courses, experts and learners around a discipline." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {academies.map((a) => (
              <div key={a.id} className="flex flex-col rounded-xl border border-line p-4 transition-colors hover:border-brand/40">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                    <GraduationCap className="h-5 w-5" />
                  </div>
                  <Badge tone="neutral">{a.category ?? "General"}</Badge>
                </div>
                <Link href={`/learning/academies/${a.id}`} className="mt-3 text-sm font-semibold text-ink hover:text-brand">{a.name}</Link>
                <p className="mt-1 line-clamp-2 text-xs text-faint">{a.description ?? "No description"}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(a.curriculum ?? []).slice(0, 3).map((c) => <Badge key={c} tone="neutral">{c}</Badge>)}
                </div>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="text-[11px] text-faint">{a.member_count ?? 0} members · {a.course_count ?? 0} courses</span>
                  {joined.has(a.id) ? (
                    <Button size="sm" variant="secondary" loading={busy} onClick={() => onLeave(a.id)}>Leave</Button>
                  ) : (
                    <Button size="sm" loading={busy} onClick={() => onJoin(a.id)}>Join</Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="My Academies" subtitle="Learning communities you've joined">
        {myAcademies.length === 0 ? (
          <EmptyState title="No memberships" description="Join an academy above to start participating." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {myAcademies.map((a) => (
              <Link key={a.id} href={`/learning/academies/${a.id}`} className="rounded-xl border border-line p-3.5 transition-colors hover:border-brand/40">
                <p className="text-[13px] font-medium text-ink">{a.name}</p>
                <p className="text-[11px] text-faint">{a.course_count ?? 0} courses · {a.member_count ?? 0} members</p>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ Onboarding

function OnboardingTab({ plan, busy, onComplete, onCreate }: {
  plan: OnboardingPlan | null;
  busy: boolean;
  onComplete: (taskId: string) => void;
  onCreate: () => void;
}) {
  if (!plan) {
    return (
      <Card title="Onboarding" subtitle="Your first 14 days at the company">
        <EmptyState
          title="No onboarding plan"
          description="Your onboarding plan is created automatically when you join. Ask your admin to create one."
          action={<Button loading={busy} onClick={onCreate}>Create my plan</Button>}
        />
      </Card>
    );
  }
  const tasks = plan.tasks ?? [];
  const done = tasks.filter((t) => t.completed).length;
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <Card title={plan.status === "completed" ? "Onboarding Complete" : `Onboarding · ${plan.status}`} subtitle="Welcome to the company" className="lg:col-span-1">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-soft text-brand">
            <Rocket className="h-8 w-8" />
          </div>
          <div>
            <p className="text-2xl font-semibold text-ink">{plan.progress}%</p>
            <p className="text-xs text-faint">{done} of {tasks.length} tasks done</p>
          </div>
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface">
          <div className="h-full rounded-full bg-brand" style={{ width: `${plan.progress}%` }} />
        </div>
        <div className="mt-4 space-y-1.5 text-[12px] text-faint">
          {plan.start_date && <p>Started {new Date(plan.start_date).toLocaleDateString()}</p>}
          {plan.target_date && <p>Target {new Date(plan.target_date).toLocaleDateString()}</p>}
          {plan.mentor_id && <p>Mentor assigned</p>}
        </div>
      </Card>
      <div className="lg:col-span-2">
        <Card title="Tasks" subtitle="Check off each step to complete onboarding">
          <div className="space-y-2.5">
            {tasks.map((t) => (
              <div key={t.id} className={`flex items-start justify-between gap-3 rounded-xl border p-3.5 ${t.completed ? "border-success/30 bg-success/5" : "border-line"}`}>
                <div className="flex items-start gap-3">
                  {t.completed ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  ) : (
                    <div className="mt-0.5 h-4 w-4 shrink-0 rounded-full border-2 border-line" />
                  )}
                  <div>
                    <p className="text-[13px] font-medium text-ink">{t.title}</p>
                    {t.description && <p className="mt-0.5 text-xs text-faint">{t.description}</p>}
                    <div className="mt-1.5 flex items-center gap-2">
                      <Badge tone="neutral">{t.category}</Badge>
                      <span className="text-[11px] text-faint">{t.kind}</span>
                    </div>
                  </div>
                </div>
                {!t.completed && (
                  <Button size="sm" loading={busy} onClick={() => onComplete(t.id)}>Complete</Button>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ AI Coach

function AiTab({ answer, question, setQuestion, busy, onAsk }: {
  answer: AiLearningAnswer | null;
  question: string;
  setQuestion: (q: string) => void;
  busy: boolean;
  onAsk: () => void;
}) {
  const suggestions = [
    "What should I learn next for my role?",
    "Which skills am I missing?",
    "What courses do you recommend?",
    "Am I ready for a promotion?",
    "Which certification should I pursue?",
  ];
  return (
    <div className="mx-auto max-w-3xl">
      <Card title="AI Learning Coach" subtitle="Ask anything about your learning, career and growth">
        <div className="flex gap-2">
          <Input placeholder="e.g. What skills should I build for a senior role?" value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onAsk()} className="flex-1" />
          <Button loading={busy} onClick={onAsk}><Send className="h-3.5 w-3.5" /> Ask</Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button key={s} onClick={() => setQuestion(s)} className="rounded-full border border-line px-3 py-1 text-[11px] text-faint transition-colors hover:border-brand/40 hover:text-brand">
              {s}
            </button>
          ))}
        </div>
      </Card>

      {answer && (
        <Card title={answer.intent} className="mt-5">
          <p className="whitespace-pre-line text-[13px] leading-relaxed text-ink">{answer.response ?? answer.answer ?? ""}</p>
          {answer.suggestions && answer.suggestions.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Suggestions</p>
              <ul className="mt-2 space-y-1.5">
                {answer.suggestions.map((s, i) => (
                  <li key={i} className="flex items-center gap-2 text-[13px] text-muted"><Lightbulb className="h-3.5 w-3.5 shrink-0 text-brand" /> {s}</li>
                ))}
              </ul>
            </div>
          )}
          {answer.gaps && answer.gaps.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Skill gaps</p>
              <div className="mt-2 space-y-2">
                {answer.gaps.map((g, i) => (
                  <div key={i} className="flex items-center gap-3 text-[13px]">
                    <span className="w-32 text-ink">{g.skill}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                      <div className="h-full rounded-full bg-brand" style={{ width: `${(g.current / g.required) * 100}%` }} />
                    </div>
                    <span className="text-[11px] text-faint">{g.current} → {g.required}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {answer.courses && answer.courses.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Recommended courses</p>
              <div className="mt-2 space-y-1.5">
                {answer.courses.map((c) => (
                  <Link key={c.id} href={`/learning/courses/${c.id}`} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-[13px] text-ink hover:border-brand/40">
                    <span>{c.title}</span>
                    <ArrowRight className="h-3.5 w-3.5 text-faint" />
                  </Link>
                ))}
              </div>
            </div>
          )}
          {answer.mentors && answer.mentors.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Mentors who can help</p>
              <div className="mt-2 space-y-1.5">
                {answer.mentors.map((m) => (
                  <div key={m.employee_id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-[13px]">
                    <span className="text-ink">{m.name}</span>
                    <span className="text-[11px] text-faint">{m.topics.join(", ")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {answer.readiness != null && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-[12px] text-faint">
                <span>Promotion readiness</span>
                <span className="font-semibold text-ink">{answer.readiness}%</span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface">
                <div className="h-full rounded-full bg-brand" style={{ width: `${answer.readiness}%` }} />
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
