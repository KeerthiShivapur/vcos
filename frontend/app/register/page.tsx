"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Building2, Sparkles, UserPlus } from "lucide-react";

import {
  isAuthenticated,
  registerFromInvite,
  registerOrganization,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/hooks/useAuth";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get("invite") ?? "";
  const isInvite = Boolean(inviteToken);
  const { refreshProfile } = useAuth();

  const [orgName, setOrgName] = useState("");
  const [slug, setSlug] = useState("");
  const [industry, setIndustry] = useState("");
  const [country, setCountry] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated()) router.replace("/home");
  }, [router]);

  useEffect(() => {
    if (orgName && !slug) setSlug(slugify(orgName));
    else if (orgName)
      setSlug((current) =>
        current === slugify(orgName) ? current : current || slugify(orgName),
      );
    // keep manual edits; auto-fill only when slug untouched
  }, [orgName]); // eslint-disable-line react-hooks/exhaustive-deps

  const title = useMemo(
    () => (isInvite ? "Join your company" : "Start your company"),
    [isInvite],
  );
  const subtitle = useMemo(
    () =>
      isInvite
        ? "You were invited to an organization on VCOS. Set up your account to begin."
        : "Register your organization. Invite employees, create structure, start working.",
    [isInvite],
  );

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      if (isInvite) {
        await registerFromInvite({
          token: inviteToken,
          full_name: fullName,
          password,
        });
        toastSuccess("Welcome aboard", "Your VCOS account is ready.");
      } else {
        if (!slug) {
          setError("Organization slug is required.");
          setLoading(false);
          return;
        }
        await registerOrganization({
          organization_name: orgName,
          organization_slug: slug,
          industry: industry || undefined,
          country: country || undefined,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC",
          currency: "USD",
          full_name: fullName,
          email,
          password,
        });
        toastSuccess(
          "Your company is live",
          "Nova — your VCOS headquarters is ready.",
        );
      }
      await refreshProfile();
      router.replace("/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to register");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand text-white shadow-popover">
            {isInvite ? (
              <UserPlus className="h-6 w-6" />
            ) : (
              <Sparkles className="h-6 w-6" />
            )}
          </div>
          <h1 className="text-xl font-bold tracking-tight text-ink">{title}</h1>
          <p className="mt-1 max-w-sm text-sm text-muted">{subtitle}</p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4 p-6">
          {error && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-[13px] text-danger">
              {error}
            </div>
          )}

          {!isInvite && (
            <>
              <div className="space-y-4 rounded-xl border border-line bg-canvas/60 p-4">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
                  <Building2 className="h-3.5 w-3.5" /> Your organization
                </p>
                <Input
                  label="Company name"
                  name="organization_name"
                  placeholder="Nova Labs"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                />
                <Input
                  label="Company slug (unique address)"
                  name="organization_slug"
                  placeholder="nova-labs"
                  required
                  pattern="[a-z0-9-]+"
                  hint="Used in your company's VCOS address."
                  value={slug}
                  onChange={(e) => setSlug(slugify(e.target.value))}
                />
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Industry"
                    name="industry"
                    placeholder="Software"
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                  />
                  <Input
                    label="Country"
                    name="country"
                    placeholder="United States"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                  />
                </div>
              </div>
            </>
          )}

          <div className="space-y-4">
            <Input
              label={
                isInvite
                  ? "Your full name"
                  : "Your full name (founder / administrator)"
              }
              name="full_name"
              placeholder="Ada Lovelace"
              required
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
            {!isInvite && (
              <Input
                label="Work email"
                name="email"
                type="email"
                placeholder="you@company.com"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
            <Input
              label="Password"
              name="password"
              type="password"
              placeholder="At least 8 characters"
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Input
              label="Confirm password"
              name="confirm_password"
              type="password"
              placeholder="Repeat your password"
              required
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>

          <Button type="submit" loading={loading} className="w-full">
            {isInvite
              ? "Accept invitation & continue"
              : "Register organization"}
          </Button>
        </form>

        <p className="mt-6 text-center text-[13px] text-muted">
          {isInvite ? (
            <Link
              href="/login"
              className="font-semibold text-brand hover:underline"
            >
              Already have an account? Sign in
            </Link>
          ) : (
            <>
              Already registered?{" "}
              <Link
                href="/login"
                className="font-semibold text-brand hover:underline"
              >
                Sign in
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}
