"use client";

import { Suspense, useEffect, useState } from "react";
import { BarChart, TrendingUp, X } from "lucide-react";
import { classNames } from "@/lib/utils";

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number;
  className?: string;
}

export function Progress({ value, className, ...props }: ProgressProps) {
  const clampedValue = Math.max(0, Math.min(100, value));
  return (
    <div
      className={classNames(
        "relative h-2 w-full overflow-hidden rounded-full bg-line",
        className,
      )}
      {...props}
      role="progressbar"
      aria-valuenow={clampedValue}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full bg-brand transition-all duration-300 ease-out"
        style={{ width: `${clampedValue}%` }}
      />
    </div>
  );
}
