"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Building2,
  Check,
  Copy,
  CreditCard,
  Plus,
  RefreshCw,
  Shield,
  Trash2,
  UserPlus,
  Users,
  X,
  Download,
} from "lucide-react";

import { api } from "@/lib/api";
import {
  AuditLog,
  Invitation,
  Organization,
  OrganizationSettings,
  OrganizationStats,
  Paginated,
  Permission,
  Role,
  User,
} from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { useFetch } from "@/hooks/useFetch";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Tabs } from "@/components/ui/Tabs";
import { Modal } from "@/components/ui/Modal";
import { MenuItem, Dropdown } from "@/components/ui/Dropdown";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import { GroupRoleMappingTab } from "./components/GroupRoleMappingTab";
import { IntegrationsTab } from "./components/IntegrationsTab";

const TABS = [
  { id: "organization", label: "Organization" },
  { id: "members", label: "Members" },
  { id: "roles", label: "Roles" },
  { id: "group-role-mapping", label: "Group Mapping" },
  { id: "integrations", label: "Integrations" },
  { id: "billing", label: "Billing" },
  { id: "audit", label: "Audit log" },
];

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsContent />
    </Suspense>
  );
}

function SettingsContent() {
  const searchParams = useSearchParams();
  const { can } = useAuth();
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState(
    TABS.some((t) => t.id === tabParam) ? tabParam! : "organization",
  );

  useEffect(() => {
    const next = searchParams.get("tab");
    if (next && TABS.some((t) => t.id === next)) setTab(next);
  }, [searchParams]);

  const canViewMembers = can("users:invite") || can("users:manage");
  const canViewRoles = can("roles:manage");
  const canViewAudit = can("audit:read");
  const canViewIntegrations = can("integrations:manage");
  const tabs = TABS.filter(
    (t) =>
      t.id === "organization" ||
      (t.id === "members" && canViewMembers) ||
      (t.id === "roles" && canViewRoles) ||
      (t.id === "group-role-mapping" && canViewRoles) ||
      (t.id === "integrations" && canViewIntegrations) ||
      (t.id === "audit" && canViewAudit),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink">
            Settings
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            Manage your company configuration.
          </p>
        </div>
        <Tabs tabs={tabs} active={tab} onChange={setTab} />
      </div>

      {tab === "organization" && <OrganizationTab />}
      {tab === "members" && canViewMembers && <MembersTab />}
      {tab === "roles" && canViewRoles && <RolesTab />}
      {tab === "billing" && <BillingTab />}
      {tab === "audit" && canViewAudit && <AuditTab />}
      {tab === "group-role-mapping" && canViewRoles && <GroupRoleMappingTab />}
      {tab === "integrations" && canViewIntegrations && <IntegrationsTab />}
    </div>
  );
}

/* ---------------------------------- Organization ---------------------------------- */

function OrganizationTab() {
  const { organization, updateOrganization, can } = useAuth();
  const manager = can("organization:update");
  const {
    data: settings,
    loading: settingsLoading,
    error: settingsError,
  } = useFetch<OrganizationSettings>("/organizations/me/settings");

  const [form, setForm] = useState({
    name: organization?.name ?? "",
    industry: organization?.industry ?? "",
    description: organization?.description ?? "",
    country: organization?.country ?? "",
    timezone: organization?.timezone ?? "UTC",
    language: organization?.language ?? "en",
    currency: organization?.currency ?? "USD",
    domain: organization?.domain ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [brandColor, setBrandColor] = useState(
    organization?.brand_primary_color ?? "#6366f1",
  );
  const [brandSaving, setBrandSaving] = useState(false);
  const [s, setS] = useState<OrganizationSettings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [stats, setStats] = useState<OrganizationStats | null>(null);

  useEffect(() => {
    if (settings) setS(settings);
  }, [settings]);

  useEffect(() => {
    if (!manager) return;
    api<OrganizationStats>("/organizations/me/stats")
      .then(setStats)
      .catch(() => {});
  }, [manager]);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const updated = await api<Organization>("/organizations/me", {
        method: "PATCH",
        body: {
          name: form.name,
          industry: form.industry || undefined,
          description: form.description || undefined,
          country: form.country || undefined,
          timezone: form.timezone || undefined,
          language: form.language || undefined,
          currency: form.currency || undefined,
          domain: form.domain || undefined,
        },
      });
      updateOrganization(updated);
      toastSuccess("Organization updated");
    } catch (err) {
      toastError(
        "Update failed",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setSaving(false);
    }
  }

  async function saveBranding() {
    setBrandSaving(true);
    try {
      const updated = await api<Organization>("/organizations/me/branding", {
        method: "POST",
        body: { brand_primary_color: brandColor },
      });
      updateOrganization(updated);
      toastSuccess("Branding updated");
    } catch (err) {
      toastError(
        "Update failed",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setBrandSaving(false);
    }
  }

  async function saveSettings(
    field: keyof OrganizationSettings,
    value: boolean | string | number,
  ) {
    setSavingSettings(true);
    try {
      const updated = await api<OrganizationSettings>(
        "/organizations/me/settings",
        {
          method: "PATCH",
          body: { [field]: value },
        },
      );
      setS(updated);
      toastSuccess("Settings saved");
    } catch (err) {
      toastError(
        "Update failed",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setSavingSettings(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <h2 className="flex items-center gap-2 border-b border-line px-5 py-4 text-sm font-semibold text-ink">
            <Building2 className="h-4 w-4 text-brand" /> Company profile
          </h2>
          <form onSubmit={saveProfile} className="space-y-4 p-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Company name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <Input
                label="Domain"
                placeholder="company.com"
                value={form.domain}
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
              />
              <Input
                label="Industry"
                placeholder="Software"
                value={form.industry}
                onChange={(e) => setForm({ ...form, industry: e.target.value })}
              />
              <Input
                label="Country"
                placeholder="United States"
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
              />
              <Input
                label="Timezone"
                value={form.timezone}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })}
              />
              <Input
                label="Language"
                value={form.language}
                onChange={(e) => setForm({ ...form, language: e.target.value })}
              />
              <Input
                label="Currency"
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-ink">
                Description
              </label>
              <Textarea
                rows={3}
                placeholder="What does your company do?"
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
              />
            </div>
            <div className="flex justify-end">
              <Button type="submit" loading={saving} disabled={!manager}>
                Save company profile
              </Button>
            </div>
          </form>
        </Card>

        <Card>
          <h2 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">
            Company settings
          </h2>
          {settingsError ? (
            <p className="p-5 text-[13px] text-danger">{settingsError}</p>
          ) : settingsLoading || !s ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : (
            <div className="divide-y divide-line">
              <SettingRow
                title="Allow self-registration"
                description="Let anyone join your company with the registration link."
                control={
                  <Toggle
                    checked={s.allow_employee_self_registration}
                    onChange={(v) =>
                      saveSettings("allow_employee_self_registration", v)
                    }
                    disabled={!manager}
                  />
                }
              />
              <SettingRow
                title="Require email verification"
                description="New members must verify their email before first sign-in."
                control={
                  <Toggle
                    checked={s.require_email_verification}
                    onChange={(v) =>
                      saveSettings("require_email_verification", v)
                    }
                    disabled={!manager}
                  />
                }
              />
              <SettingRow
                title="Weekly digest"
                description="Send a weekly summary of company activity to all members."
                control={
                  <Toggle
                    checked={s.weekly_digest}
                    onChange={(v) => saveSettings("weekly_digest", v)}
                    disabled={!manager}
                  />
                }
              />
              <SettingRow
                title="Announcements"
                description="Allow company-wide announcements."
                control={
                  <Toggle
                    checked={s.announcement_enabled}
                    onChange={(v) => saveSettings("announcement_enabled", v)}
                    disabled={!manager}
                  />
                }
              />
              <SettingRow
                title="Default theme"
                description="Theme new members start with."
                control={
                  <Dropdown
                    trigger={(open) => (
                      <Button variant="ghost" size="sm">
                        {s.default_theme}
                      </Button>
                    )}
                  >
                    {(close) => (
                      <>
                        {["light", "dark", "system"].map((theme) => (
                          <MenuItem
                            key={theme}
                            label={theme[0].toUpperCase() + theme.slice(1)}
                            onClick={() => {
                              saveSettings("default_theme", theme);
                              close();
                            }}
                          />
                        ))}
                      </>
                    )}
                  </Dropdown>
                }
              />
              <SettingRow
                title="Audit retention"
                description="Days to keep audit logs (30–3650)."
                control={
                  <input
                    type="number"
                    min={30}
                    max={3650}
                    className="input w-28 px-3 py-1.5 text-[13px]"
                    defaultValue={s.retention_days_audit}
                    disabled={!manager}
                    onBlur={(e) => {
                      const v = Number(e.target.value);
                      if (v >= 30 && v <= 3650 && v !== s.retention_days_audit)
                        saveSettings("retention_days_audit", v);
                    }}
                  />
                }
              />
            </div>
          )}
          {savingSettings && (
            <p className="px-5 pb-4 text-[12px] text-faint">Saving…</p>
          )}
        </Card>
      </div>

      <div className="space-y-6">
        <Card>
          <h2 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">
            Branding
          </h2>
          <div className="space-y-4 p-5">
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-ink">
                Brand color
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={brandColor}
                  onChange={(e) => setBrandColor(e.target.value)}
                  className="h-9 w-14 cursor-pointer rounded-lg border border-line bg-canvas p-1"
                  disabled={!manager}
                />
                <Input
                  value={brandColor}
                  onChange={(e) => setBrandColor(e.target.value)}
                  className="font-mono"
                />
              </div>
            </div>
            <Button
              variant="secondary"
              loading={brandSaving}
              onClick={saveBranding}
              disabled={!manager}
            >
              Apply branding
            </Button>
          </div>
        </Card>

        {stats && (
          <Card>
            <h2 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">
              Company stats
            </h2>
            <dl className="grid grid-cols-2 gap-px bg-line text-[13px]">
              <Stat title="Members" value={stats.total_users} />
              <Stat title="Active" value={stats.active_users} />
              <Stat title="Pending invites" value={stats.pending_invitations} />
              <Stat title="Roles" value={stats.roles_count} />
              <Stat title="Active sessions" value={stats.sessions_active} />
              <Stat title="Audit entries" value={stats.audit_entries} />
            </dl>
          </Card>
        )}
      </div>
    </div>
  );
}

function Stat({ title, value }: { title: string; value: number }) {
  return (
    <div className="bg-card p-4">
      <dt className="text-[12px] text-faint">{title}</dt>
      <dd className="mt-0.5 text-lg font-bold text-ink">{value}</dd>
    </div>
  );
}

function SettingRow({
  title,
  description,
  control,
}: {
  title: string;
  description: string;
  control: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4">
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-ink">{title}</p>
        <p className="mt-0.5 text-[12px] text-muted">{description}</p>
      </div>
      {control}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40 ${
        checked ? "bg-brand" : "bg-line"
      }`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-[22px]" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}

/* ------------------------------------ Members ------------------------------------ */

function MembersTab() {
  const { user } = useAuth();
  const { data, loading, error, refetch } = useFetch<Paginated<User>>(
    "/users?page_size=100",
  );
  const {
    data: invitations,
    loading: invitesLoading,
    refetch: refreshInvites,
  } = useFetch<Invitation[]>("/users/invitations");
  const { data: roles } = useFetch<Role[]>("/roles");

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState("employee");
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteResultUrl, setInviteResultUrl] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const assignableRoles =
    roles?.filter(
      (r: Role) => user?.role === "ceo" || (r.code !== "ceo" && r.code !== "admin"),
    ) ?? [];

  // Under burst load the browser sometimes cancels a request before it is sent
  // and the fetch only surfaces the failure much later. A 4s soft cap surfaces
  // it quickly; we then confirm via GET /users/invitations whether the invite
  // actually landed (the backend dedupes pending invites, so a re-POST after a
  // lost response would be safe too — resend covers that case with the URL).
  async function sendInvite(event: React.FormEvent) {
    event.preventDefault();
    setInviteError(null);
    setInviteSending(true);
    try {
      await doSendInvite(0);
      setInviteOpen(false);
      setInviteEmail("");
      setInviteName("");
      refetch();
      refreshInvites();
    } catch (err) {
      setInviteError(
        err instanceof Error ? err.message : "Unable to send invitation",
      );
    } finally {
      setInviteSending(false);
    }
  }

  async function doSendInvite(
    attempt: number,
  ): Promise<{ url: string | null }> {
    try {
      return await Promise.race([
        api<{
          invitation: Invitation;
          url: string | null;
          token: string | null;
        }>("/users/invite", {
          method: "POST",
          body: {
            email: inviteEmail,
            full_name: inviteName || undefined,
            role: inviteRole,
          },
        }).then((result) => {
          if (result.url) setInviteResultUrl(result.url);
          else
            toastSuccess(
              "Invitation sent",
              `${inviteEmail} will receive an email with a registration link.`,
            );
          return { url: result.url };
        }),
        new Promise<never>((_, reject) =>
          setTimeout(
            () =>
              reject(
                new Error(
                  "The request timed out, checking whether the invitation was sent…",
                ),
              ),
            4_000,
          ),
        ),
      ]);
    } catch (err) {
      if (attempt === 0) {
        await new Promise((resolve) => setTimeout(resolve, 300));
        try {
          const invitations = await api<Invitation[]>("/users/invitations");
          const pending = invitations.find(
            (i) => i.email === inviteEmail && i.status === "pending",
          );
          if (pending) {
            const resent = await api<{
              invitation: Invitation;
              url: string | null;
            }>(`/users/invitations/${pending.id}/resend`, { method: "POST" });
            if (resent.url) setInviteResultUrl(resent.url);
            return { url: resent.url ?? null };
          }
        } catch {
          /* if the check itself fails, fall through and retry the invite once */
        }
        return doSendInvite(1);
      }
      throw err;
    }
  }

  async function revokeInvitation(id: string) {
    if (
      !confirm(
        "Revoke this invitation? The invitee will no longer be able to join.",
      )
    )
      return;
    setBusyId(id);
    try {
      await api(`/users/invitations/${id}/revoke`, { method: "POST" });
      toastSuccess("Invitation revoked");
      refreshInvites();
    } catch (err) {
      toastError("Failed", err instanceof Error ? err.message : undefined);
    } finally {
      setBusyId(null);
    }
  }

  async function resendInvitation(id: string) {
    setBusyId(id);
    try {
      const result = await api<{
        invitation: Invitation;
        url: string | null;
        token: string | null;
      }>(`/users/invitations/${id}/resend`, { method: "POST" });
      toastSuccess("Invitation resent");
      if (result.url) setInviteResultUrl(result.url);
      refreshInvites();
    } catch (err) {
      toastError("Failed", err instanceof Error ? err.message : undefined);
    } finally {
      setBusyId(null);
    }
  }

  async function setUserStatus(target: User, status: "active" | "suspended") {
    if (target.id === user?.id) return;
    setBusyId(target.id);
    try {
      await api(`/users/${target.id}/status`, {
        method: "PATCH",
        body: { status },
      });
      toastSuccess(`${target.full_name} is now ${status}`);
      refetch();
    } catch (err) {
      toastError("Failed", err instanceof Error ? err.message : undefined);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Users className="h-4 w-4 text-brand" /> Members
            <span className="rounded-full bg-canvas px-2 py-0.5 text-[11px] text-muted">
              {data?.total ?? "…"}
            </span>
          </h2>
          <Button
            size="sm"
            onClick={() => {
              setInviteOpen(true);
              setInviteError(null);
            }}
          >
            <UserPlus className="h-4 w-4" /> Invite
          </Button>
        </div>
        {error ? (
          <ErrorState title="Could not load members" message={error} />
        ) : loading || !data ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-5 py-3 font-semibold">Member</th>
                  <th className="px-4 py-3 font-semibold">Role</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Joined</th>
                  <th className="px-5 py-3 text-right font-semibold">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((member: User) => (
                  <tr key={member.id} className="hover:bg-canvas/50">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[12px] font-semibold text-brand">
                          {member.full_name.slice(0, 1).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <p className="flex items-center gap-1.5 truncate font-medium text-ink">
                            {member.full_name}
                            {member.id === user?.id && (
                              <Badge tone="neutral">You</Badge>
                            )}
                          </p>
                          <p className="truncate text-[12px] text-faint">
                            {member.email}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        tone={member.role === "employee" ? "neutral" : "brand"}
                      >
                        {member.role}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1.5 text-[12px] ${member.status === "active" ? "text-success" : member.status === "suspended" ? "text-warning" : "text-faint"}`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${member.status === "active" ? "bg-success" : member.status === "suspended" ? "bg-warning" : "bg-faint"}`}
                        />
                        {member.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[12px] text-faint">
                      {formatDate(member.created_at)}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {member.id !== user?.id ? (
                        <Dropdown
                          trigger={(open) => (
                            <Button variant="ghost" size="sm">
                              Manage
                            </Button>
                          )}
                        >
                          {(close) => (
                            <MenuItem
                              label={
                                member.status === "suspended"
                                  ? "Reactivate"
                                  : "Suspend"
                              }
                              danger={member.status !== "suspended"}
                              onClick={() => {
                                close();
                                setUserStatus(
                                  member,
                                  member.status === "suspended"
                                    ? "active"
                                    : "suspended",
                                );
                              }}
                            />
                          )}
                        </Dropdown>
                      ) : (
                        <span className="text-[12px] text-faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">
          Pending invitations
          <span className="ml-2 rounded-full bg-canvas px-2 py-0.5 text-[11px] text-muted">
            {invitations?.filter((i: Invitation) => i.status === "pending").length ?? 0}
          </span>
        </h2>
        {invitesLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : !invitations || invitations.length === 0 ? (
          <EmptyState
            title="No invitations"
            description="Invite teammates to grow your company."
          />
        ) : (
          <ul className="divide-y divide-line">
            {invitations.map((inv: Invitation) => (
              <li key={inv.id} className="flex items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-ink">
                    {inv.email}
                    {inv.full_name ? (
                      <span className="text-muted"> · {inv.full_name}</span>
                    ) : null}
                  </p>
                  <p className="text-[12px] text-faint">
                    {inv.role} · invited {formatDate(inv.created_at)} · expires{" "}
                    {formatDate(inv.expires_at)}
                  </p>
                </div>
                <Badge tone={inv.status === "pending" ? "warning" : "neutral"}>
                  {inv.status}
                </Badge>
                {(inv.status === "pending" || inv.status === "expired") && (
                  <div className="flex items-center gap-3">
                    <button
                      className="text-[12px] font-medium text-brand hover:underline disabled:opacity-50"
                      disabled={busyId === inv.id}
                      onClick={() => resendInvitation(inv.id)}
                    >
                      Resend
                    </button>
                    {inv.status === "pending" && (
                      <button
                        className="text-[12px] font-medium text-danger hover:underline disabled:opacity-50"
                        disabled={busyId === inv.id}
                        onClick={() => revokeInvitation(inv.id)}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        title="Invite a teammate"
      >
        <form onSubmit={sendInvite} className="space-y-4">
          <p className="text-[13px] text-muted">
            They will receive a secure link to join your company. The link
            expires after 7 days.
          </p>
          {inviteError && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
              {inviteError}
            </div>
          )}
          <Input
            label="Email"
            name="email"
            type="email"
            placeholder="teammate@company.com"
            required
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
          />
          <Input
            label="Full name (optional)"
            name="full_name"
            placeholder="Grace Hopper"
            value={inviteName}
            onChange={(e) => setInviteName(e.target.value)}
          />
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-ink">
              Role
            </label>
            <Dropdown
              trigger={(open) => (
                <Button variant="ghost" className="w-full justify-between">
                  {inviteRole}
                </Button>
              )}
            >
              {(close) => (
                <>
                  {(assignableRoles.length > 0
                    ? assignableRoles
                    : [
                        {
                          id: "",
                          name: "Employee",
                          code: "employee",
                          is_system: true,
                          is_default: true,
                        },
                        {
                          id: "",
                          name: "Manager",
                          code: "manager",
                          is_system: true,
                          is_default: true,
                        },
                      ]
                  ).map((role: Role) => (
                    <MenuItem
                      key={role.code}
                      label={role.name}
                      onClick={() => {
                        setInviteRole(role.code);
                        close();
                      }}
                    />
                  ))}
                </>
              )}
            </Dropdown>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setInviteOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={inviteSending}>
              <UserPlus className="h-4 w-4" /> Send invitation
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(inviteResultUrl)}
        onClose={() => setInviteResultUrl(null)}
        title="Invitation link ready"
      >
        <div className="space-y-4">
          <p className="text-[13px] text-muted">
            Email transport is in development mode, so share this link directly
            with your teammate.
          </p>
          <div className="flex items-center gap-2 rounded-lg border border-line bg-canvas p-3">
            <code className="min-w-0 flex-1 break-all font-mono text-[12px] text-ink">
              {inviteResultUrl}
            </code>
            <button
              className="icon-btn shrink-0"
              onClick={() => {
                navigator.clipboard.writeText(inviteResultUrl!);
                toastSuccess("Copied to clipboard");
              }}
              aria-label="Copy link"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => setInviteResultUrl(null)}>Done</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

/* ------------------------------------- Roles ------------------------------------- */

function RolesTab() {
  const { data: roles, loading, error, refetch } = useFetch<Role[]>("/roles");
  const { data: permissions, loading: permsLoading } =
    useFetch<Permission[]>("/roles/permissions");

  const [createOpen, setCreateOpen] = useState(false);
  const [editRole, setEditRole] = useState<Role | null>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function openCreate() {
    setEditRole(null);
    setName("");
    setCode("");
    setDescription("");
    setSelected([]);
    setFormError(null);
    setCreateOpen(true);
  }

  function openEdit(role: Role) {
    setEditRole(role);
    setName(role.name);
    setCode(role.code);
    setDescription(role.description ?? "");
    setSelected(role.permissions.map((p) => p.id));
    setFormError(null);
    setCreateOpen(true);
  }

  async function saveRole(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (name.trim().length < 2 || code.trim().length < 2) {
      setFormError("Name and code must be at least 2 characters.");
      return;
    }
    setSaving(true);
    try {
      if (editRole) {
        await api(`/roles/${editRole.id}`, {
          method: "PATCH",
          body: {
            name: name.trim(),
            description: description.trim() || undefined,
            permission_ids: editRole.is_system ? undefined : selected,
          },
        });
        toastSuccess("Role updated");
      } else {
        await api("/roles", {
          method: "POST",
          body: {
            name: name.trim(),
            code: code
              .trim()
              .toLowerCase()
              .replace(/[^a-z0-9_]/g, "_"),
            description: description.trim() || undefined,
            permission_ids: selected,
          },
        });
        toastSuccess("Role created");
      }
      setCreateOpen(false);
      refetch();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Unable to save role");
    } finally {
      setSaving(false);
    }
  }

  async function deleteRole(role: Role) {
    if (!confirm(`Delete role "${role.name}"?`)) return;
    try {
      await api(`/roles/${role.id}`, { method: "DELETE" });
      toastSuccess("Role deleted");
      refetch();
    } catch (err) {
      toastError(
        "Delete failed",
        err instanceof Error ? err.message : undefined,
      );
    }
  }

  const groups = permissions
    ? permissions.reduce<Record<string, Permission[]>>((acc: Record<string, Permission[]>, p: Permission) => {
        (acc[p.resource] = acc[p.resource] || []).push(p);
        return acc;
      }, {})
    : {};

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Shield className="h-4 w-4 text-brand" /> Roles & permissions
          </h2>
          <Button size="sm" onClick={openCreate}>
            <Plus className="h-4 w-4" /> New role
          </Button>
        </div>
        {error ? (
          <ErrorState title="Could not load roles" message={error} />
        ) : loading || !roles ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {roles.map((role: Role) => (
              <li key={role.id} className="flex items-center gap-4 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 font-medium text-ink">
                    {role.name}
                    {role.is_system && <Badge tone="brand">System</Badge>}
                    {role.is_default && <Badge tone="brand">Default</Badge>}
                  </p>
                  <p className="mt-0.5 truncate text-[12px] text-muted">
                    <span className="font-mono">{role.code}</span>
                    {role.description ? ` · ${role.description}` : ""}
                  </p>
                  <p className="mt-0.5 text-[12px] text-faint">
                    {role.permissions.length} permissions · {role.user_count}{" "}
                    member{role.user_count === 1 ? "" : "s"}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    className="icon-btn"
                    onClick={() => openEdit(role)}
                    aria-label="Edit role"
                  >
                    <Shield className="h-4 w-4" />
                  </button>
                  {!role.is_system && (
                    <button
                      className="icon-btn hover:!text-danger"
                      onClick={() => deleteRole(role)}
                      aria-label="Delete role"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={editRole ? `Edit ${editRole.name}` : "Create role"}
      >
        <form onSubmit={saveRole} className="space-y-4">
          {formError && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[13px] text-danger">
              {formError}
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={editRole?.is_system}
            />
            <Input
              label="Code"
              required
              placeholder="ops_lead"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={Boolean(editRole)}
            />
          </div>
          <Textarea
            label="Description"
            rows={2}
            placeholder="What this role is for..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          {permsLoading || !permissions ? (
            <div className="flex justify-center py-6">
              <Spinner />
            </div>
          ) : (
            <div>
              <p className="mb-2 text-[13px] font-medium text-ink">
                Permissions{" "}
                {editRole?.is_system
                  ? "(system roles keep their permissions)"
                  : ""}
              </p>
              <div className="max-h-64 space-y-3 overflow-y-auto rounded-xl border border-line p-4">
                {Object.entries(groups as Record<string, Permission[]>).map(([resource, perms]) => (
                  <div key={resource}>
                    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
                      {resource}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {perms.map((perm) => {
                        const checked = selected.includes(perm.id);
                        return (
                          <button
                            type="button"
                            key={perm.id}
                            disabled={Boolean(editRole?.is_system)}
                            onClick={() =>
                              setSelected((prev) =>
                                checked
                                  ? prev.filter((id) => id !== perm.id)
                                  : [...prev, perm.id],
                              )
                            }
                            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] transition-colors disabled:opacity-60 ${
                              checked
                                ? "border-brand/40 bg-brand/10 text-brand"
                                : "border-line text-muted hover:border-brand/30"
                            }`}
                          >
                            {checked && <Check className="h-3 w-3" />}
                            {perm.code}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              {editRole ? "Save changes" : "Create role"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

/* ------------------------------------- Billing ------------------------------------ */
function BillingTab() {
  const { organization } = useAuth();
  const {
    data: subscription,
    loading,
    error,
    refetch,
  } = useFetch<any>("/commercial/subscription");
  const { data: invoices, loading: invoicesLoading } = useFetch<any[]>(
    "/commercial/invoices",
  );
  const [showChangePlan, setShowChangePlan] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [loadingAction, setLoadingAction] = useState(false);

  const handleChangePlan = async () => {
    if (!selectedPlan || !effectiveDate) return;
    setLoadingAction(true);
    try {
      await api("/commercial/subscription/change-plan", {
        method: "POST",
        body: { new_plan_key: selectedPlan, effective: effectiveDate },
      });
      toastSuccess(
        "Plan changed",
        `Subscription will change to ${selectedPlan} on ${effectiveDate}`,
      );
      setShowChangePlan(false);
      await refetch();
    } catch (err) {
      toastError(
        "Failed to change plan",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleCancelSubscription = async (immediate: boolean) => {
    const reason = prompt("Please provide a reason for cancellation:");
    if (!reason) return;

    setLoadingAction(true);
    try {
      await api("/commercial/subscription/cancel", {
        method: "POST",
        body: { reason, immediate },
      });
      toastSuccess(
        immediate
          ? "Subscription cancelled immediately"
          : "Subscription will cancel at period end",
      );
      await refetch();
    } catch (err) {
      toastError(
        "Failed to cancel subscription",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleRenewSubscription = async () => {
    setLoadingAction(true);
    try {
      await api("/commercial/subscription/renew", { method: "POST" });
      toastSuccess("Subscription renewed");
      await refetch();
    } catch (err) {
      toastError(
        "Failed to renew subscription",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleGenerateInvoice = async () => {
    setLoadingAction(true);
    try {
      const now = new Date();
      const periodStart = new Date(now.getFullYear(), now.getMonth(), 1);
      const periodEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0);
      await api("/commercial/invoices/generate", {
        method: "POST",
        body: {
          period_start: periodStart.toISOString(),
          period_end: periodEnd.toISOString(),
        },
      });
      toastSuccess("Invoice generated");
    } catch (err) {
      toastError(
        "Failed to generate invoice",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  if (!organization) return null;

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  if (error) {
    return <ErrorState title="Could not load subscription" message={error} />;
  }

  if (!subscription) {
    return (
      <Card>
        <div className="p-6 text-center">
          <EmptyState
            icon={CreditCard}
            title="No active subscription"
            description="Create a subscription to access billing features."
          />
          <Button onClick={() => setShowChangePlan(true)} className="mt-4">
            <Plus className="h-4 w-4 mr-2" /> Create Subscription
          </Button>
        </div>
      </Card>
    );
  }

  const isTrial =
    subscription.trial_ends_at &&
    new Date(subscription.trial_ends_at) > new Date();
  const statusTone = isTrial
    ? "warning"
    : subscription.state === "active"
      ? "success"
      : subscription.state === "cancelled"
        ? "danger"
        : subscription.state === "past_due"
          ? "danger"
          : "neutral";
  const statusLabel = isTrial ? "Trial" : subscription.state;

  const trialEndsContent =
    subscription.trial_ends_at &&
    new Date(subscription.trial_ends_at) > new Date() ? (
      <div>
        <p className="text-sm text-muted">Trial Ends</p>
        <p className="font-medium text-ink">
          {formatDate(subscription.trial_ends_at)}
        </p>
      </div>
    ) : null;

  const cancelAtPeriodEndButton =
    subscription.state === "active" && !isTrial ? (
      <Button
        variant="secondary"
        onClick={() => handleCancelSubscription(false)}
        disabled={loadingAction}
      >
        <X className="h-4 w-4 mr-2" /> Cancel at Period End
      </Button>
    ) : null;

  const cancelImmediatelyButton =
    subscription.state === "active" && !isTrial ? (
      <Button
        variant="secondary"
        onClick={() => handleCancelSubscription(true)}
        disabled={loadingAction}
      >
        <X className="h-4 w-4 mr-2" /> Cancel Immediately
      </Button>
    ) : null;

  const renewSubscriptionButton =
    subscription.state === "cancelled" ? (
      <Button
        variant="secondary"
        onClick={handleRenewSubscription}
        disabled={loadingAction}
      >
        <RefreshCw className="h-4 w-4 mr-2" /> Renew Subscription
      </Button>
    ) : null;

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">
            Current Subscription
          </h2>
          <Badge tone={statusTone}>{statusLabel}</Badge>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-sm text-muted">Plan</p>
              <p className="font-medium text-ink">
                {subscription.plan_name
                  ? `${subscription.plan_name} (${subscription.plan_tier})`
                  : "Custom"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">Billing Interval</p>
              <p className="font-medium text-ink capitalize">
                {subscription.billing_interval}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">Price</p>
              <p className="font-medium text-ink">
                ${(subscription.price_cents / 100).toFixed(2)}{" "}
                {subscription.currency}/{subscription.billing_interval}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">Status</p>
              <p className="font-medium text-ink">{subscription.state}</p>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 pt-4 border-t border-line">
            <div>
              <p className="text-sm text-muted">Current Period</p>
              <p className="font-medium text-ink">
                {subscription.current_period_start
                  ? formatDate(subscription.current_period_start)
                  : "-"}{" "}
                -{" "}
                {subscription.current_period_end
                  ? formatDate(subscription.current_period_end)
                  : "-"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">Auto Renew</p>
              <p className="font-medium text-ink">
                {subscription.auto_renew ? "Yes" : "No"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">Payment Provider</p>
              <p className="font-medium text-ink">
                {subscription.payment_provider ?? "Not configured"}
              </p>
            </div>
            {trialEndsContent}
          </div>
          <div className="flex flex-wrap gap-2 pt-4 border-t border-line">
            <Button
              variant="secondary"
              onClick={() => setShowChangePlan(true)}
              disabled={loadingAction}
            >
              <Plus className="h-4 w-4 mr-2" /> Change Plan
            </Button>
            {cancelAtPeriodEndButton}
            {cancelImmediatelyButton}
            {renewSubscriptionButton}
            <Button
              variant="secondary"
              onClick={handleGenerateInvoice}
              disabled={loadingAction}
            >
              <Download className="h-4 w-4 mr-2" /> Generate Invoice
            </Button>
          </div>
        </div>
      </Card>

      {showChangePlan && (
        <Modal
          open={showChangePlan}
          onClose={() => setShowChangePlan(false)}
          title="Change Plan"
          footer={
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowChangePlan(false)}
              >
                Cancel
              </Button>
              <Button onClick={handleChangePlan} loading={loadingAction}>
                Change Plan
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <Select
              label="New Plan"
              value={selectedPlan}
              onChange={(e) => setSelectedPlan(e.target.value)}
              options={[
                { value: "starter", label: "Starter (Free)" },
                { value: "professional", label: "Professional ($10/mo)" },
                { value: "enterprise", label: "Enterprise ($99/mo)" },
              ]}
              required
            />
            <Input
              label="Effective Date"
              type="date"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              required
            />
            <p className="text-sm text-muted">
              Plan changes take effect on the selected date. Upgrades may be
              prorated.
            </p>
          </div>
        </Modal>
      )}

      <Card>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">Invoices</h2>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleGenerateInvoice}
            disabled={loadingAction}
          >
            <Download className="h-4 w-4 mr-2" /> Generate Invoice
          </Button>
        </div>
        {invoicesLoading ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : invoices?.length === 0 ? (
          <EmptyState
            title="No invoices yet"
            description="Invoices will appear here when generated."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wider text-faint">
                  <th className="px-5 py-3 font-semibold">ID</th>
                  <th className="px-4 py-3 font-semibold">Issued</th>
                  <th className="px-4 py-3 font-semibold">Amount</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {invoices?.map((invoice: any) => (
                  <tr key={invoice.id} className="hover:bg-canvas/50">
                    <td className="whitespace-nowrap px-5 py-3 font-mono text-[12px] text-faint">
                      {invoice.id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-[12px] text-muted">
                      {formatDate(invoice.issued_at)}
                    </td>
                    <td className="px-4 py-3 font-medium text-ink">
                      ${(invoice.amount / 100).toFixed(2)} {invoice.currency}
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        tone={
                          invoice.status === "paid"
                            ? "success"
                            : invoice.status === "pending"
                              ? "warning"
                              : "danger"
                        }
                      >
                        {invoice.status}
                      </Badge>
                    </td>
                    <td className="px-5 py-3">
                      {invoice.status !== "paid" && (
                        <Button variant="ghost" size="sm">
                          Pay
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------- Audit ------------------------------------- */

function AuditTab() {
  const { data, loading, error, refetch } = useFetch<Paginated<AuditLog>>(
    "/audit?page_size=50",
  );

  return (
    <Card>
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="text-sm font-semibold text-ink">Audit log</h2>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>
      {error ? (
        <ErrorState title="Could not load audit log" message={error} />
      ) : loading || !data ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState
          title="No audit entries yet"
          description="Security-relevant actions will be recorded here."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-line text-[11px] uppercase tracking-wider text-faint">
                <th className="px-5 py-3 font-semibold">When</th>
                <th className="px-4 py-3 font-semibold">Actor</th>
                <th className="px-4 py-3 font-semibold">Action</th>
                <th className="px-4 py-3 font-semibold">Target</th>
                <th className="px-4 py-3 font-semibold">Result</th>
                <th className="px-5 py-3 font-semibold">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((log: AuditLog) => (
                <tr key={log.id} className="hover:bg-canvas/50">
                  <td className="whitespace-nowrap px-5 py-3 text-[12px] text-faint">
                    {formatDate(log.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <span className="truncate text-ink">
                      {log.actor_email ?? "System"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <code className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[12px] text-brand">
                      {log.action}
                    </code>
                  </td>
                  <td className="px-4 py-3 text-[12px] text-muted">
                    {log.resource_type ?? "—"}
                    {log.resource_id ? (
                      <span className="block font-mono text-[11px] text-faint">
                        {log.resource_id.slice(0, 8)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      tone={
                        log.outcome === "denied"
                          ? "danger"
                          : log.severity === "error"
                            ? "danger"
                            : "neutral"
                      }
                    >
                      {log.outcome}
                    </Badge>
                  </td>
                  <td className="px-5 py-3 font-mono text-[12px] text-faint">
                    {log.ip_address ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
