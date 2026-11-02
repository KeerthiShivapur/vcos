"use client";

import { Check, ChevronRight } from "lucide-react";

interface StepperProps {
  steps: string[];
  currentStep: number;
  completedSteps: number[];
  className?: string;
}

export function Stepper({
  steps,
  currentStep,
  completedSteps,
  className,
}: StepperProps) {
  return (
    <nav
      className={`flex items-center gap-1 ${className || ""}`}
      aria-label="Progress"
    >
      <ol className="flex items-center gap-2" role="list">
        {steps.map((step, index) => {
          const isCompleted = completedSteps.includes(index);
          const isCurrent = index === currentStep;
          const isFuture = index > currentStep;

          return (
            <li key={step} className="flex items-center">
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                  isCompleted
                    ? "bg-brand text-white"
                    : isCurrent
                      ? "bg-brand text-white"
                      : "bg-line text-muted"
                }`}
                aria-current={isCurrent ? "step" : undefined}
              >
                {isCompleted ? <Check className="h-4 w-4" /> : index + 1}
              </div>
              {index < steps.length - 1 && (
                <div
                  className={`h-0.5 flex-1 max-w-24 transition-colors ${
                    index < currentStep ? "bg-brand" : "bg-line"
                  }`}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function StepperVertical({
  steps,
  currentStep,
  completedSteps,
  className,
}: StepperProps) {
  return (
    <nav
      className={`flex flex-col items-start gap-4 ${className || ""}`}
      aria-label="Progress"
    >
      <ol className="flex flex-col gap-4" role="list">
        {steps.map((step, index) => {
          const isCompleted = completedSteps.includes(index);
          const isCurrent = index === currentStep;
          const isFuture = index > currentStep;

          return (
            <li key={step} className="flex items-start gap-4">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                    isCompleted
                      ? "bg-brand text-white"
                      : isCurrent
                        ? "bg-brand text-white"
                        : "bg-line text-muted"
                  }`}
                  aria-current={isCurrent ? "step" : undefined}
                >
                  {isCompleted ? <Check className="h-5 w-5" /> : index + 1}
                </div>
                <span
                  className={`text-sm font-medium text-center w-32 ${
                    isCompleted || isCurrent ? "text-ink" : "text-muted"
                  }`}
                >
                  {step}
                </span>
              </div>
              {index < steps.length - 1 && (
                <div
                  className={`h-8 w-0.5 flex-1 transition-colors ${
                    index < currentStep ? "bg-brand" : "bg-line"
                  }`}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
