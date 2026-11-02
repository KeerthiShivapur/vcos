"use client";

import { useState } from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { Button } from "@/components/ui/Button";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";

export function ThemeToggle() {
  const { theme, resolved, setTheme } = useTheme();
  const [open, setOpen] = useState(false);

  const options = [
    {
      value: "light" as const,
      label: "Light",
      icon: Sun,
      description: "Always use light mode",
    },
    {
      value: "dark" as const,
      label: "Dark",
      icon: Moon,
      description: "Always use dark mode",
    },
    {
      value: "system" as const,
      label: "System",
      icon: Monitor,
      description: "Match system preference",
    },
  ];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-canvas hover:text-ink"
        title={`Theme: ${theme}`}
        aria-label="Toggle theme"
      >
        {resolved === "dark" ? (
          <svg
            className="h-[18px] w-[18px]"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-3.509 9.091l-1.591-1.591M12 19.752V21m-3.509-9.091l-1.591-1.591M3.75 12H1.5m6.707 6.707l-1.061-1.061M12 3v2.25m0 0-.008 11.25M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
        ) : (
          <svg
            className="h-[18px] w-[18px]"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-3.509 9.091l-1.591-1.591M12 19.752V21m-3.509-9.091l-1.591 1.591M3.75 12H1.5m6.707 6.707l-1.061-1.061M12 3v2.25m0 0-.008 11.25M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
        )}
      </button>

      <div
        className="fixed inset-0 z-50"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />

      <div className="absolute right-0 top-full z-50 mt-2 w-56 rounded-xl border border-line bg-surface py-1 shadow-popper ring-1 ring-line">
        <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-faint">
          Theme
        </div>
        {options.map((option) => (
          <button
            key={option.value}
            onClick={() => {
              setTheme(option.value);
            }}
            className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              theme === option.value
                ? "bg-brand-soft text-brand"
                : "text-ink hover:bg-canvas"
            }`}
          >
            <option.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="flex-1 text-left">
              <p className="font-medium">{option.label}</p>
              <p className="text-[11px] text-muted">{option.description}</p>
            </div>
            {theme === option.value && (
              <svg
                className="h-4 w-4 shrink-0 text-brand"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4.5 12.75l6 6 9-13.5"
                />
              </svg>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();

  const options = [
    {
      value: "light" as const,
      label: "Light",
      description: "Always use light mode",
    },
    {
      value: "dark" as const,
      label: "Dark",
      description: "Always use dark mode",
    },
    {
      value: "system" as const,
      label: "System",
      description: "Match system preference",
    },
  ];

  return (
    <select
      value={theme}
      onChange={(e) => setTheme(e.target.value as "light" | "dark" | "system")}
      className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-brand focus:ring-2 focus:ring-brand/20 focus:outline-none"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
