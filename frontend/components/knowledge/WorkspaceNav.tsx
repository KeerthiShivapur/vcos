"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Brain,
  GitBranch,
  HeartPulse,
  ListChecks,
  MapPin,
  Target,
} from "lucide-react";

import { classNames } from "@/lib/utils";

const SECTIONS = [
  { href: "/knowledge/workspace", label: "Overview & Ask", icon: Brain },
  {
    href: "/knowledge/workspace/changes",
    label: "Changes · Insights · Gaps",
    icon: Activity,
  },
  {
    href: "/knowledge/workspace/impact",
    label: "Impact Analysis",
    icon: MapPin,
  },
  {
    href: "/knowledge/workspace/recommendations",
    label: "Command Center",
    icon: ListChecks,
  },
  {
    href: "/knowledge/workspace/actions",
    label: "Action Center",
    icon: Target,
  },
  {
    href: "/knowledge/workspace/timeline",
    label: "Evolution Timeline",
    icon: GitBranch,
  },
  {
    href: "/knowledge/workspace/health",
    label: "Health Center",
    icon: HeartPulse,
  },
];

export function KnowledgeWorkspaceNav() {
  const pathname = usePathname();
  return (
    <div className="flex flex-wrap gap-1 border-b border-line">
      {SECTIONS.map((section) => {
        const active = pathname === section.href;
        return (
          <Link
            key={section.href}
            href={section.href}
            className={classNames(
              "inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-[13px] font-medium transition-colors",
              active
                ? "border-brand text-ink"
                : "border-transparent text-faint hover:border-line hover:text-ink",
            )}
          >
            <section.icon className="h-4 w-4" />
            {section.label}
          </Link>
        );
      })}
    </div>
  );
}
