"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { KeyRound, Network, Plus, ShieldCheck, Stamp, Trash2, UserCog, XCircle } from "lucide-react";

import {
  createApprovalPolicy,
  createGovernanceAssignment,
  createGovernanceDelegation,
  createGovernanceScope,
  deleteGovernanceScope,
  getEffectivePermissions,
  listApprovalPolicies,
  listEmployees,
  listGovernanceAssignments,
  listGovernanceDelegations,
  listGovernanceScopes,
  listRoles,
  removeGovernanceAssignment,
  revokeGovernanceDelegation,
  updateApprovalPolicy,
} from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type {
  ApprovalPolicy,
  EffectivePermissions,
  EmployeeSummary,
  GovernanceAssignment,
  GovernanceDelegation,
  GovernanceScope,
  Role,
} from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { titleCase } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

const SCOPE_TYPES = ["organization", "business_unit", "region", "department", "team", "project"];
const DELEGATABLE_PERMISSIONS = [
  "projects:manage",
  "tasks:manage",
  "risks:manage",
  "approvals:manage",
  "goals:manage",
  "calendar:manage",
  "meetings:manage",
  "knowledge:manage",
  "communication:manage",
  "crm:manage",
  "finance:manage",
  "hr:manage",
  "payroll:manage",
  "governance:manage",
  "employees:manage",
  "department:manage",
  "team:manage",
];

const TABS = [
  { key: "scopes", label: "Scopes" },
  { key: "members", label: "Scoped Roles" },
  { key: "delegations", label: "Delegations" },
  { key: "policies", label: "Approval Policies" },
  { key: "effective", label: "Effective Permissions" },
];

export default function GovernancePage() {
  return (
    <Suspense fallback={null}>
      <GovernanceContent />
    </Suspense>
  );
}

function GovernanceContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.GOVERNANCE_MANAGE);

  const [tab, setTab] = useState("scopes");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [scopes, setScopes] = useState<GovernanceScope[]>([]);
  const [assignments, setAssignments] = useState<GovernanceAssignment[]>([]);
  const [delegations, setDelegations] = useState<GovernanceDelegation[]>([]);
  const [policies, setPolicies] = useState<ApprovalPolicy[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [employees, setEmployees] = useState<EmployeeSummary[]>([]);

  const [scopeModal, setScopeModal] = useState(false);
  const [assignModal, setAssignModal] = useState(false);
  const [delegateModal, setDelegateModal] = useState(false);
  const [policyModal, setPolicyModal] = useState(false);
  const [busy, setBusy] = useState(false);

  const emptyScopeForm = { name: "", scope_type: "department", parent_id: "" };
  const emptyAssignForm = { user_id: "", role_id: "", scope_id: "" };
  const emptyDelegateForm = {
    granted_to_user: "",
    permission_code: "",
    scope_id: "",
    reason: "",
    starts_at: "",
    expires_at: "",
  };
  const emptyPolicyForm = {
    name: "",
    approval_type: "other",
    description: "",
    required_permission: "",
    scope_id: "",
    self_approval_allowed: false,
  };

  const [scopeForm, setScopeForm] = useState(emptyScopeForm);
  const [assignForm, setAssignForm] = useState(emptyAssignForm);
  const [delegateForm, setDelegateForm] = useState(emptyDelegateForm);
  const [policyForm, setPolicyForm] = useState(emptyPolicyForm);

  const [effectiveUserId, setEffectiveUserId] = useState("");
  const [effectiveScopeId, setEffectiveScopeId] = useState("");
  const [effective, setEffective] = useState<EffectivePermissions | null>(null);

  const loadSeq = useRef(0);

  async function load() {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError(null);
    try {
      const [scopeList, assignList, delegList, policyList, roleList, empList] = await Promise.all([
        listGovernanceScopes(),
        listGovernanceAssignments(),
        listGovernanceDelegations(),
        listApprovalPolicies(),
        listRoles(),
        listEmployees({ page_size: 200 }),
      ]);
      if (seq !== loadSeq.current) return;
      setScopes(scopeList);
      setAssignments(assignList);
      setDelegations(delegList);
      setPolicies(policyList);
      setRoles(roleList);
      setEmployees(empList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load governance");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    const seq = ++loadSeq.current;
    try {
      const [scopeList, assignList, delegList, policyList, roleList, empList] = await Promise.all([
        listGovernanceScopes(),
        listGovernanceAssignments(),
        listGovernanceDelegations(),
        listApprovalPolicies(),
        listRoles(),
        listEmployees({ page_size: 200 }),
      ]);
      if (seq !== loadSeq.current) return;
      setScopes(scopeList);
      setAssignments(assignList);
      setDelegations(delegList);
      setPolicies(policyList);
      setRoles(roleList);
      setEmployees(empList);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to refresh");
    }
  }

  const scopeById = useMemo(() => new Map(scopes.map((s) => [s.id, s])), [scopes]);
  const employeeById = useMemo(() => new Map(employees.map((e) => [e.id, e])), [employees]);
  const employeeByUserId = useMemo(
    () => new Map(employees.filter((e) => e.user_id).map((e) => [e.user_id as string, e])),
    [employees]
  );
  const roleById = useMemo(() => new Map(roles.map((r) => [r.id, r])), [roles]);

  function userIdFor(employeeId: string): string | null {
    return employeeById.get(employeeId)?.user_id ?? null;
  }

  function memberWithAccount(employeeId: string): string | null {
    const uid = userIdFor(employeeId);
    if (!uid) {
      toastError("Selected member has no account yet — invite them first");
      return null;
    }
    return uid;
  }

  function scopeLabel(id: string | null): string {
    if (!id) return "Organization-wide";
    const scope = scopeById.get(id);
    return scope ? `${scope.name} (${titleCase(scope.scope_type)})` : "Unknown scope";
  }

  function scopePath(id: string | null): string {
    if (!id) return "Organization-wide";
    const parts: string[] = [];
    let current: GovernanceScope | undefined = scopeById.get(id);
    let guard = 0;
    while (current && guard < 32) {
      parts.unshift(current.name);
      current = current.parent_id ? scopeById.get(current.parent_id) : undefined;
      guard += 1;
    }
    return parts.join(" / ");
  }

  async function handleCreateScope() {
    if (!scopeForm.name.trim()) return toastError("Name is required");
    setBusy(true);
    try {
      await createGovernanceScope({
        name: scopeForm.name.trim(),
        scope_type: scopeForm.scope_type,
        parent_id: scopeForm.parent_id || undefined,
      });
      toastSuccess("Scope created");
      setScopeModal(false);
      setScopeForm(emptyScopeForm);
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to create scope");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteScope(id: string) {
    setBusy(true);
    try {
      await deleteGovernanceScope(id);
      toastSuccess("Scope deleted");
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delete scope");
    } finally {
      setBusy(false);
    }
  }

  async function handleAssign() {
    if (!assignForm.user_id || !assignForm.role_id) return toastError("Member and role are required");
    const targetUserId = memberWithAccount(assignForm.user_id);
    if (!targetUserId) return;
    setBusy(true);
    try {
      await createGovernanceAssignment({
        user_id: targetUserId,
        role_id: assignForm.role_id,
        scope_id: assignForm.scope_id || undefined,
      });
      toastSuccess("Role assigned");
      setAssignModal(false);
      setAssignForm(emptyAssignForm);
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to assign role");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveAssignment(id: string) {
    setBusy(true);
    try {
      await removeGovernanceAssignment(id);
      toastSuccess("Assignment removed");
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to remove assignment");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelegate() {
    if (!delegateForm.granted_to_user || !delegateForm.permission_code) {
      return toastError("Delegate and permission are required");
    }
    const targetUserId = memberWithAccount(delegateForm.granted_to_user);
    if (!targetUserId) return;
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        granted_to_user: targetUserId,
        permission_code: delegateForm.permission_code,
        scope_id: delegateForm.scope_id || undefined,
        reason: delegateForm.reason.trim() || undefined,
      };
      if (delegateForm.starts_at) payload.starts_at = new Date(delegateForm.starts_at).toISOString();
      if (delegateForm.expires_at) payload.expires_at = new Date(delegateForm.expires_at).toISOString();
      await createGovernanceDelegation(payload);
      toastSuccess("Authority delegated");
      setDelegateModal(false);
      setDelegateForm(emptyDelegateForm);
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to delegate authority");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(id: string) {
    setBusy(true);
    try {
      await revokeGovernanceDelegation(id);
      toastSuccess("Delegation revoked");
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to revoke delegation");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreatePolicy() {
    if (!policyForm.name.trim() || !policyForm.required_permission.trim()) {
      return toastError("Name and required permission are required");
    }
    setBusy(true);
    try {
      await createApprovalPolicy({
        name: policyForm.name.trim(),
        approval_type: policyForm.approval_type,
        description: policyForm.description.trim() || undefined,
        required_permission: policyForm.required_permission.trim(),
        scope_id: policyForm.scope_id || undefined,
        self_approval_allowed: policyForm.self_approval_allowed,
      });
      toastSuccess("Approval policy created");
      setPolicyModal(false);
      setPolicyForm(emptyPolicyForm);
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to create policy");
    } finally {
      setBusy(false);
    }
  }

  async function handleTogglePolicy(policy: ApprovalPolicy) {
    setBusy(true);
    try {
      await updateApprovalPolicy(policy.id, { is_active: !policy.is_active });
      toastSuccess(policy.is_active ? "Policy paused" : "Policy active");
      await refresh();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to update policy");
    } finally {
      setBusy(false);
    }
  }

  async function handleEffective() {
    if (!effectiveUserId) return toastError("Select a member");
    const targetUserId = memberWithAccount(effectiveUserId);
    if (!targetUserId) return;
    setBusy(true);
    try {
      const result = await getEffectivePermissions(targetUserId, effectiveScopeId || undefined);
      setEffective(result);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Unable to evaluate permissions");
    } finally {
      setBusy(false);
    }
  }

  if (loading && scopes.length === 0) return <Spinner label="Loading governance…" />;
  if (error) return <ErrorState title="Governance unavailable" message={error} onRetry={load} />;

  const statCards = [
    { label: "Scopes", value: scopes.length, icon: Network },
    { label: "Scoped role assignments", value: assignments.length, icon: UserCog },
    { label: "Active delegations", value: delegations.filter((d) => d.status === "active").length, icon: KeyRound },
    { label: "Approval policies", value: policies.filter((p) => p.is_active).length, icon: Stamp },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <PageHeader
        title="Governance"
        description="One authorization kernel for every size — scopes, scoped roles, delegations and approval policies."
        actions={
          canManage ? (
            <Button onClick={() => setScopeModal(true)}>
              <Plus className="h-4 w-4" /> New scope
            </Button>
          ) : undefined
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {statCards.map(({ label, value, icon: Icon }) => (
          <Card key={label} className="flex items-center gap-3 p-4">
            <div className="rounded-lg bg-canvas p-2">
              <Icon className="h-4 w-4 text-accent" />
            </div>
            <div>
              <div className="text-lg font-semibold text-ink">{value}</div>
              <div className="text-xs text-faint">{label}</div>
            </div>
          </Card>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key ? "border-brand text-brand" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "scopes" && (
        <div className="space-y-2">
          {scopes.length === 0 ? (
            <EmptyState
              title="No governance scopes yet"
              description={canManage ? "Create your first scope to start scoping roles and authority." : "Nothing here yet."}
            />
          ) : (
            scopes.map((scope) => (
              <Card key={scope.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-ink">{scope.name}</span>
                    <Badge tone="neutral">{titleCase(scope.scope_type)}</Badge>
                    {scope.depth === 0 && <Badge tone="brand">Org root</Badge>}
                  </div>
                  <p className="mt-1 text-xs text-faint">{scopePath(scope.id)}</p>
                </div>
                {canManage && (
                  <Button size="sm" variant="secondary" aria-label={`Delete ${scope.name}`} onClick={() => handleDeleteScope(scope.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </Card>
            ))
          )}
        </div>
      )}

      {tab === "members" && (
        <div className="space-y-4">
          {canManage && (
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => setAssignModal(true)}>
                <UserCog className="h-4 w-4" /> Assign role
              </Button>
            </div>
          )}
          {assignments.length === 0 ? (
            <EmptyState
              title="No scoped role assignments"
              description="Assign a role at a scope — or organization-wide — to grant authority."
            />
          ) : (
            <div className="space-y-2">
              {assignments.map((a) => (
                <Card key={a.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink">{employeeByUserId.get(a.user_id)?.full_name ?? "Member"}</span>
                      <Badge tone="brand">{roleById.get(a.role_id)?.code ?? "role"}</Badge>
                      <Badge tone="neutral">{scopeLabel(a.scope_id)}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-faint">
                      Effective at {a.scope_id ? "this scope and its descendants" : "every scope in the organization"}
                    </p>
                  </div>
                  {canManage && (
                    <Button size="sm" variant="secondary" aria-label="Remove assignment" onClick={() => handleRemoveAssignment(a.id)}>
                      <XCircle className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "delegations" && (
        <div className="space-y-4">
          {canManage && (
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => setDelegateModal(true)}>
                <KeyRound className="h-4 w-4" /> Delegate authority
              </Button>
            </div>
          )}
          {delegations.length === 0 ? (
            <EmptyState
              title="No delegations"
              description="Delegate a permission you hold to a member for a fixed window."
            />
          ) : (
            <div className="space-y-2">
              {delegations.map((d) => (
                <Card key={d.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink">{employeeByUserId.get(d.granted_to_user)?.full_name ?? "Member"}</span>
                      <Badge tone="brand">{d.permission_code}</Badge>
                      <Badge tone={d.status === "active" ? "success" : "neutral"}>{titleCase(d.status)}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-faint">
                      {scopeLabel(d.resource_id)} · {d.expires_at ? `expires ${new Date(d.expires_at).toLocaleDateString()}` : "no expiry"}
                      {d.reason ? ` · ${d.reason}` : ""}
                    </p>
                  </div>
                  {canManage && d.status === "active" && (
                    <Button size="sm" variant="secondary" onClick={() => handleRevoke(d.id)}>
                      Revoke
                    </Button>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "policies" && (
        <div className="space-y-4">
          {canManage && (
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => setPolicyModal(true)}>
                <Stamp className="h-4 w-4" /> New policy
              </Button>
            </div>
          )}
          {policies.length === 0 ? (
            <EmptyState
              title="No approval policies"
              description="Create a policy to gate who may decide approvals of a given type."
            />
          ) : (
            <div className="space-y-2">
              {policies.map((p) => (
                <Card key={p.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink">{p.name}</span>
                      <Badge tone="neutral">{titleCase(p.approval_type)}</Badge>
                      <Badge tone={p.is_active ? "success" : "neutral"}>{p.is_active ? "Active" : "Paused"}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-faint">
                      Decider needs <span className="font-medium text-ink/70">{p.required_permission}</span> at {scopeLabel(p.scope_id)}
                      {p.self_approval_allowed ? " · self-approval allowed" : " · self-approval denied"}
                    </p>
                  </div>
                  {canManage && (
                    <Button size="sm" variant="secondary" onClick={() => handleTogglePolicy(p)}>
                      {p.is_active ? "Pause" : "Activate"}
                    </Button>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "effective" && (
        <Card className="space-y-4 p-5">
          <div className="grid gap-3 md:grid-cols-3">
            <Select
              aria-label="Member"
              label="Member"
              value={effectiveUserId}
              onChange={(event) => setEffectiveUserId(event.target.value)}
              placeholder="Select a member"
              options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
            />
            <Select
              aria-label="Scope context"
              label="Scope context"
              value={effectiveScopeId}
              onChange={(event) => setEffectiveScopeId(event.target.value)}
              placeholder="Organization-wide"
              options={scopes.map((s) => ({ value: s.id, label: s.name }))}
            />
            <div className="flex items-end">
              <Button onClick={handleEffective} disabled={busy || !effectiveUserId}>
                {busy ? "Evaluating…" : "Evaluate"}
              </Button>
            </div>
          </div>
          {effective && (
            <div className="rounded-lg border border-line p-4">
              <p className="text-sm text-faint">
                {employeeByUserId.get(effective.user_id)?.full_name ?? "Member"} at{" "}
                <span className="font-medium text-ink/70">{effective.scope_id ? scopePath(effective.scope_id) : "organization-wide"}</span> —{" "}
                {effective.permissions.length} permissions
              </p>
              <div className="mt-3 flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
                {effective.permissions.map((code) => (
                  <Badge key={code} tone="neutral">
                    {code}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      <Modal
        open={scopeModal}
        onClose={() => setScopeModal(false)}
        title="Create governance scope"
        description="A scope anchors authority — roles and delegations apply at the scope and its descendants."
        footer={
          <>
            <Button variant="secondary" onClick={() => setScopeModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateScope} disabled={busy}>
              {busy ? "Creating…" : "Create scope"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <Input label="Name" name="scope-name" value={scopeForm.name} onChange={(event) => setScopeForm({ ...scopeForm, name: event.target.value })} placeholder="e.g. EMEA Operations" />
          </div>
          <Select
            aria-label="Scope type"
            label="Type"
            value={scopeForm.scope_type}
            onChange={(event) => setScopeForm({ ...scopeForm, scope_type: event.target.value })}
            options={SCOPE_TYPES.map((t) => ({ value: t, label: titleCase(t) }))}
          />
          <Select
            aria-label="Parent scope"
            label="Parent scope"
            value={scopeForm.parent_id}
            onChange={(event) => setScopeForm({ ...scopeForm, parent_id: event.target.value })}
            placeholder="None (organization root)"
            options={scopes
              .filter((s) => s.scope_type !== "project")
              .map((s) => ({ value: s.id, label: s.name }))}
          />
        </div>
      </Modal>

      <Modal
        open={assignModal}
        onClose={() => setAssignModal(false)}
        title="Assign role"
        description="The role grants its permissions at the chosen scope — or organization-wide when no scope is selected."
        footer={
          <>
            <Button variant="secondary" onClick={() => setAssignModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleAssign} disabled={busy}>
              {busy ? "Assigning…" : "Assign role"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            aria-label="Member"
            label="Member"
            value={assignForm.user_id}
            onChange={(event) => setAssignForm({ ...assignForm, user_id: event.target.value })}
            placeholder="Select a member"
            options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
          />
          <Select
            aria-label="Role"
            label="Role"
            value={assignForm.role_id}
            onChange={(event) => setAssignForm({ ...assignForm, role_id: event.target.value })}
            placeholder="Select a role"
            options={roles.map((r) => ({ value: r.id, label: `${r.code} — ${r.name}` }))}
          />
          <Select
            aria-label="Scope"
            label="Scope"
            value={assignForm.scope_id}
            onChange={(event) => setAssignForm({ ...assignForm, scope_id: event.target.value })}
            placeholder="Organization-wide"
            options={scopes.map((s) => ({ value: s.id, label: s.name }))}
          />
        </div>
      </Modal>

      <Modal
        open={delegateModal}
        onClose={() => setDelegateModal(false)}
        title="Delegate authority"
        description="Grant a permission you hold to another member, optionally for a window and a scope."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDelegateModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleDelegate} disabled={busy}>
              {busy ? "Delegating…" : "Delegate authority"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Select
            aria-label="Delegate"
            label="Delegate"
            value={delegateForm.granted_to_user}
            onChange={(event) => setDelegateForm({ ...delegateForm, granted_to_user: event.target.value })}
            placeholder="Select a member"
            options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
          />
          <Select
            aria-label="Permission"
            label="Permission"
            value={delegateForm.permission_code}
            onChange={(event) => setDelegateForm({ ...delegateForm, permission_code: event.target.value })}
            placeholder="Select a permission"
            options={DELEGATABLE_PERMISSIONS.map((p) => ({ value: p, label: p }))}
          />
          <Select
            aria-label="Delegation scope"
            label="Scope"
            value={delegateForm.scope_id}
            onChange={(event) => setDelegateForm({ ...delegateForm, scope_id: event.target.value })}
            placeholder="Organization-wide"
            options={scopes.map((s) => ({ value: s.id, label: s.name }))}
          />
          <div>
            <label className="label">Reason</label>
            <Textarea aria-label="Delegation reason" value={delegateForm.reason} onChange={(event) => setDelegateForm({ ...delegateForm, reason: event.target.value })} rows={2} placeholder="Why is this authority being delegated?" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Input label="Starts at" name="delegation-starts" type="datetime-local" value={delegateForm.starts_at} onChange={(event) => setDelegateForm({ ...delegateForm, starts_at: event.target.value })} />
            </div>
            <div>
              <Input label="Expires at" name="delegation-expires" type="datetime-local" value={delegateForm.expires_at} onChange={(event) => setDelegateForm({ ...delegateForm, expires_at: event.target.value })} />
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={policyModal}
        onClose={() => setPolicyModal(false)}
        title="Create approval policy"
        description="Approvals of this type may only be decided by holders of the required permission at the policy's scope."
        footer={
          <>
            <Button variant="secondary" onClick={() => setPolicyModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreatePolicy} disabled={busy}>
              {busy ? "Creating…" : "Create policy"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <Input label="Name" name="policy-name" value={policyForm.name} onChange={(event) => setPolicyForm({ ...policyForm, name: event.target.value })} placeholder="e.g. Contract approval requires legal" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Input label="Approval type" name="policy-type" value={policyForm.approval_type} onChange={(event) => setPolicyForm({ ...policyForm, approval_type: event.target.value })} placeholder="other" />
            </div>
            <div>
              <Input label="Required permission" name="policy-perm" value={policyForm.required_permission} onChange={(event) => setPolicyForm({ ...policyForm, required_permission: event.target.value })} placeholder="e.g. finance:manage" />
            </div>
          </div>
          <Select
            aria-label="Policy scope"
            label="Scope"
            value={policyForm.scope_id}
            onChange={(event) => setPolicyForm({ ...policyForm, scope_id: event.target.value })}
            placeholder="Organization-wide"
            options={scopes.map((s) => ({ value: s.id, label: s.name }))}
          />
          <div>
            <label className="label">Description</label>
            <Textarea aria-label="Policy description" value={policyForm.description} onChange={(event) => setPolicyForm({ ...policyForm, description: event.target.value })} rows={2} />
          </div>
          <label className="flex items-center gap-2 text-sm text-ink/80">
            <input
              type="checkbox"
              checked={policyForm.self_approval_allowed}
              onChange={(event) => setPolicyForm({ ...policyForm, self_approval_allowed: event.target.checked })}
              className="h-4 w-4"
            />
            Allow self-approval by the requester
          </label>
        </div>
      </Modal>
    </div>
  );
}
