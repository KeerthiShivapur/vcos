"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, ChevronRight, Plus } from "lucide-react";

import { getWikiTree, listWikiPages } from "@/lib/api";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import type { WikiPage, WikiTreeNode } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { statusToneFor } from "@/components/knowledge/KnowledgeBadge";

export default function WikiPage() {
  return (
    <Suspense fallback={null}>
      <WikiContent />
    </Suspense>
  );
}

function WikiContent() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.KNOWLEDGE_MANAGE);
  const [tree, setTree] = useState<WikiTreeNode[]>([]);
  const [unattached, setUnattached] = useState<WikiPage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [treeData, pages] = await Promise.all([
        getWikiTree(),
        listWikiPages({ limit: 500 }),
      ]);
      setTree(treeData);
      const inTree = new Set<string>();
      const walk = (nodes: WikiTreeNode[]) =>
        nodes.forEach((n) => {
          inTree.add(n.id);
          walk(n.children ?? []);
        });
      walk(treeData);
      setUnattached(pages.filter((p) => !inTree.has(p.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load wiki");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Wiki"
        description="The living handbook — organized as a tree of pages."
        actions={
          canManage ? (
            <Link href="/wiki/new">
              <Button size="sm">
                <Plus className="h-4 w-4" /> New page
              </Button>
            </Link>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState title="Could not load wiki" message={error} />
      ) : loading ? (
        <div className="flex justify-center py-24">
          <Spinner label="Loading wiki" />
        </div>
      ) : tree.length === 0 && unattached.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="No wiki pages yet"
          description="Create your first page — you can nest pages under it later."
          action={
            canManage ? (
              <Link href="/wiki/new">
                <Button size="sm">
                  <Plus className="h-4 w-4" /> New page
                </Button>
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card p-5">
            <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-faint">
              Page tree
            </p>
            <TreeNodeList nodes={tree} depth={0} />
            {unattached.length > 0 && (
              <div className="mt-4 border-t border-line pt-3">
                <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-faint">
                  Unattached pages
                </p>
                {unattached.map((page) => (
                  <PageRow key={page.id} page={page} />
                ))}
              </div>
            )}
          </div>

          <div className="card p-5">
            <p className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-faint">
              All pages
            </p>
            <div className="space-y-1.5">
              {[...walkPages(tree), ...unattached].map((page) => (
                <PageRow key={page.id} page={page} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function walkPages(nodes: WikiTreeNode[]): WikiTreeNode[] {
  return nodes.flatMap((node) => [node, ...walkPages(node.children ?? [])]);
}

function TreeNodeList({
  nodes,
  depth,
}: {
  nodes: WikiTreeNode[];
  depth: number;
}) {
  if (nodes.length === 0) return null;
  return (
    <ul className="space-y-1">
      {nodes.map((node) => (
        <li key={node.id}>
          <Link
            href={`/wiki/${node.id}`}
            className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[13px] font-medium text-ink transition-colors hover:bg-surface"
            style={{ marginLeft: depth * 16 }}
          >
            <ChevronRight
              className={`h-3.5 w-3.5 text-faint ${node.children?.length ? "" : "opacity-0"}`}
            />
            <span className="truncate">{node.title}</span>
            <Badge tone={statusToneFor(node.status)}>{node.status}</Badge>
            {node.child_count > 0 && (
              <span className="ml-auto text-[11px] text-faint">
                {node.child_count}
              </span>
            )}
          </Link>
          {node.children?.length > 0 && (
            <TreeNodeList nodes={node.children} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  );
}

function PageRow({
  page,
}: {
  page: { id: string; title: string; status: string };
}) {
  return (
    <Link
      href={`/wiki/${page.id}`}
      className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink transition-colors hover:bg-surface"
    >
      <span className="truncate font-medium">{page.title}</span>
      <Badge tone={statusToneFor(page.status)}>{page.status}</Badge>
    </Link>
  );
}
