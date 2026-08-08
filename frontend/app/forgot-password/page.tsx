"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { KeyRound, Sparkles } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { toastSuccess } from "@/components/ui/Toaster";

function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api("/auth/forgot-password", { method: "POST", auth: false, body: { email } });
      setSent(true);
      toastSuccess("Reset link sent", "Check your inbox for instructions.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send reset link");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand text-white shadow-popover">
            <KeyRound className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-ink">Reset your password</h1>
          <p className="mt-1 text-sm text-muted">
            {sent
              ? "If an account exists for that email, a reset link is on its way."
              : "Enter your work email and we'll send you a reset link."}
          </p>
        </div>

        {sent ? (
          <div className="card p-6 text-center">
            <p className="text-sm text-muted">The email has been sent. Follow the link inside to choose a new password.</p>
            <Link href="/login" className="mt-4 inline-block text-sm font-semibold text-brand hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="card space-y-4 p-6">
            {error && (
              <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-[13px] text-danger">
                {error}
              </div>
            )}
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
            <Button type="submit" loading={loading} className="w-full">
              Send reset link
            </Button>
          </form>
        )}

        <p className="mt-6 text-center text-[13px] text-muted">
          Remembered it?{" "}
          <Link href="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function ForgotPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ForgotPasswordForm />
    </Suspense>
  );
}
