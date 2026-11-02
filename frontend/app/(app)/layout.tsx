"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { Header } from "@/components/header/Header";
import { useAuth } from "@/hooks/useAuth";
import { useNotifications } from "@/hooks/useNotifications";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";

function AuthBlocked({
  title,
  message,
  retrying,
  onRetry,
  onSignOut,
}: {
  title: string;
  message: string;
  retrying: boolean;
  onRetry: () => void;
  onSignOut: () => void;
}) {
  return (
    <div className="flex h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 text-center shadow-popover">
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        <p className="mt-2 text-sm text-muted">{message}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button onClick={onRetry} loading={retrying}>
            Try again
          </Button>
          <Button variant="secondary" onClick={onSignOut}>
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, error, retry, logout } =
    useAuth();
  const { unreadCount } = useNotifications();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      const next =
        pathname && pathname !== "/home" && pathname !== "/"
          ? `?next=${encodeURIComponent(pathname)}`
          : "";
      router.replace(`/login${next}`);
    }
  }, [loading, user, pathname, router]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        router.push("/search");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Opening your company" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Redirecting to sign in" />
      </div>
    );
  }

  if (error && error.includes("workspace")) {
    return (
      <AuthBlocked
        title="Company workspace unavailable"
        message={
          error ??
          "Your account is not linked to an active company workspace. Contact your administrator."
        }
        retrying={false}
        onRetry={() => void retry()}
        onSignOut={() => void logout()}
      />
    );
  }

  if (error) {
    return (
      <AuthBlocked
        title="We couldn't open your company"
        message={error ?? "Check your connection and try again."}
        retrying={false}
        onRetry={() => void retry()}
        onSignOut={() => void logout()}
      />
    );
  }

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Opening your company" />
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar unread={unreadCount} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
