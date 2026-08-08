"use client";

import Link from "next/link";
import { Eye, MessageSquare } from "lucide-react";

import { kindLabel } from "@/components/knowledge/KnowledgeBadge";
import { KindIconTile } from "@/components/knowledge/KindIcon";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { formatDate } from "@/lib/utils";

interface KnowledgeCardProps {
  item: {
    id: string;
    kind: string;
    title: string;
    status: string;
    tags?: string[];
    author_name?: string | null;
    owner_name?: string | null;
    view_count?: number;
    comment_count?: number;
    updated_at?: string | null;
    url?: string;
    description?: string | null;
    summary?: string | null;
  };
  href?: string;
}

const STATUS_TONES: Record<string, "success" | "warning" | "neutral"> = {
  published: "success",
  approved: "success",
  made: "success",
  implemented: "success",
  reviewed: "success",
  in_review: "warning",
  proposed: "warning",
};

export function KnowledgeCard({ item, href }: KnowledgeCardProps) {
  const name = item.author_name ?? item.owner_name ?? null;
  const target = href ?? item.url ?? `/${item.kind === "wiki" ? "wiki" : item.kind === "sop" ? "sops" : `${item.kind === "document" ? "documents" : `${item.kind}s`}`}/${item.id}`;
  const tone = STATUS_TONES[item.status] ?? "neutral";

  return (
    <Link
      href={target}
      className="card group flex flex-col p-5 transition-shadow hover:shadow-popover"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <KindIconTile kind={item.kind} />
          <div className="min-w-0">
            <h3 className="truncate font-semibold text-ink group-hover:text-brand">{item.title}</h3>
            <p className="text-[12px] text-faint">{kindLabel(item.kind)}</p>
          </div>
        </div>
        <Badge tone={tone}>{item.status.replace(/_/g, " ")}</Badge>
      </div>

      {(item.description || item.summary) && (
        <p className="mt-3 line-clamp-2 text-[13px] leading-relaxed text-muted">
          {item.description ?? item.summary}
        </p>
      )}

      {item.tags && item.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {item.tags.slice(0, 4).map((tag) => (
            <span key={tag} className="rounded-md bg-canvas px-2 py-0.5 text-[11px] text-muted">
              #{tag}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
        <span className="flex items-center gap-1.5 text-[12px] text-faint">
          {name ? (
            <>
              <Avatar name={name} size="sm" /> {name}
            </>
          ) : (
            <span>Unassigned</span>
          )}
        </span>
        <span className="flex items-center gap-3 text-[12px] text-faint">
          {typeof item.view_count === "number" && (
            <span className="flex items-center gap-1">
              <Eye className="h-3.5 w-3.5" /> {item.view_count}
            </span>
          )}
          {typeof item.comment_count === "number" && (
            <span className="flex items-center gap-1">
              <MessageSquare className="h-3.5 w-3.5" /> {item.comment_count}
            </span>
          )}
          {item.updated_at && <span>{formatDate(item.updated_at)}</span>}
        </span>
      </div>
    </Link>
  );
}
