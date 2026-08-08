"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Network, ZoomIn, ZoomOut } from "lucide-react";

import { getKnowledgeGraph } from "@/lib/api";
import type { KnowledgeGraph, KnowledgeGraphNode } from "@/types";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { KIND_LABELS } from "@/components/knowledge/KnowledgeBadge";
import { Badge } from "@/components/ui/Badge";

const KIND_COLORS: Record<string, string> = {
  document: "#6366f1",
  wiki: "#0ea5e9",
  policy: "#f59e0b",
  sop: "#10b981",
  template: "#8b5cf6",
  decision: "#ef4444",
  project: "#64748b",
  goal: "#14b8a6",
  task: "#94a3b8",
  meeting: "#a3e635",
  employee: "#f472b6",
  department: "#475569",
  team: "#7c3aed",
};

interface LayoutNode extends KnowledgeGraphNode {
  x: number;
  y: number;
}

export default function KnowledgeGraphPage() {
  const { user } = useAuth();
  const [data, setData] = useState<KnowledgeGraph | null>(null);
  const [focus, setFocus] = useState("");
  const [kind, setKind] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [selected, setSelected] = useState<KnowledgeGraphNode | null>(null);

  async function load(focusId?: string, kindFilter?: string) {
    setLoading(true);
    setError(null);
    try {
      setData(
        await getKnowledgeGraph({
          focus: focusId || undefined,
          kind: kindFilter || undefined,
          limit: 200,
        })
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load graph");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const layout: LayoutNode[] = useMemo(() => {
    if (!data) return [];
    const nodes = data.nodes;
    if (nodes.length === 0) return [];
    const width = 900;
    const height = 620;
    const centerX = width / 2;
    const centerY = height / 2;

    const n = nodes.length;
    const ringCount = Math.min(3, Math.ceil(Math.sqrt(n)));
    const perRing: number[] = [];
    let remaining = n;
    for (let r = 0; r < ringCount; r++) {
      const share = r === ringCount - 1 ? remaining : Math.ceil((n - (r * n) / ringCount) / (ringCount - r));
      perRing.push(share);
      remaining -= share;
    }

    const result: LayoutNode[] = [];
    let index = 0;
    const radii = [70, 190, 290];
    for (let r = 0; r < perRing.length; r++) {
      const count = perRing[r];
      const radius = radii[Math.min(r, radii.length - 1)];
      for (let i = 0; i < count && index < n; i++) {
        const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
        result.push({
          ...nodes[index],
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        });
        index += 1;
      }
    }
    return result;
  }, [data]);

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader title="Knowledge Graph" description="The visible map of the company's brain." />
        <ErrorState title="Could not load graph" message={error} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Knowledge Graph"
        description="Every document, policy, SOP and decision, linked to the work they belong to."
      />

      <Card
        title="Graph explorer"
        subtitle={`${data?.nodes.length ?? 0} nodes · ${data?.edges.length ?? 0} relations`}
        actions={
          <div className="flex items-center gap-1.5">
            <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.max(0.5, z - 0.15))}>
              <ZoomOut className="h-4 w-4" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setZoom((z) => Math.min(2, z + 0.15))}>
              <ZoomIn className="h-4 w-4" />
            </Button>
          </div>
        }
        bodyClassName="p-0"
      >
        <div className="grid gap-0 lg:grid-cols-[1fr_260px]">
          <div className="relative overflow-hidden" style={{ height: 640 }}>
            {loading ? (
              <div className="flex h-full items-center justify-center"><Spinner label="Laying out graph" /></div>
            ) : !data || data.nodes.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <EmptyState icon={Network} title="Nothing to map yet" description="Create knowledge items and link them to projects to see them here." />
              </div>
            ) : (
              <svg viewBox="0 0 900 620" className="h-full w-full" style={{ transform: `scale(${zoom})` }}>
                <g>
                  {data.edges.map((edge, i) => {
                    const source = layout.find((n) => n.id === edge.source);
                    const target = layout.find((n) => n.id === edge.target);
                    if (!source || !target) return null;
                    return (
                      <g key={i}>
                        <line
                          x1={source.x}
                          y1={source.y}
                          x2={target.x}
                          y2={target.y}
                          stroke="#d1d5db"
                          strokeWidth={1}
                          className="transition-opacity"
                          opacity={selected && selected.id !== edge.source && selected.id !== edge.target ? 0.15 : 1}
                        />
                        <text
                          x={(source.x + target.x) / 2}
                          y={(source.y + target.y) / 2 - 4}
                          textAnchor="middle"
                          fontSize={8}
                          fill="#9ca3af"
                        >
                          {edge.relation.replace(/_/g, " ")}
                        </text>
                      </g>
                    );
                  })}
                </g>
                <g>
                  {layout.map((node) => {
                    const color = KIND_COLORS[node.kind] ?? "#94a3b8";
                    const isSelected = selected?.id === node.id;
                    return (
                      <g
                        key={node.id}
                        className="cursor-pointer"
                        onClick={() => setSelected(isSelected ? null : node)}
                      >
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={node.id === data.nodes[0]?.id ? 16 : 10}
                          fill={color}
                          fillOpacity={isSelected ? 1 : 0.85}
                          stroke="#fff"
                          strokeWidth={2}
                          opacity={selected && !isSelected ? 0.4 : 1}
                        />
                        <text
                          x={node.x}
                          y={node.y - 14}
                          textAnchor="middle"
                          fontSize={10}
                          fontWeight={600}
                          fill="#374151"
                          opacity={selected && !isSelected ? 0.3 : 1}
                        >
                          {node.label.length > 22 ? `${node.label.slice(0, 20)}…` : node.label}
                        </text>
                      </g>
                    );
                  })}
                </g>
              </svg>
            )}
          </div>

          <div className="border-t border-line p-4 lg:border-l lg:border-t-0">
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[12px] font-medium text-faint">Focus on an item</label>
                <div className="flex gap-2">
                  <Input
                    placeholder="entity id (e.g. doc id)"
                    value={focus}
                    onChange={(e) => setFocus(e.target.value)}
                    className="text-sm"
                  />
                  <Button size="sm" onClick={() => load(focus)}>Go</Button>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[12px] font-medium text-faint">Filter by kind</label>
                <Select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value);
                    load(undefined, e.target.value);
                  }}
                  options={[
                    { value: "", label: "All kinds" },
                    ...Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label })),
                  ]}
                />
              </div>
              <Button size="sm" variant="ghost" onClick={() => { setFocus(""); setKind(""); load(); }}>
                Reset view
              </Button>
            </div>

            <div className="mt-5 border-t border-line pt-4">
              <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-faint">Legend</p>
              <div className="space-y-1.5">
                {Object.entries(KIND_LABELS).map(([k, label]) => (
                  <div key={k} className="flex items-center gap-2 text-[12px] text-muted">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: KIND_COLORS[k] }} />
                    {label}
                  </div>
                ))}
              </div>
            </div>

            {selected && (
              <div className="mt-5 border-t border-line pt-4">
                <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-faint">Selected</p>
                <p className="text-[13px] font-semibold text-ink">{selected.label}</p>
                <Badge tone="brand">{kindLabel(selected.kind)}</Badge>
                {selected.status && <p className="mt-1 text-[12px] text-muted">Status: {selected.status}</p>}
                <p className="mt-1 truncate text-[12px] text-faint">{selected.id}</p>
                {typeof selected.meta.url === "string" && (
                  <Link href={selected.meta.url} className="mt-2 inline-block text-[12px] font-medium text-brand hover:underline">
                    Open →
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}
