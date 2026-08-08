"use client";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-faint">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-brand" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
