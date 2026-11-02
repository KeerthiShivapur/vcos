"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { classNames } from "@/lib/utils";

type ToastKind = "success" | "error" | "info";
interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  message?: string;
}

let pushToast:
  ((kind: ToastKind, title: string, message?: string) => void) | null = null;

export function toast(kind: ToastKind, title: string, message?: string) {
  pushToast?.(kind, title, message);
}

export const toastSuccess = (title: string, message?: string) =>
  toast("success", title, message);
export const toastError = (title: string, message?: string) =>
  toast("error", title, message);

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    pushToast = (kind, title, message) => {
      const id = Date.now() + Math.random();
      setToasts((current) => [...current, { id, kind, title, message }]);
      window.setTimeout(() => {
        setToasts((current) => current.filter((t) => t.id !== id));
      }, 4500);
    };
    return () => {
      pushToast = null;
    };
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const icons: Record<ToastKind, React.ReactNode> = {
    success: <CheckCircle2 className="h-4 w-4 text-success" />,
    error: <XCircle className="h-4 w-4 text-danger" />,
    info: <Info className="h-4 w-4 text-brand" />,
  };

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={classNames(
            "pointer-events-auto flex animate-pop items-start gap-3 rounded-xl border border-line bg-elevated p-3.5 shadow-popover",
          )}
        >
          <span className="mt-0.5 shrink-0">{icons[t.kind]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink">{t.title}</p>
            {t.message && (
              <p className="mt-0.5 text-xs text-muted">{t.message}</p>
            )}
          </div>
          <button
            onClick={() => dismiss(t.id)}
            className="text-faint hover:text-ink"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
