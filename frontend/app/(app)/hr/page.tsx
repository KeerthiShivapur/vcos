"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Award,
  Banknote,
  BarChart3,
  Briefcase,
  Building2,
  CalendarClock,
  CalendarDays,
  ClipboardCheck,
  Clock,
  FileCheck2,
  HeartPulse,
  LayoutDashboard,
  Package,
  Plane,
  RefreshCw,
  Rocket,
  Send,
  Sparkles,
  Target,
  TrendingUp,
  UserRound,
  Users,
  Wrench,
} from "lucide-react";

import {
  addCandidate,
  addHoliday,
  addOffboardingTask,
  addSuccessionCandidate,
  approveLeaveRequest,
  askHrAi,
  assignAsset,
  cancelLeaveRequest,
  clockIn,
  clockOut,
  closeRecruitmentJob,
  completeInterview,
  completeOffboarding,
  completeOffboardingTask,
  completePerformanceReview,
  completeTraining,
  computeWorkforceSnapshot,
  createAsset,
  createLeaveType,
  createOffer,
  createPayrollProvider,
  createPayrollRun,
  createPerformanceCycle,
  createPerformanceGoal,
  createPerformanceReview,
  createRecruitmentJob,
  createShift,
  createTrainingRequirement,
  createWellbeingCheckIn,
  createWorkforcePlan,
  getComplianceOverview,
  getHrDashboard,
  getHiringNeeds,
  getPayrollOverview,
  getPerformanceSummary,
  getRecruitmentStats,
  getWellbeingOverview,
  getWorkforceAnalytics,
  listAlumni,
  listAssets,
  listAttendanceCorrections,
  listAttendanceRecords,
  listCandidates,
  listComplianceDocuments,
  listHolidays,
  listInterviews,
  listLeaveRequests,
  listLeaveTypes,
  listOffboardings,
  listOffers,
  listPayrollProviders,
  listPayrollRuns,
  listPerformanceCycles,
  listPerformanceGoals,
  listPerformanceReviews,
  listRecruitmentJobs,
  listShifts,
  listSuccessionCandidates,
  listTrainingCompletions,
  listTrainingRequirements,
  listWorkforcePlans,
  listWorkforceSnapshots,
  markAlumniBoomerang,
  markPayrollRunFailed,
  markPayrollRunSynced,
  myLeaveBalances,
  pendingLeaveRequests,
  recordComplianceDocument,
  recordManualAttendance,
  rejectLeaveRequest,
  renewComplianceDocument,
  requestLeave,
  reviewAttendanceCorrection,
  scheduleInterview,
  setCycleStatus,
  startOffboarding,
  submitExitInterview,
  submitPerformanceReview,
  updateAssetStatus,
  updateCandidate,
  updateGoalProgress,
  updateOfferStatus,
  updatePayrollProvider,
  updateWorkforcePlan,
  updateSuccessionCandidate,
  updateLeaveType,
} from "@/lib/api";
import type {
  Asset,
  AttendanceCorrection,
  AttendanceRecord,
  Candidate,
  ComplianceDocument,
  ComplianceOverview,
  HiringNeeds,
  Holiday,
  HrAiAnswer,
  HrDashboard,
  Interview,
  Job,
  LeaveBalance,
  LeaveRequestItem,
  LeaveSummary,
  LeaveType,
  Offer,
  OffboardingItem,
  PayrollOverview,
  PayrollProvider,
  PayrollRun,
  PerformanceCycle,
  PerformanceGoal,
  PerformanceReview,
  PerformanceSummary,
  RecruitmentStats,
  Shift,
  SuccessionCandidate,
  TrainingCompletion,
  TrainingRequirement,
  WellbeingOverview,
  WorkforceAnalytics,
  WorkforcePlan,
  WorkforceSnapshot,
} from "@/lib/api";
import type { EmployeeSummary } from "@/types";
import { listEmployees } from "@/lib/api";
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
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Table, Th, Td, Tr } from "@/components/ui/Table";

export default function HrPage() {
  return (
    <Suspense fallback={null}>
      <HrContent />
    </Suspense>
  );
}

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "attendance", label: "Attendance", icon: Clock },
  { id: "leave", label: "Leave", icon: Plane },
  { id: "hiring", label: "Hiring", icon: Briefcase },
  { id: "performance", label: "Performance", icon: Target },
  { id: "assets", label: "Assets", icon: Package },
  { id: "offboarding", label: "Offboarding", icon: Rocket },
  { id: "compliance", label: "Compliance", icon: FileCheck2 },
  { id: "workforce", label: "Workforce", icon: TrendingUp },
  { id: "wellbeing", label: "Wellbeing", icon: HeartPulse },
  { id: "payroll", label: "Payroll", icon: Banknote },
  { id: "ai", label: "HR AI", icon: Sparkles },
];

const fmtMin = (minutes?: number | null) => {
  if (!minutes) return "0h";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m > 0 ? `${m}m` : ""}`.trim() : `${m}m`;
};

const fmtMoney = (value?: number | null) =>
  value == null
    ? "—"
    : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function HrContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.HR_MANAGE);
  const canPayroll = roleCan(user?.role, PERMISSIONS.PAYROLL_MANAGE);

  const tab = searchParams.get("tab") ?? "overview";
  const setTab = (id: string) => router.replace(`/hr?tab=${id}`);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [dashboard, setDashboard] = useState<HrDashboard | null>(null);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);

  const [shifts, setShifts] = useState<Shift[]>([]);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [attendanceRecords, setAttendanceRecords] = useState<
    AttendanceRecord[]
  >([]);
  const [corrections, setCorrections] = useState<AttendanceCorrection[]>([]);

  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [leaveRequests, setLeaveRequests] = useState<LeaveRequestItem[]>([]);
  const [pendingLeave, setPendingLeave] = useState<LeaveRequestItem[]>([]);
  const [leaveSummary, setLeaveSummary] = useState<LeaveSummary | null>(null);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [recruitmentStats, setRecruitmentStats] =
    useState<RecruitmentStats | null>(null);

  const [cycles, setCycles] = useState<PerformanceCycle[]>([]);
  const [performanceGoals, setPerformanceGoals] = useState<PerformanceGoal[]>(
    [],
  );
  const [reviews, setReviews] = useState<PerformanceReview[]>([]);
  const [performanceSummary, setPerformanceSummary] =
    useState<PerformanceSummary | null>(null);

  const [assets, setAssets] = useState<Asset[]>([]);
  const [offboardings, setOffboardings] = useState<OffboardingItem[]>([]);
  const [alumni, setAlumni] = useState<Awaited<ReturnType<typeof listAlumni>>>(
    [],
  );

  const [complianceDocs, setComplianceDocs] = useState<ComplianceDocument[]>(
    [],
  );
  const [requirements, setRequirements] = useState<TrainingRequirement[]>([]);
  const [trainings, setTrainings] = useState<TrainingCompletion[]>([]);
  const [complianceOverview, setComplianceOverview] =
    useState<ComplianceOverview | null>(null);

  const [plans, setPlans] = useState<WorkforcePlan[]>([]);
  const [succession, setSuccession] = useState<SuccessionCandidate[]>([]);
  const [snapshots, setSnapshots] = useState<WorkforceSnapshot[]>([]);
  const [workforce, setWorkforce] = useState<WorkforceAnalytics | null>(null);
  const [hiringNeeds, setHiringNeeds] = useState<HiringNeeds | null>(null);

  const [wellbeing, setWellbeing] = useState<WellbeingOverview | null>(null);
  const [payrollOverview, setPayrollOverview] =
    useState<PayrollOverview | null>(null);
  const [providers, setProviders] = useState<PayrollProvider[]>([]);
  const [payrollRuns, setPayrollRuns] = useState<PayrollRun[]>([]);

  const [ai, setAi] = useState<HrAiAnswer | null>(null);
  const [aiQuestion, setAiQuestion] = useState("");

  const loadAll = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    setError(null);
    try {
      const [
        dash,
        employeesRes,
        shiftsRes,
        holidaysRes,
        attendanceRes,
        correctionsRes,
        leaveTypesRes,
        leaveRequestsRes,
        pendingRes,
        leaveSummaryRes,
        jobsRes,
        candidatesRes,
        interviewsRes,
        offersRes,
        recruitmentRes,
        cyclesRes,
        goalsRes,
        reviewsRes,
        performanceRes,
        assetsRes,
        offboardingsRes,
        alumniRes,
        docsRes,
        requirementsRes,
        trainingsRes,
        complianceRes,
        plansRes,
        successionRes,
        snapshotsRes,
        workforceRes,
        hiringRes,
        wellbeingRes,
        payrollRes,
        providersRes,
        runsRes,
      ] = await Promise.allSettled([
        getHrDashboard(),
        listEmployees({ page_size: 200 }),
        listShifts(),
        listHolidays(),
        listAttendanceRecords({ limit: 100 }),
        listAttendanceCorrections({}),
        listLeaveTypes(),
        listLeaveRequests({}),
        pendingLeaveRequests(),
        getHrDashboard().then((d) => d.leave),
        listRecruitmentJobs(),
        listCandidates({}),
        listInterviews({}),
        listOffers({}),
        getRecruitmentStats(),
        listPerformanceCycles(),
        listPerformanceGoals({}),
        listPerformanceReviews({}),
        getPerformanceSummary(),
        listAssets({}),
        listOffboardings(),
        listAlumni(),
        listComplianceDocuments({}),
        listTrainingRequirements(),
        listTrainingCompletions(),
        getComplianceOverview(),
        listWorkforcePlans(),
        listSuccessionCandidates(),
        listWorkforceSnapshots(),
        getWorkforceAnalytics(),
        getHiringNeeds(),
        getWellbeingOverview(),
        getPayrollOverview(),
        listPayrollProviders(),
        listPayrollRuns({}),
      ]);
      const ok = <T,>(r: PromiseSettledResult<T>): T | null =>
        r.status === "fulfilled" ? r.value : null;
      setDashboard(ok(dash));
      setEmployees(ok(employeesRes) ?? []);
      setShifts(ok(shiftsRes) ?? []);
      setHolidays(ok(holidaysRes) ?? []);
      setAttendanceRecords(ok(attendanceRes) ?? []);
      setCorrections(ok(correctionsRes) ?? []);
      setLeaveTypes(ok(leaveTypesRes) ?? []);
      setLeaveRequests(ok(leaveRequestsRes) ?? []);
      setPendingLeave(ok(pendingRes) ?? []);
      setLeaveSummary(ok(leaveSummaryRes));
      setJobs(ok(jobsRes) ?? []);
      setCandidates(ok(candidatesRes) ?? []);
      setInterviews(ok(interviewsRes) ?? []);
      setOffers(ok(offersRes) ?? []);
      setRecruitmentStats(ok(recruitmentRes));
      setCycles(ok(cyclesRes) ?? []);
      setPerformanceGoals(ok(goalsRes) ?? []);
      setReviews(ok(reviewsRes) ?? []);
      setPerformanceSummary(ok(performanceRes));
      setAssets(ok(assetsRes) ?? []);
      setOffboardings(ok(offboardingsRes) ?? []);
      setAlumni(ok(alumniRes) ?? []);
      setComplianceDocs(ok(docsRes) ?? []);
      setRequirements(ok(requirementsRes) ?? []);
      setTrainings(ok(trainingsRes) ?? []);
      setComplianceOverview(ok(complianceRes));
      setPlans(ok(plansRes) ?? []);
      setSuccession(ok(successionRes) ?? []);
      setSnapshots(ok(snapshotsRes) ?? []);
      setWorkforce(ok(workforceRes));
      setHiringNeeds(ok(hiringRes));
      setWellbeing(ok(wellbeingRes));
      setPayrollOverview(ok(payrollRes));
      setProviders(ok(providersRes) ?? []);
      setPayrollRuns(ok(runsRes) ?? []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll(true);
  }, [loadAll]);

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
      const res = await askHrAi(aiQuestion);
      setAi(res);
      setAiQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Spinner label="Loading People Operations" />;
  if (error && !dashboard) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <PageHeader
          title="People Operations"
          description="HR & workforce operating system — attendance, leave, hiring, performance and more."
        />
        <ErrorState message={error} onRetry={loadAll} />
      </div>
    );
  }

  const empOptions = employees.map((e) => ({
    value: e.id,
    label: e.full_name,
  }));
  const jobOptions = jobs.map((j) => ({ value: j.id, label: j.title }));
  const leaveTypeOptions = leaveTypes.map((t) => ({
    value: t.id,
    label: `${t.name} (${t.code})`,
  }));

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <PageHeader
        title="People Operations"
        description="Your HR & workforce operating system — attendance, leave, hiring, performance, compliance and payroll in one place."
        breadcrumb="HR"
        actions={
          <div className="flex items-center gap-2">
            {canManage && <Badge tone="brand">Admin</Badge>}
            <Button
              variant="secondary"
              size="sm"
              loading={busy}
              onClick={() => loadAll()}
            >
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
        }
      />

      {error && !notice && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger/5 px-4 py-2.5 text-[13px] text-danger">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 rounded-lg border border-success/20 bg-success/5 px-4 py-2.5 text-[13px] text-success">
          {notice}
        </div>
      )}

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      <div className="mt-6">
        {tab === "overview" && <OverviewTab data={dashboard} />}
        {tab === "attendance" && (
          <AttendanceTab
            shifts={shifts}
            holidays={holidays}
            records={attendanceRecords}
            corrections={corrections}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onClockIn={(payload) =>
              run(async () => {
                await clockIn(payload);
              }, "Clocked in")
            }
            onClockOut={() =>
              run(async () => {
                await clockOut();
              }, "Clocked out")
            }
            onManual={(payload) =>
              run(async () => {
                await recordManualAttendance(payload);
              }, "Manual record added")
            }
            onAddShift={(payload) =>
              run(async () => {
                await createShift(payload);
              }, "Shift created")
            }
            onAddHoliday={(payload) =>
              run(async () => {
                await addHoliday(payload);
              }, "Holiday added")
            }
            onReviewCorrection={(id, decision) =>
              run(async () => {
                await reviewAttendanceCorrection(id, decision);
              }, `Correction ${decision}d`)
            }
          />
        )}
        {tab === "leave" && (
          <LeaveTab
            types={leaveTypes}
            balances={myBalances}
            requests={leaveRequests}
            pending={pendingLeave}
            summary={leaveSummary}
            leaveTypeOptions={leaveTypeOptions}
            canManage={canManage}
            busy={busy}
            onRequest={(payload) =>
              run(async () => {
                await requestLeave(payload);
              }, "Leave requested")
            }
            onApprove={(id, note) =>
              run(async () => {
                await approveLeaveRequest(id, note);
              }, "Leave approved")
            }
            onReject={(id, note) =>
              run(async () => {
                await rejectLeaveRequest(id, note);
              }, "Leave rejected")
            }
            onCancel={(id) =>
              run(async () => {
                await cancelLeaveRequest(id);
              }, "Leave cancelled")
            }
            onCreateType={(payload) =>
              run(async () => {
                await createLeaveType(payload);
              }, "Leave type created")
            }
            onToggleType={(id, active) =>
              run(async () => {
                await updateLeaveType(id, { is_active: active });
              }, "Leave type updated")
            }
          />
        )}
        {tab === "hiring" && (
          <HiringTab
            stats={recruitmentStats}
            jobs={jobs}
            candidates={candidates}
            interviews={interviews}
            offers={offers}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onJob={(payload) =>
              run(async () => {
                await createRecruitmentJob(payload);
              }, "Job created")
            }
            onCloseJob={(id) =>
              run(async () => {
                await closeRecruitmentJob(id);
              }, "Job closed")
            }
            onCandidate={(payload) =>
              run(async () => {
                await addCandidate(payload);
              }, "Candidate added")
            }
            onStage={(id, stage) =>
              run(async () => {
                await updateCandidate(id, { stage });
              }, "Stage updated")
            }
            onInterview={(payload) =>
              run(async () => {
                await scheduleInterview(payload);
              }, "Interview scheduled")
            }
            onCompleteInterview={(id, payload) =>
              run(async () => {
                await completeInterview(id, payload);
              }, "Interview completed")
            }
            onOffer={(payload) =>
              run(async () => {
                await createOffer(payload);
              }, "Offer created")
            }
            onOfferStatus={(id, status) =>
              run(async () => {
                await updateOfferStatus(id, status);
              }, `Offer ${status}`)
            }
          />
        )}
        {tab === "performance" && (
          <PerformanceTab
            summary={performanceSummary}
            cycles={cycles}
            goals={performanceGoals}
            reviews={reviews}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onCycle={(payload) =>
              run(async () => {
                await createPerformanceCycle(payload);
              }, "Cycle created")
            }
            onCycleStatus={(id, status) =>
              run(async () => {
                await setCycleStatus(id, status);
              }, "Cycle updated")
            }
            onGoal={(payload) =>
              run(async () => {
                await createPerformanceGoal(payload);
              }, "Goal created")
            }
            onProgress={(id, progress) =>
              run(async () => {
                await updateGoalProgress(id, progress);
              }, "Progress updated")
            }
            onReview={(payload) =>
              run(async () => {
                await createPerformanceReview(payload);
              }, "Review created")
            }
            onSubmit={(id) =>
              run(async () => {
                await submitPerformanceReview(id, {});
              }, "Review submitted")
            }
            onComplete={(id) =>
              run(async () => {
                await completePerformanceReview(id);
              }, "Review completed")
            }
          />
        )}
        {tab === "assets" && (
          <AssetsTab
            assets={assets}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onCreate={(payload) =>
              run(async () => {
                await createAsset(payload);
              }, "Asset created")
            }
            onAssign={(id, employeeId) =>
              run(async () => {
                await assignAsset(id, employeeId);
              }, "Asset assigned")
            }
            onStatus={(id, status) =>
              run(async () => {
                await updateAssetStatus(id, status);
              }, "Asset status updated")
            }
          />
        )}
        {tab === "offboarding" && (
          <OffboardingTab
            offboardings={offboardings}
            alumni={alumni}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onStart={(payload) =>
              run(async () => {
                await startOffboarding(payload);
              }, "Offboarding started")
            }
            onTask={(id, payload) =>
              run(async () => {
                await addOffboardingTask(id, payload);
              }, "Task added")
            }
            onCompleteTask={(id, taskId) =>
              run(async () => {
                await completeOffboardingTask(id, taskId);
              }, "Task completed")
            }
            onExitInterview={(id, payload) =>
              run(async () => {
                await submitExitInterview(id, payload);
              }, "Exit interview saved")
            }
            onComplete={(id) =>
              run(async () => {
                await completeOffboarding(id);
              }, "Offboarding completed")
            }
            onBoomerang={(id) =>
              run(async () => {
                await markAlumniBoomerang(id);
              }, "Marked as boomerang")
            }
          />
        )}
        {tab === "compliance" && (
          <ComplianceTab
            overview={complianceOverview}
            documents={complianceDocs}
            requirements={requirements}
            trainings={trainings}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onDocument={(payload) =>
              run(async () => {
                await recordComplianceDocument(payload);
              }, "Document recorded")
            }
            onRenew={(id, payload) =>
              run(async () => {
                await renewComplianceDocument(id, payload);
              }, "Document renewed")
            }
            onRequirement={(payload) =>
              run(async () => {
                await createTrainingRequirement(payload);
              }, "Requirement created")
            }
            onTraining={(payload) =>
              run(async () => {
                await completeTraining(payload);
              }, "Training completion recorded")
            }
          />
        )}
        {tab === "workforce" && (
          <WorkforceTab
            analytics={workforce}
            plans={plans}
            succession={succession}
            snapshots={snapshots}
            hiringNeeds={hiringNeeds}
            employees={empOptions}
            canManage={canManage}
            busy={busy}
            onPlan={(payload) =>
              run(async () => {
                await createWorkforcePlan(payload);
              }, "Plan created")
            }
            onPlanStatus={(id, status) =>
              run(async () => {
                await updateWorkforcePlan(id, { status });
              }, "Plan updated")
            }
            onCandidate={(payload) =>
              run(async () => {
                await addSuccessionCandidate(payload);
              }, "Candidate added")
            }
            onReadiness={(id, readiness) =>
              run(async () => {
                await updateSuccessionCandidate(id, { readiness });
              }, "Readiness updated")
            }
            onSnapshot={() =>
              run(async () => {
                await computeWorkforceSnapshot();
              }, "Snapshot computed")
            }
          />
        )}
        {tab === "wellbeing" && (
          <WellbeingTab
            overview={wellbeing}
            busy={busy}
            onCheckIn={(payload) =>
              run(async () => {
                await createWellbeingCheckIn(payload);
              }, "Check-in recorded")
            }
          />
        )}
        {tab === "payroll" && (
          <PayrollTab
            overview={payrollOverview}
            providers={providers}
            runs={payrollRuns}
            canManage={canPayroll}
            busy={busy}
            onProvider={(payload) =>
              run(async () => {
                await createPayrollProvider(payload);
              }, "Provider created")
            }
            onToggleProvider={(id, active) =>
              run(async () => {
                await updatePayrollProvider(id, { is_active: active });
              }, "Provider updated")
            }
            onRun={(payload) =>
              run(async () => {
                await createPayrollRun(payload);
              }, "Run recorded")
            }
            onSynced={(id, ref) =>
              run(async () => {
                await markPayrollRunSynced(id, ref);
              }, "Run marked synced")
            }
            onFailed={(id) =>
              run(async () => {
                await markPayrollRunFailed(id);
              }, "Run marked failed")
            }
          />
        )}
        {tab === "ai" && (
          <AiTab
            answer={ai}
            question={aiQuestion}
            setQuestion={setAiQuestion}
            busy={busy}
            onAsk={askAi}
          />
        )}
      </div>
    </div>
  );
}

// Re-exported convenience (balances fetched lazily per render)
const myBalances: LeaveBalance[] = [];

// ------------------------------------------------------------------ Overview

function OverviewTab({ data }: { data: HrDashboard | null }) {
  if (!data)
    return (
      <EmptyState
        title="No data yet"
        description="People operations metrics will appear here once HR data is available."
      />
    );
  const w = data.workforce;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Headcount"
          value={w.headcount}
          hint={`${w.hires_month} hires · ${w.exits_month} exits this month`}
          icon={Users}
        />
        <StatCard
          label="Open Positions"
          value={data.recruitment.open_positions}
          hint={`${data.recruitment.open_jobs} open jobs`}
          icon={Briefcase}
        />
        <StatCard
          label="Pending Leave"
          value={data.leave.pending_count}
          hint={`${data.leave.approved_count} approved`}
          icon={Plane}
        />
        <StatCard
          label="Attrition"
          value={`${w.attrition_rate}%`}
          hint={
            w.hiring_needs.attrition_pressure
              ? "Attrition pressure detected"
              : "Monthly rate"
          }
          icon={TrendingUp}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card
            title="Workforce Trend"
            subtitle="Headcount over the last snapshots"
          >
            {w.trend.length === 0 ? (
              <EmptyState
                title="No snapshots yet"
                description="Compute a snapshot from the Workforce tab to see the trend."
              />
            ) : (
              <div className="flex h-40 items-end gap-3">
                {w.trend.map((t) => (
                  <div
                    key={t.date}
                    className="flex flex-1 flex-col items-center gap-1"
                  >
                    <span className="text-[10px] font-medium text-ink">
                      {t.headcount}
                    </span>
                    <div
                      className="w-full rounded-t-md bg-brand"
                      style={{
                        height: `${Math.max(6, (t.headcount / Math.max(...w.trend.map((x) => x.headcount))) * 110)}px`,
                      }}
                    />
                    <span className="text-[10px] text-faint">
                      {new Date(t.date).toLocaleDateString(undefined, {
                        month: "short",
                      })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card
            title="Pending Approvals"
            subtitle="Leave requests awaiting review"
          >
            {data.leave.pending_count === 0 ? (
              <EmptyState
                title="Nothing pending"
                description="No leave requests are waiting for approval."
              />
            ) : (
              <div className="space-y-2.5">
                {data.leave.per_type.length === 0 && (
                  <p className="text-[13px] text-faint">No requests yet.</p>
                )}
              </div>
            )}
            {data.offboarding.list.length > 0 && (
              <div className="mt-4 border-t border-line pt-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                  Active offboardings
                </p>
                {data.offboarding.list.map((o) => (
                  <div
                    key={o.id}
                    className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                  >
                    <div>
                      <p className="text-[13px] font-medium text-ink">
                        {o.employee_name}
                      </p>
                      <p className="text-[11px] text-faint">
                        {o.reason ?? "—"}
                      </p>
                    </div>
                    <Badge tone={statusTone(o.status)}>{o.status}</Badge>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Hiring Funnel" subtitle="Candidates by stage">
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.recruitment.candidates_by_stage).length ===
              0 ? (
                <p className="text-[13px] text-faint">No candidates yet.</p>
              ) : (
                Object.entries(data.recruitment.candidates_by_stage).map(
                  ([stage, count]) => (
                    <div
                      key={stage}
                      className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5"
                    >
                      <span className="text-[12px] text-faint">{stage}</span>
                      <Badge tone="brand">{count}</Badge>
                    </div>
                  ),
                )
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card title="Compliance Health" subtitle="Documents & trainings">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">
                  Expired documents
                </span>
                <Badge
                  tone={
                    data.compliance.expired_documents ? "danger" : "success"
                  }
                >
                  {data.compliance.expired_documents}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">
                  Expiring in 30 days
                </span>
                <Badge
                  tone={data.compliance.expiring_30 ? "warning" : "neutral"}
                >
                  {data.compliance.expiring_30}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">
                  Missing trainings
                </span>
                <Badge
                  tone={
                    data.compliance.missing_trainings ? "warning" : "neutral"
                  }
                >
                  {data.compliance.missing_trainings}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Total documents</span>
                <Badge tone="brand">{data.compliance.total_documents}</Badge>
              </div>
            </div>
          </Card>

          <Card title="Performance" subtitle="Current cycle health">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">
                  Reviews completed
                </span>
                <Badge tone="brand">
                  {data.performance.reviews.completed}/
                  {data.performance.reviews.total}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Average rating</span>
                <Badge
                  tone={
                    data.performance.reviews.average_rating >= 4
                      ? "success"
                      : "neutral"
                  }
                >
                  {data.performance.reviews.average_rating || "—"}/5
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Open cycles</span>
                <Badge tone="neutral">{data.performance.cycles.open}</Badge>
              </div>
            </div>
          </Card>

          <Card title="Wellbeing" subtitle="Workload risk overview">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">
                  At-risk employees
                </span>
                <Badge
                  tone={data.wellbeing.at_risk_employees ? "danger" : "success"}
                >
                  {data.wellbeing.at_risk_employees}
                </Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">High risk checks</span>
                <Badge tone="danger">{data.wellbeing.high}</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Total check-ins</span>
                <Badge tone="neutral">{data.wellbeing.total_checks}</Badge>
              </div>
            </div>
          </Card>

          <Card title="Payroll" subtitle="External provider reference">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Active providers</span>
                <Badge tone="brand">{data.payroll.active_providers}</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Synced runs</span>
                <Badge tone="success">{data.payroll.runs.synced}</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-muted">Pending runs</span>
                <Badge tone="warning">{data.payroll.runs.pending}</Badge>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Attendance

function AttendanceTab({
  shifts,
  holidays,
  records,
  corrections,
  employees,
  canManage,
  busy,
  onClockIn,
  onClockOut,
  onManual,
  onAddShift,
  onAddHoliday,
  onReviewCorrection,
}: {
  shifts: Shift[];
  holidays: Holiday[];
  records: AttendanceRecord[];
  corrections: AttendanceCorrection[];
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onClockIn: (payload: Record<string, unknown>) => void;
  onClockOut: () => void;
  onManual: (payload: Record<string, unknown>) => void;
  onAddShift: (payload: Record<string, unknown>) => void;
  onAddHoliday: (payload: Record<string, unknown>) => void;
  onReviewCorrection: (id: string, decision: string) => void;
}) {
  const [showClock, setShowClock] = useState(false);
  const [clockWorkMode, setClockWorkMode] = useState("office");
  const [showManual, setShowManual] = useState(false);
  const [showShift, setShowShift] = useState(false);
  const [showHoliday, setShowHoliday] = useState(false);
  const [manual, setManual] = useState<Record<string, string>>({});
  const [shift, setShift] = useState<Record<string, string>>({});
  const [holiday, setHoliday] = useState<Record<string, string>>({});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={() => setShowClock(true)}>
          <Clock className="h-3.5 w-3.5" /> Clock in
        </Button>
        <Button variant="secondary" loading={busy} onClick={onClockOut}>
          Clock out
        </Button>
        {canManage && (
          <>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowManual(true)}
            >
              Manual record
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowShift(true)}
            >
              Add shift
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowHoliday(true)}
            >
              Add holiday
            </Button>
          </>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Today's Records"
          subtitle="Latest attendance across the org"
        >
          {records.length === 0 ? (
            <EmptyState
              title="No records"
              description="Clock in or add a manual record to get started."
            />
          ) : (
            <div className="space-y-2.5">
              {records.slice(0, 10).map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">
                      {new Date(r.date).toLocaleDateString()} · {r.work_mode}
                    </p>
                    <p className="text-[11px] text-faint">
                      {r.check_in
                        ? new Date(r.check_in).toLocaleTimeString()
                        : "—"}{" "}
                      →{" "}
                      {r.check_out
                        ? new Date(r.check_out).toLocaleTimeString()
                        : "open"}{" "}
                      · {fmtMin(r.work_minutes)}
                    </p>
                  </div>
                  <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Corrections" subtitle="Pending attendance corrections">
          {corrections.length === 0 ? (
            <EmptyState
              title="No corrections"
              description="Correction requests will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {corrections.map((c) => (
                <div key={c.id} className="rounded-xl border border-line p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">
                      {new Date(c.requested_date).toLocaleDateString()}
                    </p>
                    <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-faint">
                    {c.reason ?? "No reason"}
                  </p>
                  {c.status === "pending" && canManage && (
                    <div className="mt-2 flex gap-2">
                      <Button
                        size="sm"
                        loading={busy}
                        onClick={() => onReviewCorrection(c.id, "approve")}
                      >
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onReviewCorrection(c.id, "reject")}
                      >
                        Reject
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Shifts" subtitle="Configured shifts">
          {shifts.length === 0 ? (
            <EmptyState
              title="No shifts"
              description="Create shifts to structure attendance."
            />
          ) : (
            <div className="space-y-2.5">
              {shifts.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">{s.name}</p>
                    <p className="text-[11px] text-faint">
                      {s.start_time} → {s.end_time} · {s.work_hours}h ·{" "}
                      {s.days.join(", ") || "flexible"}
                    </p>
                  </div>
                  <Badge tone={s.is_active ? "success" : "neutral"}>
                    {s.is_active ? "Active" : "Inactive"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Holidays" subtitle="Company holidays & observances">
          {holidays.length === 0 ? (
            <EmptyState
              title="No holidays"
              description="Add holidays to keep leave calendars accurate."
            />
          ) : (
            <div className="space-y-2.5">
              {holidays.map((h) => (
                <div
                  key={h.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">{h.name}</p>
                    <p className="text-[11px] text-faint">
                      {new Date(h.date).toLocaleDateString()} · {h.kind}
                      {h.optional ? " · optional" : ""}
                    </p>
                  </div>
                  <Badge tone={h.optional ? "neutral" : "brand"}>
                    {h.optional ? "Optional" : "Observed"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={showClock}
        onClose={() => setShowClock(false)}
        title="Clock in"
        description="Record your attendance"
      >
        <div className="space-y-3">
          <Select
            label="Work mode"
            options={[
              { value: "office", label: "Office" },
              { value: "remote", label: "Remote" },
              { value: "work_from_home", label: "Work from home" },
            ]}
            value={clockWorkMode}
            onChange={(e) => setClockWorkMode(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowClock(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onClockIn({ work_mode: clockWorkMode });
                setShowClock(false);
              }}
            >
              Clock in
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showManual}
        onClose={() => setShowManual(false)}
        title="Manual attendance record"
      >
        <div className="space-y-3">
          <Select
            label="Employee"
            options={employees}
            value={manual.employee_id ?? ""}
            onChange={(e) =>
              setManual({ ...manual, employee_id: e.target.value })
            }
          />
          <Input
            label="Date"
            type="date"
            value={manual.date ?? ""}
            onChange={(e) => setManual({ ...manual, date: e.target.value })}
          />
          <Select
            label="Status"
            options={[
              { value: "present", label: "Present" },
              { value: "work_from_home", label: "Work from home" },
              { value: "late", label: "Late" },
              { value: "absent", label: "Absent" },
              { value: "leave", label: "Leave" },
              { value: "half_day", label: "Half day" },
            ]}
            value={manual.status ?? ""}
            onChange={(e) => setManual({ ...manual, status: e.target.value })}
          />
          <Input
            label="Check-in time"
            type="time"
            value={manual.check_in ?? ""}
            onChange={(e) => setManual({ ...manual, check_in: e.target.value })}
          />
          <Input
            label="Check-out time"
            type="time"
            value={manual.check_out ?? ""}
            onChange={(e) =>
              setManual({ ...manual, check_out: e.target.value })
            }
          />
          <Textarea
            label="Note"
            value={manual.note ?? ""}
            onChange={(e) => setManual({ ...manual, note: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowManual(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onManual(manual);
                setShowManual(false);
                setManual({});
              }}
            >
              Save record
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showShift}
        onClose={() => setShowShift(false)}
        title="Create shift"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={shift.name ?? ""}
            onChange={(e) => setShift({ ...shift, name: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Start time"
              type="time"
              value={shift.start_time ?? ""}
              onChange={(e) =>
                setShift({ ...shift, start_time: e.target.value })
              }
            />
            <Input
              label="End time"
              type="time"
              value={shift.end_time ?? ""}
              onChange={(e) => setShift({ ...shift, end_time: e.target.value })}
            />
          </div>
          <Input
            label="Work hours"
            type="number"
            value={shift.work_hours ?? ""}
            onChange={(e) => setShift({ ...shift, work_hours: e.target.value })}
          />
          <Input
            label="Break minutes"
            type="number"
            value={shift.break_minutes ?? ""}
            onChange={(e) =>
              setShift({ ...shift, break_minutes: e.target.value })
            }
          />
          <Input
            label="Days (comma separated, e.g. Mon,Tue)"
            value={shift.days ?? ""}
            onChange={(e) => setShift({ ...shift, days: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowShift(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onAddShift({
                  ...shift,
                  days: (shift.days ?? "")
                    .split(",")
                    .map((d) => d.trim())
                    .filter(Boolean),
                });
                setShowShift(false);
                setShift({});
              }}
            >
              Create shift
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showHoliday}
        onClose={() => setShowHoliday(false)}
        title="Add holiday"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={holiday.name ?? ""}
            onChange={(e) => setHoliday({ ...holiday, name: e.target.value })}
          />
          <Input
            label="Date"
            type="date"
            value={holiday.date ?? ""}
            onChange={(e) => setHoliday({ ...holiday, date: e.target.value })}
          />
          <Select
            label="Kind"
            options={[
              { value: "national", label: "National" },
              { value: "company", label: "Company" },
              { value: "regional", label: "Regional" },
            ]}
            value={holiday.kind ?? ""}
            onChange={(e) => setHoliday({ ...holiday, kind: e.target.value })}
          />
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={holiday.optional === "true"}
              onChange={(e) =>
                setHoliday({ ...holiday, optional: String(e.target.checked) })
              }
            />
            <span className="text-[13px] text-muted">Optional holiday</span>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowHoliday(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onAddHoliday({
                  ...holiday,
                  optional: holiday.optional === "true",
                });
                setShowHoliday(false);
                setHoliday({});
              }}
            >
              Add holiday
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Leave

function LeaveTab({
  types,
  balances,
  requests,
  pending,
  summary,
  leaveTypeOptions,
  canManage,
  busy,
  onRequest,
  onApprove,
  onReject,
  onCancel,
  onCreateType,
  onToggleType,
}: {
  types: LeaveType[];
  balances: LeaveBalance[];
  requests: LeaveRequestItem[];
  pending: LeaveRequestItem[];
  summary: LeaveSummary | null;
  leaveTypeOptions: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onRequest: (payload: Record<string, unknown>) => void;
  onApprove: (id: string, note?: string) => void;
  onReject: (id: string, note?: string) => void;
  onCancel: (id: string) => void;
  onCreateType: (payload: Record<string, unknown>) => void;
  onToggleType: (id: string, active: boolean) => void;
}) {
  const [showRequest, setShowRequest] = useState(false);
  const [showType, setShowType] = useState(false);
  const [req, setReq] = useState<Record<string, string>>({});
  const [type, setType] = useState<Record<string, string>>({});

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        <Button loading={busy} onClick={() => setShowRequest(true)}>
          <Plane className="h-3.5 w-3.5" /> Request leave
        </Button>
        {canManage && (
          <Button
            variant="secondary"
            loading={busy}
            onClick={() => setShowType(true)}
          >
            New leave type
          </Button>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="My Balances" subtitle="Annual leave entitlements">
          {balances.length === 0 ? (
            <EmptyState
              title="No balances"
              description="Your leave balances will appear here."
            />
          ) : (
            <div className="space-y-3">
              {balances.map((b) => (
                <div key={b.leave_type_id} className="flex items-center gap-3">
                  <div className="w-32 shrink-0">
                    <p className="text-[13px] font-medium text-ink">{b.name}</p>
                    <p className="text-[10px] text-faint">
                      {b.is_paid ? "Paid" : "Unpaid"}
                    </p>
                  </div>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(100, (b.remaining / Math.max(1, b.allocated)) * 100)}%`,
                        backgroundColor: b.color,
                      }}
                    />
                  </div>
                  <div className="w-24 shrink-0 text-right">
                    <p className="text-[13px] font-semibold text-ink">
                      {b.remaining} days
                    </p>
                    <p className="text-[10px] text-faint">
                      {b.used} used of {b.allocated}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Pending for review"
          subtitle="Leave requests awaiting decision"
        >
          {pending.length === 0 ? (
            <EmptyState
              title="Nothing pending"
              description="Requests needing your approval will appear here."
            />
          ) : (
            <div className="space-y-3">
              {pending.map((r) => (
                <div key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">
                      {r.employee_name}
                    </p>
                    <Badge tone="brand">{r.leave_type}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-faint">
                    {new Date(r.start_date).toLocaleDateString()} →{" "}
                    {new Date(r.end_date).toLocaleDateString()} · {r.days} days
                  </p>
                  {r.reason && (
                    <p className="mt-1 text-xs text-faint italic">{r.reason}</p>
                  )}
                  {canManage && (
                    <div className="mt-2.5 flex gap-2">
                      <Button
                        size="sm"
                        loading={busy}
                        onClick={() => onApprove(r.id)}
                      >
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onReject(r.id)}
                      >
                        Reject
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="All Requests" subtitle="Leave request history">
        {requests.length === 0 ? (
          <EmptyState
            title="No requests yet"
            description="Requested leave will appear here."
          />
        ) : (
          <Table
            head={
              <>
                <Th>Employee</Th>
                <Th>Type</Th>
                <Th>Dates</Th>
                <Th>Days</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
            empty={
              <div className="px-4 py-8 text-center text-[13px] text-faint">
                No leave requests found.
              </div>
            }
          >
            {requests.slice(0, 20).map((r) => (
              <Tr key={r.id}>
                <Td>{r.employee_name ?? "—"}</Td>
                <Td>
                  <Badge tone="brand">{r.leave_type}</Badge>
                </Td>
                <Td className="text-[12px]">
                  {new Date(r.start_date).toLocaleDateString()} →{" "}
                  {new Date(r.end_date).toLocaleDateString()}
                </Td>
                <Td>{r.days}</Td>
                <Td>
                  <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                </Td>
                <Td>
                  <div className="flex gap-1.5">
                    {r.status === "pending" && canManage && (
                      <Button
                        size="sm"
                        loading={busy}
                        onClick={() => onApprove(r.id)}
                      >
                        Approve
                      </Button>
                    )}
                    {r.status === "pending" && canManage && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onReject(r.id)}
                      >
                        Reject
                      </Button>
                    )}
                    {(r.status === "pending" || r.status === "approved") && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onCancel(r.id)}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </Td>
              </Tr>
            ))}
          </Table>
        )}
      </Card>

      {canManage && (
        <Card title="Leave Types" subtitle="Entitlements & policies">
          {types.length === 0 ? (
            <EmptyState
              title="No leave types"
              description="Leave types will appear here."
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {types.map((t) => (
                <div key={t.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">
                      {t.name}
                    </p>
                    <Badge tone={t.is_active ? "success" : "neutral"}>
                      {t.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-faint">
                    {t.days_per_year} days/yr · carry {t.carry_over} ·{" "}
                    {t.is_paid ? "paid" : "unpaid"}
                  </p>
                  {canManage && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="mt-2"
                      loading={busy}
                      onClick={() => onToggleType(t.id, !t.is_active)}
                    >
                      {t.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <Modal
        open={showRequest}
        onClose={() => setShowRequest(false)}
        title="Request leave"
      >
        <div className="space-y-3">
          <Select
            label="Leave type"
            options={leaveTypeOptions}
            value={req.leave_type_id ?? ""}
            onChange={(e) => setReq({ ...req, leave_type_id: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Start date"
              type="date"
              value={req.start_date ?? ""}
              onChange={(e) => setReq({ ...req, start_date: e.target.value })}
            />
            <Input
              label="End date"
              type="date"
              value={req.end_date ?? ""}
              onChange={(e) => setReq({ ...req, end_date: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={req.half_day === "true"}
              onChange={(e) =>
                setReq({ ...req, half_day: String(e.target.checked) })
              }
            />
            <span className="text-[13px] text-muted">Half day</span>
          </div>
          <Textarea
            label="Reason"
            value={req.reason ?? ""}
            onChange={(e) => setReq({ ...req, reason: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowRequest(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onRequest({ ...req, half_day: req.half_day === "true" });
                setShowRequest(false);
                setReq({});
              }}
            >
              Submit request
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showType}
        onClose={() => setShowType(false)}
        title="New leave type"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={type.name ?? ""}
            onChange={(e) => setType({ ...type, name: e.target.value })}
          />
          <Input
            label="Code"
            value={type.code ?? ""}
            onChange={(e) => setType({ ...type, code: e.target.value })}
          />
          <Input
            label="Color (hex)"
            value={type.color ?? "#6366f1"}
            onChange={(e) => setType({ ...type, color: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Days per year"
              type="number"
              value={type.days_per_year ?? ""}
              onChange={(e) =>
                setType({ ...type, days_per_year: e.target.value })
              }
            />
            <Input
              label="Carry over"
              type="number"
              value={type.carry_over ?? ""}
              onChange={(e) => setType({ ...type, carry_over: e.target.value })}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={type.is_paid === "true"}
              onChange={(e) =>
                setType({ ...type, is_paid: String(e.target.checked) })
              }
            />
            <span className="text-[13px] text-muted">Paid leave</span>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowType(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onCreateType({
                  ...type,
                  days_per_year: Number(type.days_per_year ?? 0),
                  carry_over: Number(type.carry_over ?? 0),
                  is_paid: type.is_paid === "true",
                });
                setShowType(false);
                setType({});
              }}
            >
              Create type
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Hiring

function HiringTab({
  stats,
  jobs,
  candidates,
  interviews,
  offers,
  employees,
  canManage,
  busy,
  onJob,
  onCloseJob,
  onCandidate,
  onStage,
  onInterview,
  onCompleteInterview,
  onOffer,
  onOfferStatus,
}: {
  stats: RecruitmentStats | null;
  jobs: Job[];
  candidates: Candidate[];
  interviews: Interview[];
  offers: Offer[];
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onJob: (payload: Record<string, unknown>) => void;
  onCloseJob: (id: string) => void;
  onCandidate: (payload: Record<string, unknown>) => void;
  onStage: (id: string, stage: string) => void;
  onInterview: (payload: Record<string, unknown>) => void;
  onCompleteInterview: (id: string, payload: Record<string, unknown>) => void;
  onOffer: (payload: Record<string, unknown>) => void;
  onOfferStatus: (id: string, status: string) => void;
}) {
  const [showJob, setShowJob] = useState(false);
  const [showCandidate, setShowCandidate] = useState(false);
  const [showInterview, setShowInterview] = useState(false);
  const [showOffer, setShowOffer] = useState(false);
  const [job, setJob] = useState<Record<string, string>>({});
  const [candidate, setCandidate] = useState<Record<string, string>>({});
  const [interview, setInterview] = useState<Record<string, string>>({});
  const [offer, setOffer] = useState<Record<string, string>>({});

  const jobOptions = jobs.map((j) => ({ value: j.id, label: j.title }));
  const candOptions = candidates.map((c) => ({ value: c.id, label: c.name }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Open Jobs"
          value={stats?.open_jobs ?? 0}
          hint={`${stats?.open_positions ?? 0} open positions`}
          icon={Briefcase}
        />
        <StatCard
          label="Candidates"
          value={stats?.total_candidates ?? 0}
          hint={`${stats?.interviews_scheduled ?? 0} interviews scheduled`}
          icon={Users}
        />
        <StatCard
          label="Offers"
          value={stats?.offers.total ?? 0}
          hint={`${stats?.offers.accepted ?? 0} accepted`}
          icon={Award}
        />
        <StatCard
          label="Hires"
          value={stats?.hires ?? 0}
          hint="Candidates moved to hired"
          icon={Rocket}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canManage && (
          <>
            <Button loading={busy} onClick={() => setShowJob(true)}>
              Post job
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowCandidate(true)}
            >
              Add candidate
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowInterview(true)}
            >
              Schedule interview
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowOffer(true)}
            >
              Create offer
            </Button>
          </>
        )}
      </div>

      <Card title="Jobs" subtitle="Open roles and pipeline">
        {jobs.length === 0 ? (
          <EmptyState
            title="No jobs yet"
            description="Post your first opening to start the hiring pipeline."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {jobs.map((j) => (
              <div
                key={j.id}
                className="flex flex-col rounded-xl border border-line p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <Badge tone={statusTone(j.status)}>{j.status}</Badge>
                  <Badge tone="neutral">{j.openings} openings</Badge>
                </div>
                <p className="mt-3 text-sm font-semibold text-ink">{j.title}</p>
                <p className="mt-0.5 text-[11px] text-faint">
                  {j.department ?? "—"} · {j.location ?? "Remote friendly"}
                </p>
                <p className="mt-2 line-clamp-2 text-xs text-faint">
                  {j.description ?? "No description"}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {j.skills.slice(0, 4).map((s) => (
                    <Badge key={s} tone="brand">
                      {s}
                    </Badge>
                  ))}
                </div>
                {j.status === "open" && canManage && (
                  <div className="mt-auto flex justify-end pt-3">
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={busy}
                      onClick={() => onCloseJob(j.id)}
                    >
                      Close
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Candidates" subtitle="Pipeline by stage">
        {candidates.length === 0 ? (
          <EmptyState
            title="No candidates"
            description="Add candidates to see match scores and move them through stages."
          />
        ) : (
          <Table
            head={
              <>
                <Th>Name</Th>
                <Th>Job</Th>
                <Th>Stage</Th>
                <Th>Match</Th>
                <Th>Experience</Th>
                <Th>Source</Th>
              </>
            }
            empty={
              <div className="px-4 py-8 text-center text-[13px] text-faint">
                No candidates found.
              </div>
            }
          >
            {candidates.map((c) => (
              <Tr key={c.id}>
                <Td>
                  <p className="text-[13px] font-medium text-ink">{c.name}</p>
                  <p className="text-[11px] text-faint">
                    {c.current_title ?? "—"}{" "}
                    {c.current_company ? `@ ${c.current_company}` : ""}
                  </p>
                </Td>
                <Td className="text-[12px]">{c.job_title}</Td>
                <Td>
                  <div className="flex items-center gap-1.5">
                    <Badge tone={statusTone(c.stage)}>{c.stage}</Badge>
                    {canManage && (
                      <Select
                        options={[
                          "applied",
                          "screened",
                          "interview",
                          "offer",
                          "hired",
                          "rejected",
                        ].map((s) => ({ value: s, label: s }))}
                        value={c.stage}
                        onChange={(e) => onStage(c.id, e.target.value)}
                        className="!w-28 !py-1 text-[11px]"
                      />
                    )}
                  </div>
                </Td>
                <Td>
                  <Badge
                    tone={
                      c.match_score >= 60
                        ? "success"
                        : c.match_score >= 30
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {c.match_score}%
                  </Badge>
                </Td>
                <Td className="text-[12px]">{c.experience_years}y</Td>
                <Td className="text-[12px] text-faint">{c.source}</Td>
              </Tr>
            ))}
          </Table>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Interviews" subtitle="Scheduled and completed">
          {interviews.length === 0 ? (
            <EmptyState
              title="No interviews"
              description="Scheduled interviews will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {interviews.slice(0, 10).map((i) => (
                <div key={i.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">
                      {i.candidate_name} · {i.job_title}
                    </p>
                    <Badge tone={statusTone(i.status)}>{i.status}</Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-faint">
                    {i.scheduled_at
                      ? new Date(i.scheduled_at).toLocaleString()
                      : "not scheduled"}{" "}
                    · {i.duration_minutes} min · {i.mode}
                  </p>
                  {i.rating != null && (
                    <p className="mt-1 text-[12px] text-ink">
                      Rating: {i.rating}/5
                    </p>
                  )}
                  {i.status === "scheduled" && canManage && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="mt-2"
                      loading={busy}
                      onClick={() =>
                        onCompleteInterview(i.id, {
                          rating: 4,
                          recommendation: "hire",
                          feedback: "Strong candidate",
                        })
                      }
                    >
                      Complete with rating
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Offers" subtitle="Compensation and status">
          {offers.length === 0 ? (
            <EmptyState
              title="No offers"
              description="Created offers will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {offers.map((o) => (
                <div key={o.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">
                      {o.candidate_name}
                    </p>
                    <Badge tone={statusTone(o.status)}>{o.status}</Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-faint">
                    {o.job_title} · {fmtMoney(o.salary)}
                    {o.equity ? ` + ${o.equity}` : ""}
                  </p>
                  {o.start_date && (
                    <p className="text-[11px] text-faint">
                      Starts {new Date(o.start_date).toLocaleDateString()}
                    </p>
                  )}
                  {o.status === "sent" && canManage && (
                    <div className="mt-2 flex gap-2">
                      <Button
                        size="sm"
                        loading={busy}
                        onClick={() => onOfferStatus(o.id, "accepted")}
                      >
                        Accept
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onOfferStatus(o.id, "declined")}
                      >
                        Decline
                      </Button>
                    </div>
                  )}
                  {o.status === "draft" && canManage && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="mt-2"
                      loading={busy}
                      onClick={() => onOfferStatus(o.id, "sent")}
                    >
                      Send
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={showJob}
        onClose={() => setShowJob(false)}
        title="Post a job"
      >
        <div className="space-y-3">
          <Input
            label="Title"
            value={job.title ?? ""}
            onChange={(e) => setJob({ ...job, title: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Department"
              value={job.department ?? ""}
              onChange={(e) => setJob({ ...job, department: e.target.value })}
            />
            <Input
              label="Location"
              value={job.location ?? ""}
              onChange={(e) => setJob({ ...job, location: e.target.value })}
            />
          </div>
          <Input
            label="Skills (comma separated)"
            value={job.skills ?? ""}
            onChange={(e) => setJob({ ...job, skills: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Openings"
              type="number"
              value={job.openings ?? "1"}
              onChange={(e) => setJob({ ...job, openings: e.target.value })}
            />
            <Input
              label="Salary range"
              value={job.salary_range ?? ""}
              onChange={(e) => setJob({ ...job, salary_range: e.target.value })}
            />
          </div>
          <Textarea
            label="Description"
            value={job.description ?? ""}
            onChange={(e) => setJob({ ...job, description: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowJob(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onJob({
                  ...job,
                  openings: Number(job.openings ?? 1),
                  skills: (job.skills ?? "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setShowJob(false);
                setJob({});
              }}
            >
              Post job
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showCandidate}
        onClose={() => setShowCandidate(false)}
        title="Add candidate"
      >
        <div className="space-y-3">
          <Select
            label="Job"
            options={jobOptions}
            value={candidate.job_id ?? ""}
            onChange={(e) =>
              setCandidate({ ...candidate, job_id: e.target.value })
            }
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Name"
              value={candidate.name ?? ""}
              onChange={(e) =>
                setCandidate({ ...candidate, name: e.target.value })
              }
            />
            <Input
              label="Email"
              value={candidate.email ?? ""}
              onChange={(e) =>
                setCandidate({ ...candidate, email: e.target.value })
              }
            />
          </div>
          <Input
            label="Skills (comma separated)"
            value={candidate.skills ?? ""}
            onChange={(e) =>
              setCandidate({ ...candidate, skills: e.target.value })
            }
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Experience (years)"
              type="number"
              value={candidate.experience_years ?? ""}
              onChange={(e) =>
                setCandidate({ ...candidate, experience_years: e.target.value })
              }
            />
            <Select
              label="Stage"
              options={[
                "applied",
                "screened",
                "interview",
                "offer",
                "hired",
                "rejected",
              ].map((s) => ({ value: s, label: s }))}
              value={candidate.stage ?? ""}
              onChange={(e) =>
                setCandidate({ ...candidate, stage: e.target.value })
              }
            />
          </div>
          <Input
            label="Current company"
            value={candidate.current_company ?? ""}
            onChange={(e) =>
              setCandidate({ ...candidate, current_company: e.target.value })
            }
          />
          <Textarea
            label="Notes"
            value={candidate.notes ?? ""}
            onChange={(e) =>
              setCandidate({ ...candidate, notes: e.target.value })
            }
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCandidate(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onCandidate({
                  ...candidate,
                  skills: (candidate.skills ?? "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                  experience_years: Number(candidate.experience_years ?? 0),
                });
                setShowCandidate(false);
                setCandidate({});
              }}
            >
              Add candidate
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showInterview}
        onClose={() => setShowInterview(false)}
        title="Schedule interview"
      >
        <div className="space-y-3">
          <Select
            label="Candidate"
            options={candOptions}
            value={interview.candidate_id ?? ""}
            onChange={(e) =>
              setInterview({ ...interview, candidate_id: e.target.value })
            }
          />
          <Select
            label="Job"
            options={jobOptions}
            value={interview.job_id ?? ""}
            onChange={(e) =>
              setInterview({ ...interview, job_id: e.target.value })
            }
          />
          <Input
            label="Scheduled at"
            type="datetime-local"
            value={interview.scheduled_at ?? ""}
            onChange={(e) =>
              setInterview({ ...interview, scheduled_at: e.target.value })
            }
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Duration (minutes)"
              type="number"
              value={interview.duration_minutes ?? "45"}
              onChange={(e) =>
                setInterview({ ...interview, duration_minutes: e.target.value })
              }
            />
            <Select
              label="Mode"
              options={[
                { value: "video", label: "Video" },
                { value: "phone", label: "Phone" },
                { value: "onsite", label: "Onsite" },
              ]}
              value={interview.mode ?? ""}
              onChange={(e) =>
                setInterview({ ...interview, mode: e.target.value })
              }
            />
          </div>
          <Input
            label="Panel (comma separated names)"
            value={interview.panel ?? ""}
            onChange={(e) =>
              setInterview({ ...interview, panel: e.target.value })
            }
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowInterview(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onInterview({
                  ...interview,
                  duration_minutes: Number(interview.duration_minutes ?? 45),
                  panel: (interview.panel ?? "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setShowInterview(false);
                setInterview({});
              }}
            >
              Schedule
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showOffer}
        onClose={() => setShowOffer(false)}
        title="Create offer"
      >
        <div className="space-y-3">
          <Select
            label="Candidate"
            options={candOptions}
            value={offer.candidate_id ?? ""}
            onChange={(e) =>
              setOffer({ ...offer, candidate_id: e.target.value })
            }
          />
          <Select
            label="Job"
            options={jobOptions}
            value={offer.job_id ?? ""}
            onChange={(e) => setOffer({ ...offer, job_id: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Salary (annual)"
              type="number"
              value={offer.salary ?? ""}
              onChange={(e) => setOffer({ ...offer, salary: e.target.value })}
            />
            <Input
              label="Equity"
              value={offer.equity ?? ""}
              onChange={(e) => setOffer({ ...offer, equity: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Start date"
              type="date"
              value={offer.start_date ?? ""}
              onChange={(e) =>
                setOffer({ ...offer, start_date: e.target.value })
              }
            />
            <Input
              label="Offer expires"
              type="date"
              value={offer.expires_at ?? ""}
              onChange={(e) =>
                setOffer({ ...offer, expires_at: e.target.value })
              }
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowOffer(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onOffer({ ...offer, salary: Number(offer.salary ?? 0) });
                setShowOffer(false);
                setOffer({});
              }}
            >
              Create offer
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Performance

function PerformanceTab({
  summary,
  cycles,
  goals,
  reviews,
  employees,
  canManage,
  busy,
  onCycle,
  onCycleStatus,
  onGoal,
  onProgress,
  onReview,
  onSubmit,
  onComplete,
}: {
  summary: PerformanceSummary | null;
  cycles: PerformanceCycle[];
  goals: PerformanceGoal[];
  reviews: PerformanceReview[];
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onCycle: (payload: Record<string, unknown>) => void;
  onCycleStatus: (id: string, status: string) => void;
  onGoal: (payload: Record<string, unknown>) => void;
  onProgress: (id: string, progress: number) => void;
  onReview: (payload: Record<string, unknown>) => void;
  onSubmit: (id: string) => void;
  onComplete: (id: string) => void;
}) {
  const [showCycle, setShowCycle] = useState(false);
  const [showGoal, setShowGoal] = useState(false);
  const [showReview, setShowReview] = useState(false);
  const [cycle, setCycle] = useState<Record<string, string>>({});
  const [goal, setGoal] = useState<Record<string, string>>({});
  const [review, setReview] = useState<Record<string, string>>({});

  const cycleOptions = cycles.map((c) => ({ value: c.id, label: c.name }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Cycles"
          value={summary?.cycles.total ?? 0}
          hint={`${summary?.cycles.open ?? 0} open`}
          icon={CalendarDays}
        />
        <StatCard
          label="Reviews"
          value={summary?.reviews.total ?? 0}
          hint={`${summary?.reviews.completed ?? 0} completed`}
          icon={ClipboardCheck}
        />
        <StatCard
          label="Average Rating"
          value={
            summary?.reviews.average_rating
              ? `${summary.reviews.average_rating}/5`
              : "—"
          }
          hint="Across completed reviews"
          icon={Award}
        />
        <StatCard
          label="Active Goals"
          value={summary?.goals.active ?? 0}
          hint={`${summary?.goals.completed ?? 0} completed`}
          icon={Target}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canManage && (
          <Button loading={busy} onClick={() => setShowCycle(true)}>
            New cycle
          </Button>
        )}
        <Button
          variant="secondary"
          loading={busy}
          onClick={() => setShowGoal(true)}
        >
          Create goal
        </Button>
        {canManage && (
          <Button
            variant="secondary"
            loading={busy}
            onClick={() => setShowReview(true)}
          >
            Create review
          </Button>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Cycles" subtitle="Review cycles">
          {cycles.length === 0 ? (
            <EmptyState
              title="No cycles"
              description="Start a performance cycle to structure reviews."
            />
          ) : (
            <div className="space-y-2.5">
              {cycles.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3.5"
                >
                  <div>
                    <p className="text-[13px] font-semibold text-ink">
                      {c.name}
                    </p>
                    <p className="text-[11px] text-faint">
                      {c.description ?? "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                    {canManage && c.status !== "closed" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() =>
                          onCycleStatus(
                            c.id,
                            c.status === "open" ? "reviewing" : "closed",
                          )
                        }
                      >
                        {c.status === "open" ? "Start review" : "Close"}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Reviews" subtitle="360 & manager reviews">
          {reviews.length === 0 ? (
            <EmptyState
              title="No reviews"
              description="Created reviews will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {reviews.slice(0, 10).map((r) => (
                <div key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">
                      {r.employee_name} · {r.kind}
                    </p>
                    <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                  </div>
                  {r.reviewer_name && (
                    <p className="text-[11px] text-faint">
                      by {r.reviewer_name}
                    </p>
                  )}
                  {r.rating != null && (
                    <p className="mt-1 text-[12px] text-ink">
                      Rating: {r.rating}/5
                    </p>
                  )}
                  {r.ai_summary && (
                    <p className="mt-1.5 line-clamp-2 rounded-lg bg-surface px-3 py-2 text-[11px] italic text-faint">
                      {r.ai_summary}
                    </p>
                  )}
                  {r.status === "draft" && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="mt-2"
                      loading={busy}
                      onClick={() => onSubmit(r.id)}
                    >
                      Submit
                    </Button>
                  )}
                  {r.status === "submitted" && canManage && (
                    <Button
                      size="sm"
                      className="mt-2"
                      loading={busy}
                      onClick={() => onComplete(r.id)}
                    >
                      Complete & summarize
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Goals" subtitle="Performance goals progress">
        {goals.length === 0 ? (
          <EmptyState
            title="No goals"
            description="Create goals to track performance."
          />
        ) : (
          <Table
            head={
              <>
                <Th>Goal</Th>
                <Th>Kind</Th>
                <Th>Progress</Th>
                <Th>Status</Th>
                <Th>Due</Th>
              </>
            }
            empty={
              <div className="px-4 py-8 text-center text-[13px] text-faint">
                No goals found.
              </div>
            }
          >
            {goals.slice(0, 15).map((g) => (
              <Tr key={g.id}>
                <Td className="text-[13px] font-medium text-ink">{g.title}</Td>
                <Td>
                  <Badge tone="brand">{g.kind}</Badge>
                </Td>
                <Td className="w-40">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                      <div
                        className="h-full rounded-full bg-brand"
                        style={{ width: `${g.progress}%` }}
                      />
                    </div>
                    <span className="w-9 text-right text-[11px] text-faint">
                      {g.progress}%
                    </span>
                  </div>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    defaultValue={g.progress}
                    className="mt-1 !h-7 !w-20 !py-0 text-[11px]"
                    onBlur={(e) => {
                      const v = Number(e.target.value);
                      if (v !== g.progress) onProgress(g.id, v);
                    }}
                  />
                </Td>
                <Td>
                  <Badge tone={statusTone(g.status)}>{g.status}</Badge>
                </Td>
                <Td className="text-[12px]">
                  {g.due_date ? new Date(g.due_date).toLocaleDateString() : "—"}
                </Td>
              </Tr>
            ))}
          </Table>
        )}
      </Card>

      <Modal
        open={showCycle}
        onClose={() => setShowCycle(false)}
        title="New performance cycle"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={cycle.name ?? ""}
            onChange={(e) => setCycle({ ...cycle, name: e.target.value })}
          />
          <Input
            label="Description"
            value={cycle.description ?? ""}
            onChange={(e) =>
              setCycle({ ...cycle, description: e.target.value })
            }
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCycle(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onCycle(cycle);
                setShowCycle(false);
                setCycle({});
              }}
            >
              Create cycle
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showGoal}
        onClose={() => setShowGoal(false)}
        title="Create performance goal"
      >
        <div className="space-y-3">
          <Select
            label="Employee"
            options={employees}
            value={goal.employee_id ?? ""}
            onChange={(e) => setGoal({ ...goal, employee_id: e.target.value })}
          />
          <Select
            label="Cycle"
            options={cycleOptions}
            value={goal.cycle_id ?? ""}
            onChange={(e) => setGoal({ ...goal, cycle_id: e.target.value })}
          />
          <Input
            label="Title"
            value={goal.title ?? ""}
            onChange={(e) => setGoal({ ...goal, title: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Kind"
              options={[
                { value: "okr", label: "OKR" },
                { value: "kpi", label: "KPI" },
                { value: "development", label: "Development" },
              ]}
              value={goal.kind ?? ""}
              onChange={(e) => setGoal({ ...goal, kind: e.target.value })}
            />
            <Input
              label="Weight"
              type="number"
              value={goal.weight ?? "1"}
              onChange={(e) => setGoal({ ...goal, weight: e.target.value })}
            />
          </div>
          <Input
            label="Due date"
            type="date"
            value={goal.due_date ?? ""}
            onChange={(e) => setGoal({ ...goal, due_date: e.target.value })}
          />
          <Textarea
            label="Description"
            value={goal.description ?? ""}
            onChange={(e) => setGoal({ ...goal, description: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowGoal(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onGoal({ ...goal, weight: Number(goal.weight ?? 1) });
                setShowGoal(false);
                setGoal({});
              }}
            >
              Create goal
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showReview}
        onClose={() => setShowReview(false)}
        title="Create review"
      >
        <div className="space-y-3">
          <Select
            label="Employee"
            options={employees}
            value={review.employee_id ?? ""}
            onChange={(e) =>
              setReview({ ...review, employee_id: e.target.value })
            }
          />
          <Select
            label="Cycle"
            options={cycleOptions}
            value={review.cycle_id ?? ""}
            onChange={(e) => setReview({ ...review, cycle_id: e.target.value })}
          />
          <Select
            label="Kind"
            options={[
              { value: "manager", label: "Manager" },
              { value: "self", label: "Self" },
              { value: "peer", label: "Peer" },
              { value: "360", label: "360" },
            ]}
            value={review.kind ?? ""}
            onChange={(e) => setReview({ ...review, kind: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowReview(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onReview(review);
                setShowReview(false);
                setReview({});
              }}
            >
              Create review
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Assets

function AssetsTab({
  assets,
  employees,
  canManage,
  busy,
  onCreate,
  onAssign,
  onStatus,
}: {
  assets: Asset[];
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onCreate: (payload: Record<string, unknown>) => void;
  onAssign: (id: string, employeeId?: string) => void;
  onStatus: (id: string, status: string) => void;
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [asset, setAsset] = useState<Record<string, string>>({});
  const [assignFor, setAssignFor] = useState<Record<string, string>>({});

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of assets) counts[a.status] = (counts[a.status] ?? 0) + 1;
    return counts;
  }, [assets]);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Total Assets" value={assets.length} icon={Package} />
        <StatCard
          label="Assigned"
          value={statusCounts.assigned ?? 0}
          hint={`${statusCounts.available ?? 0} available`}
          icon={UserRound}
        />
        <StatCard
          label="Maintenance"
          value={statusCounts.maintenance ?? 0}
          icon={Wrench}
        />
        <StatCard label="Lost" value={statusCounts.lost ?? 0} icon={Package} />
      </div>

      {canManage && (
        <Button loading={busy} onClick={() => setShowCreate(true)}>
          Register asset
        </Button>
      )}

      <Card title="Asset Register" subtitle="Equipment & inventory">
        {assets.length === 0 ? (
          <EmptyState
            title="No assets"
            description="Registered assets will appear here."
          />
        ) : (
          <Table
            head={
              <>
                <Th>Asset</Th>
                <Th>Category</Th>
                <Th>Assigned To</Th>
                <Th>Status</Th>
                <Th>Warranty</Th>
                <Th>Actions</Th>
              </>
            }
            empty={
              <div className="px-4 py-8 text-center text-[13px] text-faint">
                No assets found.
              </div>
            }
          >
            {assets.map((a) => (
              <Tr key={a.id}>
                <Td>
                  <p className="text-[13px] font-medium text-ink">{a.name}</p>
                  <p className="text-[11px] text-faint">
                    {a.serial_number ?? "no serial"}
                  </p>
                </Td>
                <Td>
                  <Badge tone="brand">{a.category}</Badge>
                </Td>
                <Td className="text-[12px]">{a.employee_name ?? "—"}</Td>
                <Td>
                  <Badge tone={statusTone(a.status)}>{a.status}</Badge>
                </Td>
                <Td className="text-[12px]">
                  {a.warranty_until
                    ? new Date(a.warranty_until).toLocaleDateString()
                    : "—"}
                </Td>
                <Td>
                  {canManage && (
                    <div className="flex items-center gap-1.5">
                      <Select
                        options={[
                          "available",
                          "assigned",
                          "maintenance",
                          "returned",
                          "lost",
                        ].map((s) => ({ value: s, label: s }))}
                        value={a.status}
                        onChange={(e) => onStatus(a.id, e.target.value)}
                        className="!w-28 !py-1 text-[11px]"
                      />
                      {(a.status === "available" ||
                        a.status === "returned") && (
                        <Select
                          placeholder="Assign"
                          options={employees}
                          value={assignFor[a.id] ?? ""}
                          onChange={(e) => {
                            onAssign(a.id, e.target.value || undefined);
                            setAssignFor({
                              ...assignFor,
                              [a.id]: e.target.value,
                            });
                          }}
                          className="!w-32 !py-1 text-[11px]"
                        />
                      )}
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        )}
      </Card>

      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Register asset"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={asset.name ?? ""}
            onChange={(e) => setAsset({ ...asset, name: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Category"
              options={[
                { value: "laptop", label: "Laptop" },
                { value: "monitor", label: "Monitor" },
                { value: "phone", label: "Phone" },
                { value: "accessory", label: "Accessory" },
                { value: "other", label: "Other" },
              ]}
              value={asset.category ?? ""}
              onChange={(e) => setAsset({ ...asset, category: e.target.value })}
            />
            <Input
              label="Serial number"
              value={asset.serial_number ?? ""}
              onChange={(e) =>
                setAsset({ ...asset, serial_number: e.target.value })
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Purchase date"
              type="date"
              value={asset.purchase_date ?? ""}
              onChange={(e) =>
                setAsset({ ...asset, purchase_date: e.target.value })
              }
            />
            <Input
              label="Warranty until"
              type="date"
              value={asset.warranty_until ?? ""}
              onChange={(e) =>
                setAsset({ ...asset, warranty_until: e.target.value })
              }
            />
          </div>
          <Textarea
            label="Notes"
            value={asset.notes ?? ""}
            onChange={(e) => setAsset({ ...asset, notes: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onCreate(asset);
                setShowCreate(false);
                setAsset({});
              }}
            >
              Register
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Offboarding

function OffboardingTab({
  offboardings,
  alumni,
  employees,
  canManage,
  busy,
  onStart,
  onTask,
  onCompleteTask,
  onExitInterview,
  onComplete,
  onBoomerang,
}: {
  offboardings: OffboardingItem[];
  alumni: Awaited<ReturnType<typeof listAlumni>>;
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onStart: (payload: Record<string, unknown>) => void;
  onTask: (id: string, payload: Record<string, unknown>) => void;
  onCompleteTask: (id: string, taskId: string) => void;
  onExitInterview: (id: string, payload: Record<string, unknown>) => void;
  onComplete: (id: string) => void;
  onBoomerang: (id: string) => void;
}) {
  const [showStart, setShowStart] = useState(false);
  const [start, setStart] = useState<Record<string, string>>({});
  const [detailFor, setDetailFor] = useState<OffboardingItem | null>(null);
  const [showTask, setShowTask] = useState(false);
  const [showExit, setShowExit] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [exit, setExit] = useState<Record<string, string>>({});

  return (
    <div className="space-y-5">
      {canManage && (
        <Button loading={busy} onClick={() => setShowStart(true)}>
          <Rocket className="h-3.5 w-3.5" /> Start offboarding
        </Button>
      )}

      <Card title="Offboardings" subtitle="Departures in progress">
        {offboardings.length === 0 ? (
          <EmptyState
            title="No offboardings"
            description="Started offboardings will appear here."
          />
        ) : (
          <div className="space-y-2.5">
            {offboardings.map((o) => (
              <div key={o.id} className="rounded-xl border border-line p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <p className="text-[13px] font-semibold text-ink">
                      {o.employee_name}
                    </p>
                    <Badge tone={statusTone(o.status)}>{o.status}</Badge>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDetailFor(o)}
                  >
                    View
                  </Button>
                </div>
                <p className="mt-1 text-[11px] text-faint">
                  {o.reason ?? "—"} · exits{" "}
                  {o.exit_date
                    ? new Date(o.exit_date).toLocaleDateString()
                    : "—"}{" "}
                  · {o.tasks.filter((t) => t.status === "completed").length}/
                  {o.tasks.length} tasks
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Alumni" subtitle="Former employees we keep in touch with">
        {alumni.length === 0 ? (
          <EmptyState
            title="No alumni"
            description="Completed offboardings with alumni transition will appear here."
          />
        ) : (
          <Table
            head={
              <>
                <Th>Name</Th>
                <Th>Left</Th>
                <Th>Reason</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
            empty={
              <div className="px-4 py-8 text-center text-[13px] text-faint">
                No alumni found.
              </div>
            }
          >
            {alumni.map((a) => (
              <Tr key={a.id}>
                <Td className="text-[13px] font-medium text-ink">{a.name}</Td>
                <Td className="text-[12px]">
                  {a.left_at ? new Date(a.left_at).toLocaleDateString() : "—"}
                </Td>
                <Td className="text-[12px] text-faint">{a.reason ?? "—"}</Td>
                <Td>
                  <Badge tone={statusTone(a.status)}>{a.status}</Badge>
                </Td>
                <Td>
                  {canManage && a.status !== "boomerang" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={busy}
                      onClick={() => onBoomerang(a.id)}
                    >
                      Boomerang
                    </Button>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        )}
      </Card>

      <Modal
        open={showStart}
        onClose={() => setShowStart(false)}
        title="Start offboarding"
      >
        <div className="space-y-3">
          <Select
            label="Employee"
            options={employees}
            value={start.employee_id ?? ""}
            onChange={(e) =>
              setStart({ ...start, employee_id: e.target.value })
            }
          />
          <Input
            label="Reason"
            value={start.reason ?? ""}
            onChange={(e) => setStart({ ...start, reason: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Resignation date"
              type="date"
              value={start.resignation_date ?? ""}
              onChange={(e) =>
                setStart({ ...start, resignation_date: e.target.value })
              }
            />
            <Input
              label="Exit date"
              type="date"
              value={start.exit_date ?? ""}
              onChange={(e) =>
                setStart({ ...start, exit_date: e.target.value })
              }
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={start.transitions_to_alumni === "true"}
              onChange={(e) =>
                setStart({
                  ...start,
                  transitions_to_alumni: String(e.target.checked),
                })
              }
            />
            <span className="text-[13px] text-muted">
              Create alumni profile on completion
            </span>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowStart(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onStart({
                  ...start,
                  transitions_to_alumni: start.transitions_to_alumni === "true",
                });
                setShowStart(false);
                setStart({});
              }}
            >
              Start offboarding
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={detailFor != null}
        onClose={() => setDetailFor(null)}
        title={detailFor ? `Offboarding · ${detailFor.employee_name}` : ""}
        description={detailFor?.reason ?? undefined}
        size="lg"
      >
        {detailFor && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge tone={statusTone(detailFor.status)}>
                {detailFor.status}
              </Badge>
              {detailFor.transitions_to_alumni && (
                <Badge tone="brand">Alumni on exit</Badge>
              )}
              {detailFor.exit_interview && (
                <Badge tone="success">Exit interview done</Badge>
              )}
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wide text-faint">
                  Checklist
                </p>
                <div className="flex gap-2">
                  {canManage && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setShowTask(true)}
                    >
                      Add task
                    </Button>
                  )}
                  {canManage && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setShowExit(true)}
                    >
                      Exit interview
                    </Button>
                  )}
                </div>
              </div>
              <div className="space-y-2">
                {detailFor.tasks.map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                  >
                    <div>
                      <p className="text-[13px] font-medium text-ink">
                        {t.title}
                      </p>
                      <p className="text-[11px] text-faint">
                        {t.category}{" "}
                        {t.completed_at
                          ? `· done ${new Date(t.completed_at).toLocaleDateString()}`
                          : ""}
                      </p>
                    </div>
                    {t.status === "completed" ? (
                      <Badge tone="success">Done</Badge>
                    ) : (
                      canManage && (
                        <Button
                          size="sm"
                          loading={busy}
                          onClick={() => onCompleteTask(detailFor.id, t.id)}
                        >
                          Complete
                        </Button>
                      )
                    )}
                  </div>
                ))}
              </div>
            </div>
            {canManage &&
              detailFor.tasks.every((t) => t.status === "completed") &&
              detailFor.status !== "completed" && (
                <Button
                  loading={busy}
                  onClick={() => {
                    onComplete(detailFor.id);
                    setDetailFor(null);
                  }}
                >
                  Finalize offboarding
                </Button>
              )}
          </div>
        )}
      </Modal>

      <Modal
        open={showTask}
        onClose={() => setShowTask(false)}
        title="Add offboarding task"
      >
        <div className="space-y-3">
          <Input
            label="Title"
            value={taskTitle}
            onChange={(e) => setTaskTitle(e.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowTask(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                if (detailFor) {
                  onTask(detailFor.id, {
                    title: taskTitle,
                    category: "knowledge",
                  });
                }
                setShowTask(false);
                setTaskTitle("");
              }}
            >
              Add task
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showExit}
        onClose={() => setShowExit(false)}
        title="Exit interview"
      >
        <div className="space-y-3">
          <Textarea
            label="Feedback"
            value={exit.feedback ?? ""}
            onChange={(e) => setExit({ ...exit, feedback: e.target.value })}
          />
          <Input
            label="Reason"
            value={exit.reason ?? ""}
            onChange={(e) => setExit({ ...exit, reason: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowExit(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                if (detailFor) {
                  onExitInterview(detailFor.id, exit);
                }
                setShowExit(false);
                setExit({});
              }}
            >
              Save interview
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Compliance

function ComplianceTab({
  overview,
  documents,
  requirements,
  trainings,
  employees,
  canManage,
  busy,
  onDocument,
  onRenew,
  onRequirement,
  onTraining,
}: {
  overview: ComplianceOverview | null;
  documents: ComplianceDocument[];
  requirements: TrainingRequirement[];
  trainings: TrainingCompletion[];
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onDocument: (payload: Record<string, unknown>) => void;
  onRenew: (id: string, payload: Record<string, unknown>) => void;
  onRequirement: (payload: Record<string, unknown>) => void;
  onTraining: (payload: Record<string, unknown>) => void;
}) {
  const [showDoc, setShowDoc] = useState(false);
  const [showReq, setShowReq] = useState(false);
  const [showTraining, setShowTraining] = useState(false);
  const [doc, setDoc] = useState<Record<string, string>>({});
  const [req, setReq] = useState<Record<string, string>>({});
  const [training, setTraining] = useState<Record<string, string>>({});

  const reqOptions = requirements.map((r) => ({ value: r.id, label: r.name }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Documents"
          value={overview?.documents.total ?? 0}
          hint={`${overview?.documents.valid ?? 0} valid`}
          icon={FileCheck2}
        />
        <StatCard
          label="Expired"
          value={overview?.documents.expired ?? 0}
          hint="Need immediate action"
          icon={FileCheck2}
        />
        <StatCard
          label="Expiring ≤ 30d"
          value={overview?.documents.expiring_30 ?? 0}
          icon={CalendarClock}
        />
        <StatCard
          label="Missing Trainings"
          value={overview?.trainings.missing ?? 0}
          hint={`${overview?.trainings.expired_completions ?? 0} expired`}
          icon={ClipboardCheck}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canManage && (
          <>
            <Button loading={busy} onClick={() => setShowDoc(true)}>
              Record document
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowReq(true)}
            >
              Add requirement
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowTraining(true)}
            >
              Record training
            </Button>
          </>
        )}
      </div>

      <Card title="Documents" subtitle="Visas, certifications, IDs and more">
        {documents.length === 0 ? (
          <EmptyState
            title="No documents"
            description="Recorded compliance documents will appear here."
          />
        ) : (
          <Table
            head={
              <>
                <Th>Title</Th>
                <Th>Type</Th>
                <Th>Employee</Th>
                <Th>Expires</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
            empty={
              <div className="px-4 py-8 text-center text-[13px] text-faint">
                No documents found.
              </div>
            }
          >
            {documents.slice(0, 15).map((d) => (
              <Tr key={d.id}>
                <Td className="text-[13px] font-medium text-ink">{d.title}</Td>
                <Td>
                  <Badge tone="brand">{d.document_type}</Badge>
                </Td>
                <Td className="text-[12px]">{d.employee_name ?? "—"}</Td>
                <Td className="text-[12px]">
                  {d.expires_at
                    ? new Date(d.expires_at).toLocaleDateString()
                    : "—"}
                </Td>
                <Td>
                  <Badge tone={statusTone(d.status)}>{d.status}</Badge>
                </Td>
                <Td>
                  {canManage && d.status !== "valid" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      loading={busy}
                      onClick={() => onRenew(d.id, {})}
                    >
                      Renew
                    </Button>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
        )}
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Training Requirements"
          subtitle="Mandatory training programs"
        >
          {requirements.length === 0 ? (
            <EmptyState
              title="No requirements"
              description="Create training requirements to track completions."
            />
          ) : (
            <div className="space-y-2.5">
              {requirements.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">{r.name}</p>
                    <p className="text-[11px] text-faint">
                      {r.category} · every {r.frequency_days} days ·{" "}
                      {r.required_for.join(", ") || "everyone"}
                    </p>
                  </div>
                  <Badge tone="brand">{r.category}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Training Completions" subtitle="Who completed what">
          {trainings.length === 0 ? (
            <EmptyState
              title="No completions"
              description="Recorded training completions will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {trainings.slice(0, 12).map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">
                      {t.employee_name} · {t.requirement}
                    </p>
                    <p className="text-[11px] text-faint">
                      completed{" "}
                      {t.completed_at
                        ? new Date(t.completed_at).toLocaleDateString()
                        : "—"}
                      {t.expires_at
                        ? ` · expires ${new Date(t.expires_at).toLocaleDateString()}`
                        : ""}
                    </p>
                  </div>
                  <Badge tone={t.expired ? "danger" : "success"}>
                    {t.expired ? "Expired" : "Current"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={showDoc}
        onClose={() => setShowDoc(false)}
        title="Record compliance document"
      >
        <div className="space-y-3">
          <Select
            label="Employee"
            options={employees}
            value={doc.employee_id ?? ""}
            onChange={(e) => setDoc({ ...doc, employee_id: e.target.value })}
          />
          <Input
            label="Title"
            value={doc.title ?? ""}
            onChange={(e) => setDoc({ ...doc, title: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Type"
              options={[
                { value: "visa", label: "Visa" },
                { value: "passport", label: "Passport" },
                { value: "certification", label: "Certification" },
                { value: "id", label: "ID" },
                { value: "contract", label: "Contract" },
                { value: "other", label: "Other" },
              ]}
              value={doc.document_type ?? ""}
              onChange={(e) =>
                setDoc({ ...doc, document_type: e.target.value })
              }
            />
            <Input
              label="Reference"
              value={doc.reference ?? ""}
              onChange={(e) => setDoc({ ...doc, reference: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Issued"
              type="date"
              value={doc.issued_at ?? ""}
              onChange={(e) => setDoc({ ...doc, issued_at: e.target.value })}
            />
            <Input
              label="Expires"
              type="date"
              value={doc.expires_at ?? ""}
              onChange={(e) => setDoc({ ...doc, expires_at: e.target.value })}
            />
          </div>
          <Textarea
            label="Notes"
            value={doc.notes ?? ""}
            onChange={(e) => setDoc({ ...doc, notes: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowDoc(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onDocument(doc);
                setShowDoc(false);
                setDoc({});
              }}
            >
              Record document
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showReq}
        onClose={() => setShowReq(false)}
        title="Add training requirement"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={req.name ?? ""}
            onChange={(e) => setReq({ ...req, name: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Category"
              options={[
                { value: "compliance", label: "Compliance" },
                { value: "safety", label: "Safety" },
                { value: "security", label: "Security" },
                { value: "professional", label: "Professional" },
              ]}
              value={req.category ?? ""}
              onChange={(e) => setReq({ ...req, category: e.target.value })}
            />
            <Input
              label="Frequency (days)"
              type="number"
              value={req.frequency_days ?? "365"}
              onChange={(e) =>
                setReq({ ...req, frequency_days: e.target.value })
              }
            />
          </div>
          <Input
            label="Required for (roles, comma separated)"
            value={req.required_for ?? ""}
            onChange={(e) => setReq({ ...req, required_for: e.target.value })}
          />
          <Textarea
            label="Description"
            value={req.description ?? ""}
            onChange={(e) => setReq({ ...req, description: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowReq(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onRequirement({
                  ...req,
                  frequency_days: Number(req.frequency_days ?? 365),
                  required_for: (req.required_for ?? "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setShowReq(false);
                setReq({});
              }}
            >
              Add requirement
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showTraining}
        onClose={() => setShowTraining(false)}
        title="Record training completion"
      >
        <div className="space-y-3">
          <Select
            label="Employee"
            options={employees}
            value={training.employee_id ?? ""}
            onChange={(e) =>
              setTraining({ ...training, employee_id: e.target.value })
            }
          />
          <Select
            label="Requirement"
            options={reqOptions}
            value={training.requirement_id ?? ""}
            onChange={(e) =>
              setTraining({ ...training, requirement_id: e.target.value })
            }
          />
          <Input
            label="Completed"
            type="date"
            value={training.completed_at ?? ""}
            onChange={(e) =>
              setTraining({ ...training, completed_at: e.target.value })
            }
          />
          <Input
            label="Provider"
            value={training.provider ?? ""}
            onChange={(e) =>
              setTraining({ ...training, provider: e.target.value })
            }
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowTraining(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onTraining(training);
                setShowTraining(false);
                setTraining({});
              }}
            >
              Record completion
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Workforce

function WorkforceTab({
  analytics,
  plans,
  succession,
  snapshots,
  hiringNeeds,
  employees,
  canManage,
  busy,
  onPlan,
  onPlanStatus,
  onCandidate,
  onReadiness,
  onSnapshot,
}: {
  analytics: WorkforceAnalytics | null;
  plans: WorkforcePlan[];
  succession: SuccessionCandidate[];
  snapshots: WorkforceSnapshot[];
  hiringNeeds: HiringNeeds | null;
  employees: { value: string; label: string }[];
  canManage: boolean;
  busy: boolean;
  onPlan: (payload: Record<string, unknown>) => void;
  onPlanStatus: (id: string, status: string) => void;
  onCandidate: (payload: Record<string, unknown>) => void;
  onReadiness: (id: string, readiness: number) => void;
  onSnapshot: () => void;
}) {
  const [showPlan, setShowPlan] = useState(false);
  const [showCandidate, setShowCandidate] = useState(false);
  const [plan, setPlan] = useState<Record<string, string>>({});
  const [candidate, setCandidate] = useState<Record<string, string>>({});

  const latest = snapshots[0];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Headcount"
          value={analytics?.headcount ?? 0}
          hint={`${analytics?.headcount_status.total ?? 0} total records`}
          icon={Users}
        />
        <StatCard
          label="Hires / Exits"
          value={`${analytics?.hires_month ?? 0} / ${analytics?.exits_month ?? 0}`}
          hint="This month"
          icon={Rocket}
        />
        <StatCard
          label="Attrition"
          value={`${analytics?.attrition_rate ?? 0}%`}
          hint={
            hiringNeeds?.attrition_pressure
              ? "Pressure detected"
              : "Monthly rate"
          }
          icon={TrendingUp}
        />
        <StatCard
          label="Succession Ready"
          value={analytics?.succession_pipeline.ready ?? 0}
          hint={`${analytics?.succession_pipeline.developing ?? 0} developing`}
          icon={Users}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canManage && (
          <>
            <Button loading={busy} onClick={() => setShowPlan(true)}>
              New plan
            </Button>
            <Button
              variant="secondary"
              loading={busy}
              onClick={() => setShowCandidate(true)}
            >
              Add succession candidate
            </Button>
            <Button variant="secondary" loading={busy} onClick={onSnapshot}>
              Compute snapshot
            </Button>
          </>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Hiring Needs"
          subtitle="Open roles + plan growth by department"
        >
          {!hiringNeeds || hiringNeeds.by_department.length === 0 ? (
            <EmptyState
              title="No hiring needs"
              description="Open jobs will drive hiring signals."
            />
          ) : (
            <div className="space-y-2.5">
              {hiringNeeds.by_department.map((n) => (
                <div
                  key={n.department}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">
                      {n.department}
                    </p>
                    <p className="text-[11px] text-faint">
                      {n.open_positions} open · {n.plan_growth} plan growth
                    </p>
                  </div>
                  <Badge tone={statusTone(n.priority)}>
                    {n.priority} priority
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Succession Pipeline" subtitle="Ready now and developing">
          {succession.length === 0 ? (
            <EmptyState
              title="No succession candidates"
              description="Add candidates to build the leadership pipeline."
            />
          ) : (
            <div className="space-y-2.5">
              {succession.map((s) => (
                <div key={s.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-[13px] font-semibold text-ink">
                        {s.candidate_name} → {s.position_title}
                      </p>
                      <p className="text-[11px] text-faint">
                        {s.candidate_designation ?? "—"}
                      </p>
                    </div>
                    <Badge
                      tone={
                        s.status === "ready"
                          ? "success"
                          : s.status === "developing"
                            ? "warning"
                            : "neutral"
                      }
                    >
                      {s.status}
                    </Badge>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-[11px] text-faint">Readiness</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                      <div
                        className="h-full rounded-full bg-brand"
                        style={{ width: `${s.readiness}%` }}
                      />
                    </div>
                    <span className="text-[11px] font-semibold text-brand">
                      {s.readiness}%
                    </span>
                  </div>
                  {canManage && (
                    <Select
                      className="mt-2 !w-32 !py-1 text-[11px]"
                      options={["identified", "developing", "ready"].map(
                        (x) => ({ value: x, label: x }),
                      )}
                      value={s.status}
                      onChange={(e) => onReadiness(s.id, s.readiness)}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Workforce Plans"
          subtitle="Headcount planning"
          actions={
            canManage ? (
              <Button
                size="sm"
                variant="secondary"
                loading={busy}
                onClick={() => setShowPlan(true)}
              >
                New plan
              </Button>
            ) : undefined
          }
        >
          {plans.length === 0 ? (
            <EmptyState
              title="No plans"
              description="Workforce plans will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {plans.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">
                      {p.title}
                    </p>
                    <p className="text-[11px] text-faint">
                      {p.department ?? "—"} · {p.horizon} · target{" "}
                      {p.headcount_target} · budget {fmtMoney(p.budget)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={statusTone(p.status)}>{p.status}</Badge>
                    {canManage && p.status === "draft" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onPlanStatus(p.id, "active")}
                      >
                        Activate
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Snapshots" subtitle="Computed workforce snapshots">
          {snapshots.length === 0 ? (
            <EmptyState
              title="No snapshots"
              description="Compute a snapshot to track headcount trends."
            />
          ) : (
            <div className="space-y-2.5">
              {snapshots.slice(0, 8).map((s) => (
                <div
                  key={s.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">
                      {new Date(s.date).toLocaleDateString()}
                    </p>
                    <p className="text-[11px] text-faint">
                      {s.headcount} headcount · {s.hires_month} hires ·{" "}
                      {s.exits_month} exits
                    </p>
                  </div>
                  <Badge tone={s.attrition_rate > 10 ? "warning" : "success"}>
                    {s.attrition_rate}% attrition
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={showPlan}
        onClose={() => setShowPlan(false)}
        title="New workforce plan"
      >
        <div className="space-y-3">
          <Input
            label="Title"
            value={plan.title ?? ""}
            onChange={(e) => setPlan({ ...plan, title: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Department"
              value={plan.department ?? ""}
              onChange={(e) => setPlan({ ...plan, department: e.target.value })}
            />
            <Select
              label="Horizon"
              options={[
                { value: "quarter", label: "Quarter" },
                { value: "year", label: "Year" },
                { value: "multi_year", label: "Multi-year" },
              ]}
              value={plan.horizon ?? ""}
              onChange={(e) => setPlan({ ...plan, horizon: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Headcount target"
              type="number"
              value={plan.headcount_target ?? "1"}
              onChange={(e) =>
                setPlan({ ...plan, headcount_target: e.target.value })
              }
            />
            <Input
              label="Budget"
              type="number"
              value={plan.budget ?? ""}
              onChange={(e) => setPlan({ ...plan, budget: e.target.value })}
            />
          </div>
          <Input
            label="Skill needs (comma separated)"
            value={plan.skill_needs ?? ""}
            onChange={(e) => setPlan({ ...plan, skill_needs: e.target.value })}
          />
          <Textarea
            label="Notes"
            value={plan.notes ?? ""}
            onChange={(e) => setPlan({ ...plan, notes: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowPlan(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onPlan({
                  ...plan,
                  headcount_target: Number(plan.headcount_target ?? 1),
                  budget: Number(plan.budget ?? 0),
                  skill_needs: (plan.skill_needs ?? "")
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                });
                setShowPlan(false);
                setPlan({});
              }}
            >
              Create plan
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showCandidate}
        onClose={() => setShowCandidate(false)}
        title="Add succession candidate"
      >
        <div className="space-y-3">
          <Input
            label="Position title"
            value={candidate.position_title ?? ""}
            onChange={(e) =>
              setCandidate({ ...candidate, position_title: e.target.value })
            }
          />
          <Select
            label="Candidate"
            options={employees}
            value={candidate.candidate_employee_id ?? ""}
            onChange={(e) =>
              setCandidate({
                ...candidate,
                candidate_employee_id: e.target.value,
              })
            }
          />
          <Input
            label="Readiness (%)"
            type="number"
            value={candidate.readiness ?? "0"}
            onChange={(e) =>
              setCandidate({ ...candidate, readiness: e.target.value })
            }
          />
          <Textarea
            label="Rationale"
            value={candidate.rationale ?? ""}
            onChange={(e) =>
              setCandidate({ ...candidate, rationale: e.target.value })
            }
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCandidate(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onCandidate({
                  ...candidate,
                  readiness: Number(candidate.readiness ?? 0),
                });
                setShowCandidate(false);
                setCandidate({});
              }}
            >
              Add candidate
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Wellbeing

function WellbeingTab({
  overview,
  busy,
  onCheckIn,
}: {
  overview: WellbeingOverview | null;
  busy: boolean;
  onCheckIn: (payload: Record<string, unknown>) => void;
}) {
  const [showCheckIn, setShowCheckIn] = useState(false);
  const [metrics, setMetrics] = useState<Record<string, string>>({});

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Check-ins"
          value={overview?.total_checks ?? 0}
          hint="All time"
          icon={HeartPulse}
        />
        <StatCard
          label="Low Risk"
          value={overview?.low ?? 0}
          icon={HeartPulse}
        />
        <StatCard
          label="Medium Risk"
          value={overview?.medium ?? 0}
          icon={HeartPulse}
        />
        <StatCard
          label="At-Risk People"
          value={overview?.at_risk_employees ?? 0}
          hint="Latest check-in high risk"
          icon={HeartPulse}
        />
      </div>

      <Button loading={busy} onClick={() => setShowCheckIn(true)}>
        Weekly check-in
      </Button>

      <Card
        title="Latest High-Risk Checks"
        subtitle="Follow up with these teammates"
      >
        {!overview || overview.latest_high.length === 0 ? (
          <EmptyState
            title="No high-risk check-ins"
            description="Team members showing sustained high workload signals appear here."
          />
        ) : (
          <div className="space-y-2.5">
            {overview.latest_high.map((c) => (
              <div key={c.id} className="rounded-xl border border-line p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[13px] font-semibold text-ink">
                    {c.employee_name}
                  </p>
                  <Badge tone="danger">{c.risk_level}</Badge>
                </div>
                <p className="mt-1 text-[11px] text-faint">
                  {new Date(c.check_date).toLocaleDateString()}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.signals.map((s, i) => (
                    <Badge key={i} tone="warning">
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal
        open={showCheckIn}
        onClose={() => setShowCheckIn(false)}
        title="Weekly wellbeing check-in"
        description="Workload & engagement signals — not a health check."
      >
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Meeting hours"
              type="number"
              value={metrics.meeting_hours ?? ""}
              onChange={(e) =>
                setMetrics({ ...metrics, meeting_hours: e.target.value })
              }
            />
            <Input
              label="Open tasks"
              type="number"
              value={metrics.task_load ?? ""}
              onChange={(e) =>
                setMetrics({ ...metrics, task_load: e.target.value })
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Learning load"
              type="number"
              value={metrics.learning_load ?? "0"}
              onChange={(e) =>
                setMetrics({ ...metrics, learning_load: e.target.value })
              }
            />
            <Input
              label="Leave balance (days)"
              type="number"
              value={metrics.leave_balance_days ?? ""}
              onChange={(e) =>
                setMetrics({ ...metrics, leave_balance_days: e.target.value })
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Recognitions"
              type="number"
              value={metrics.recognitions ?? "0"}
              onChange={(e) =>
                setMetrics({ ...metrics, recognitions: e.target.value })
              }
            />
            <Input
              label="Engagement (0-5)"
              type="number"
              value={metrics.engagement ?? "3"}
              onChange={(e) =>
                setMetrics({ ...metrics, engagement: e.target.value })
              }
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowCheckIn(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onCheckIn({
                  metrics: Object.fromEntries(
                    Object.entries(metrics).map(([k, v]) => [
                      k,
                      Number(v ?? 0),
                    ]),
                  ),
                });
                setShowCheckIn(false);
                setMetrics({});
              }}
            >
              Submit check-in
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ Payroll

function PayrollTab({
  overview,
  providers,
  runs,
  canManage,
  busy,
  onProvider,
  onToggleProvider,
  onRun,
  onSynced,
  onFailed,
}: {
  overview: PayrollOverview | null;
  providers: PayrollProvider[];
  runs: PayrollRun[];
  canManage: boolean;
  busy: boolean;
  onProvider: (payload: Record<string, unknown>) => void;
  onToggleProvider: (id: string, active: boolean) => void;
  onRun: (payload: Record<string, unknown>) => void;
  onSynced: (id: string, ref?: string) => void;
  onFailed: (id: string) => void;
}) {
  const [showProvider, setShowProvider] = useState(false);
  const [showRun, setShowRun] = useState(false);
  const [provider, setProvider] = useState<Record<string, string>>({});
  const [run, setRun] = useState<Record<string, string>>({});

  const providerOptions = providers.map((p) => ({
    value: p.id,
    label: p.name,
  }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Providers"
          value={overview?.providers ?? 0}
          hint={`${overview?.active_providers ?? 0} active`}
          icon={Building2}
        />
        <StatCard
          label="Runs"
          value={overview?.runs.total ?? 0}
          hint={`${overview?.runs.synced ?? 0} synced`}
          icon={BarChart3}
        />
        <StatCard
          label="Pending"
          value={overview?.runs.pending ?? 0}
          icon={Clock}
        />
        <StatCard
          label="Latest Gross"
          value={fmtMoney(overview?.latest_synced_gross)}
          hint="Latest synced run"
          icon={Banknote}
        />
      </div>

      {canManage && (
        <div className="flex flex-wrap gap-2">
          <Button loading={busy} onClick={() => setShowProvider(true)}>
            Add provider
          </Button>
          <Button
            variant="secondary"
            loading={busy}
            onClick={() => setShowRun(true)}
          >
            Record run
          </Button>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Providers" subtitle="External payroll systems">
          {providers.length === 0 ? (
            <EmptyState
              title="No providers"
              description="Configure an external payroll provider reference."
            />
          ) : (
            <div className="space-y-2.5">
              {providers.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-line p-3"
                >
                  <div>
                    <p className="text-[13px] font-medium text-ink">{p.name}</p>
                    <p className="text-[11px] text-faint">{p.provider}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={p.is_active ? "success" : "neutral"}>
                      {p.is_active ? "Active" : "Inactive"}
                    </Badge>
                    {canManage && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onToggleProvider(p.id, !p.is_active)}
                      >
                        {p.is_active ? "Deactivate" : "Activate"}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Payroll Runs" subtitle="External run references">
          {runs.length === 0 ? (
            <EmptyState
              title="No runs"
              description="Recorded payroll runs will appear here."
            />
          ) : (
            <div className="space-y-2.5">
              {runs.slice(0, 12).map((r) => (
                <div key={r.id} className="rounded-xl border border-line p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-[13px] font-medium text-ink">
                        {r.provider_name ?? "Payroll"} ·{" "}
                        {r.period_start
                          ? new Date(r.period_start).toLocaleDateString()
                          : "—"}{" "}
                        →{" "}
                        {r.period_end
                          ? new Date(r.period_end).toLocaleDateString()
                          : "—"}
                      </p>
                      <p className="text-[11px] text-faint">
                        {r.employee_count} employees ·{" "}
                        {fmtMoney(r.gross_amount)} · ref {r.reference_id ?? "—"}
                      </p>
                    </div>
                    <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                  </div>
                  {canManage && r.status === "pending" && (
                    <div className="mt-2 flex gap-2">
                      <Button
                        size="sm"
                        loading={busy}
                        onClick={() => onSynced(r.id)}
                      >
                        Mark synced
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={busy}
                        onClick={() => onFailed(r.id)}
                      >
                        Mark failed
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={showProvider}
        onClose={() => setShowProvider(false)}
        title="Add payroll provider"
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={provider.name ?? ""}
            onChange={(e) => setProvider({ ...provider, name: e.target.value })}
          />
          <Select
            label="Provider"
            options={[
              { value: "adp", label: "ADP" },
              { value: "gusto", label: "Gusto" },
              { value: "workday", label: "Workday" },
              { value: "oracle", label: "Oracle" },
              { value: "sap", label: "SAP" },
              { value: "local", label: "Local" },
            ]}
            value={provider.provider ?? ""}
            onChange={(e) =>
              setProvider({ ...provider, provider: e.target.value })
            }
          />
          <Textarea
            label="Config (JSON)"
            value={provider.config ?? ""}
            onChange={(e) =>
              setProvider({ ...provider, config: e.target.value })
            }
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowProvider(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onProvider({
                  ...provider,
                  config: provider.config
                    ? JSON.parse(provider.config || "{}")
                    : {},
                });
                setShowProvider(false);
                setProvider({});
              }}
            >
              Add provider
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={showRun}
        onClose={() => setShowRun(false)}
        title="Record payroll run"
      >
        <div className="space-y-3">
          <Select
            label="Provider"
            options={providerOptions}
            value={run.provider_id ?? ""}
            onChange={(e) => setRun({ ...run, provider_id: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Period start"
              type="date"
              value={run.period_start ?? ""}
              onChange={(e) => setRun({ ...run, period_start: e.target.value })}
            />
            <Input
              label="Period end"
              type="date"
              value={run.period_end ?? ""}
              onChange={(e) => setRun({ ...run, period_end: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Employee count"
              type="number"
              value={run.employee_count ?? ""}
              onChange={(e) =>
                setRun({ ...run, employee_count: e.target.value })
              }
            />
            <Input
              label="Gross amount"
              type="number"
              value={run.gross_amount ?? ""}
              onChange={(e) => setRun({ ...run, gross_amount: e.target.value })}
            />
          </div>
          <Input
            label="External reference id"
            value={run.reference_id ?? ""}
            onChange={(e) => setRun({ ...run, reference_id: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowRun(false)}>
              Cancel
            </Button>
            <Button
              loading={busy}
              onClick={() => {
                onRun({
                  ...run,
                  employee_count: Number(run.employee_count ?? 0),
                  gross_amount: Number(run.gross_amount ?? 0),
                });
                setShowRun(false);
                setRun({});
              }}
            >
              Record run
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ------------------------------------------------------------------ HR AI

function AiTab({
  answer,
  question,
  setQuestion,
  busy,
  onAsk,
}: {
  answer: HrAiAnswer | null;
  question: string;
  setQuestion: (v: string) => void;
  busy: boolean;
  onAsk: () => void;
}) {
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Card
        title="HR AI Companion"
        subtitle="Ask about your workforce — leave, promotions, attrition, hiring needs, compliance and more."
      >
        <div className="flex gap-2">
          <Input
            placeholder="e.g. Who is ready for promotion? How many people are on leave? What is our attrition?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onAsk();
            }}
          />
          <Button loading={busy} onClick={onAsk}>
            <Send className="h-3.5 w-3.5" /> Ask
          </Button>
        </div>
        {answer && (
          <div className="mt-4 rounded-xl border border-line bg-surface p-4">
            <p className="text-sm leading-relaxed text-ink">
              {answer.answer || answer.summary}
            </p>
            {answer.context && answer.context.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {answer.context.map((c) => (
                  <Badge key={c} tone="brand">
                    {c}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
