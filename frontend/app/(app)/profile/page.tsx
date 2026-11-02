"use client";

import { useState } from "react";
import { KeyRound, Laptop, LogOut, Save } from "lucide-react";

import { api } from "@/lib/api";
import { Session, User } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { useFetch } from "@/hooks/useFetch";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

export default function ProfilePage() {
  const { user, organization, refreshProfile, logout } = useAuth();
  const {
    data: sessions,
    loading: sessionsLoading,
    error: sessionsError,
    refetch,
  } = useFetch<Session[]>("/auth/sessions");

  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [jobTitle, setJobTitle] = useState(user?.job_title ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [timezone, setTimezone] = useState(
    user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC",
  );
  const [saving, setSaving] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changing, setChanging] = useState(false);

  const [sessionBusyId, setSessionBusyId] = useState<string | null>(null);

  if (!user) return null;

  async function handleUpdateProfile(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await api<User>("/users/me", {
        method: "PATCH",
        body: {
          full_name: fullName,
          job_title: jobTitle || undefined,
          phone: phone || undefined,
          timezone: timezone || undefined,
        },
      });
      await refreshProfile();
      toastSuccess("Profile updated");
    } catch (err) {
      toastError(
        "Update failed",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(event: React.FormEvent) {
    event.preventDefault();
    if (newPassword.length < 8) {
      toastError(
        "Password too short",
        "New password must be at least 8 characters.",
      );
      return;
    }
    if (newPassword !== confirmPassword) {
      toastError("Passwords do not match");
      return;
    }
    setChanging(true);
    try {
      await api("/auth/change-password", {
        method: "POST",
        body: { current_password: currentPassword, new_password: newPassword },
      });
      toastSuccess("Password changed", "Other sessions were signed out.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      refetch();
    } catch (err) {
      toastError(
        "Change failed",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setChanging(false);
    }
  }

  async function revokeSession(session: Session) {
    if (session.is_current) return;
    setSessionBusyId(session.id);
    try {
      await api(`/auth/sessions/${session.id}`, { method: "DELETE" });
      toastSuccess("Session signed out");
      refetch();
    } catch (err) {
      toastError("Failed", err instanceof Error ? err.message : undefined);
    } finally {
      setSessionBusyId(null);
    }
  }

  async function revokeAll() {
    if (
      !confirm(
        "Sign out all other sessions? Your current device stays signed in.",
      )
    )
      return;
    try {
      await api("/auth/sessions", { method: "DELETE" });
      toastSuccess("All other sessions signed out");
      refetch();
    } catch (err) {
      toastError("Failed", err instanceof Error ? err.message : undefined);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Profile"
        description={`Your identity in ${organization?.name ?? "your company"}.`}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <h2 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">
              Personal information
            </h2>
            <form onSubmit={handleUpdateProfile} className="space-y-4 p-5">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-brand text-lg font-bold text-white">
                  {fullName.slice(0, 1).toUpperCase() || "?"}
                </div>
                <div>
                  <p className="font-medium text-ink">{user.email}</p>
                  <p className="text-[13px] text-muted">
                    Member since {formatDate(user.created_at)}
                  </p>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Input
                  label="Full name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                />
                <Input
                  label="Job title"
                  placeholder="Founder & CEO"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                />
                <Input
                  label="Phone"
                  placeholder="+1 555 0100"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                />
                <Input
                  label="Timezone"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                />
              </div>
              <div className="flex justify-end">
                <Button type="submit" loading={saving}>
                  <Save className="h-4 w-4" /> Save changes
                </Button>
              </div>
            </form>
          </Card>

          <Card>
            <h2 className="flex items-center gap-2 border-b border-line px-5 py-4 text-sm font-semibold text-ink">
              <KeyRound className="h-4 w-4 text-brand" /> Change password
            </h2>
            <form onSubmit={handleChangePassword} className="space-y-4 p-5">
              <Input
                label="Current password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Input
                  label="New password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="At least 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
                <Input
                  label="Confirm new password"
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </div>
              <p className="text-[12px] text-faint">
                Changing your password signs out all other devices.
              </p>
              <div className="flex justify-end">
                <Button type="submit" variant="secondary" loading={changing}>
                  Update password
                </Button>
              </div>
            </form>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Laptop className="h-4 w-4 text-brand" /> Active sessions
              </h2>
              <Button variant="ghost" size="sm" onClick={revokeAll}>
                Sign out all
              </Button>
            </div>
            {sessionsError ? (
              <p className="p-5 text-[13px] text-danger">{sessionsError}</p>
            ) : sessionsLoading ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {sessions?.map((s: Session) => (
                  <li key={s.id} className="flex items-center gap-3 px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2 truncate text-[13px] font-medium text-ink">
                        {s.device_name ||
                          [s.os, s.browser].filter(Boolean).join(" · ") ||
                          "Unknown device"}
                        {s.is_current && (
                          <Badge tone="brand">This device</Badge>
                        )}
                      </p>
                      <p className="truncate text-[12px] text-faint">
                        {[s.browser, s.os, s.device_type]
                          .filter(Boolean)
                          .join(" · ") || "Unknown client"}{" "}
                        · {s.ip_address ?? "Unknown IP"}
                      </p>
                      <p className="text-[12px] text-faint">
                        Last active {formatDate(s.last_activity_at)}
                      </p>
                    </div>
                    {!s.is_current && (
                      <button
                        className="text-[12px] font-medium text-danger hover:underline disabled:opacity-50"
                        disabled={sessionBusyId === s.id}
                        onClick={() => revokeSession(s)}
                      >
                        Sign out
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card className="border-danger/20">
            <div className="flex items-center justify-between p-5">
              <div>
                <p className="text-sm font-semibold text-ink">
                  Sign out of VCOS
                </p>
                <p className="text-[13px] text-muted">
                  Ends this session on this device.
                </p>
              </div>
              <Button
                variant="danger"
                size="sm"
                onClick={async () => {
                  await logout();
                }}
              >
                <LogOut className="h-4 w-4" /> Sign out
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
