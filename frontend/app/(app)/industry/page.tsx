"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Boxes,
  Brain,
  CheckCircle2,
  ChevronRight,
  FileText,
  LayoutDashboard,
  ListChecks,
  Play,
  Plus,
  RefreshCw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Store,
  TrendingUp,
  UploadCloud,
  Workflow,
  XCircle,
  Zap,
} from "lucide-react";

import {
  industryActivateWorkflow,
  industryAdvanceWorkflow,
  industryAIChat,
  industryAIToggle,
  industryAnalytics,
  industryApplyTemplate,
  industryCatalog,
  industryInstall,
  industryInstalled,
  industryPackAI,
  industryPackCompliance,
  industryPackModules,
  industryPackOverview,
  industryRecordMetrics,
  industryRunCompliance,
  industrySelections,
  industrySelect,
  industryTemplates,
  industryToggleModule,
  industryUninstall,
  industryWorkflowAction,
  industryWorkflows,
  industryWorkflowTemplates,
} from "@/lib/api";
import type {
  IndustryCompliancePosture,
  IndustryComplianceRule,
  IndustryKPI,
  IndustryMetricCard,
  IndustryModule,
  IndustryPackOverview,
  IndustryPackSummary,
  IndustrySelection,
  IndustryTemplate,
  IndustryWorkflowRun,
  IndustryWorkflowTemplate,
  InstalledIndustryPack,
} from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs } from "@/components/ui/Tabs";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Table, Th, Td, Tr } from "@/components/ui/Table";

const FLOW_STATUS_TONE = (s: string) =>
  s === "completed"
    ? "success"
    : s === "running" || s === "active"
      ? "brand"
      : s === "paused" || s === "pending"
        ? "warning"
        : s === "cancelled" || s === "failed"
          ? "danger"
          : "neutral";

const SEVERITY_TONE = (s: string) =>
  s === "critical" || s === "high"
    ? "danger"
    : s === "medium"
      ? "warning"
      : s === "low"
        ? "neutral"
        : "brand";

function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

export default function IndustryPage() {
  return (
    <Suspense fallback={null}>
      <IndustryContent />
    </Suspense>
  );
}

function IndustryContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canRead = roleCan(user?.role, PERMISSIONS.INDUSTRY_READ);
  const canManage = roleCan(user?.role, PERMISSIONS.INDUSTRY_MANAGE);

  const tab = searchParams.get("tab") ?? "overview";
  const setTab = (id: string) => router.replace(`/industry?tab=${id}`);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [catalog, setCatalog] = useState<IndustryPackSummary[]>([]);
  const [installed, setInstalled] = useState<InstalledIndustryPack[]>([]);
  const [selections, setSelections] = useState<IndustrySelection[]>([]);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pack, setPack] = useState<IndustryPackOverview | null>(null);

  const [showSelect, setShowSelect] = useState<string | null>(null);
  const [selectForm, setSelectForm] = useState({
    business_type: "",
    company_size: "",
    country: "",
  });

  const load = useCallback(async () => {
    setError(null);
    try {
      const [cat, inst, sel] = await Promise.all([
        industryCatalog(),
        industryInstalled(),
        industrySelections(),
      ]);
      setCatalog(cat);
      setInstalled(inst);
      setSelections(sel);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load industry data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openPack = useCallback(async (key: string) => {
    setError(null);
    setSelectedKey(key);
    setPack(null);
    try {
      const overview = await industryPackOverview(key);
      setPack(overview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pack");
      setSelectedKey(null);
    }
  }, []);

  const closePack = useCallback(() => {
    setSelectedKey(null);
    setPack(null);
  }, []);

  const installPack = useCallback(
    async (key: string) => {
      setBusy(true);
      setError(null);
      try {
        await industryInstall(key);
        setNotice(`${catalog.find((p) => p.key === key)?.name ?? key} installed`);
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Install failed");
      } finally {
        setBusy(false);
      }
    },
    [catalog, load]
  );

  const uninstallPack = useCallback(
    async (key: string) => {
      if (!window.confirm(`Uninstall the ${key} industry pack? This removes modules and configurations.`)) return;
      setBusy(true);
      setError(null);
      try {
        await industryUninstall(key);
        setNotice(`${key} pack uninstalled`);
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Uninstall failed");
      } finally {
        setBusy(false);
      }
    },
    [load]
  );

  const selectPack = useCallback(async () => {
    if (!showSelect) return;
    setBusy(true);
    setError(null);
    try {
      await industrySelect({
        industry_key: showSelect,
        business_type: selectForm.business_type || undefined,
        company_size: selectForm.company_size || undefined,
        country: selectForm.country || undefined,
      });
      setNotice(`${catalog.find((p) => p.key === showSelect)?.name ?? showSelect} selected for your company`);
      setShowSelect(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Selection failed");
    } finally {
      setBusy(false);
    }
  }, [showSelect, selectForm, catalog, load]);

  if (!canRead) {
    return (
      <ErrorState
        title="Industry Solutions"
        message="You don't have permission to view industry solutions. Ask an administrator for industry:read."
      />
    );
  }

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner label="Loading industry packs" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        breadcrumb="Industry"
        title="Industry Solutions"
        description="Vertical industry packs with prebuilt modules, workflows, compliance controls, AI profiles and KPIs."
        actions={
          <Button variant="secondary" onClick={() => void load()} loading={busy}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      {error && <ErrorState title="Something went wrong" message={error} />}
      {notice && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          <span className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" /> {notice}
          </span>
          <button onClick={() => setNotice(null)} className="text-success/70 hover:text-success">
            <XCircle className="h-4 w-4" />
          </button>
        </div>
      )}

      {selectedKey ? (
        <PackDetail
          key={selectedKey}
          industryKey={selectedKey}
          pack={pack}
          summary={catalog.find((p) => p.key === selectedKey) ?? null}
          canManage={canManage}
          onBack={closePack}
          onChanged={() => void load()}
        />
      ) : (
        <>
          <Tabs
            tabs={[
              { id: "overview", label: "Overview", icon: LayoutDashboard },
              { id: "catalog", label: "Pack Catalog", icon: Store, count: catalog.length },
              { id: "workflows", label: "Workflows", icon: ListChecks },
            ]}
            active={tab}
            onChange={setTab}
          />

          <div className="mt-5">
            {tab === "overview" && (
              <OverviewTab
                catalog={catalog}
                installed={installed}
                selections={selections}
                canManage={canManage}
                onOpen={(key) => void openPack(key)}
                onInstall={(key) => void installPack(key)}
                onSelect={(key) => setShowSelect(key)}
                onUninstall={(key) => void uninstallPack(key)}
              />
            )}
            {tab === "catalog" && (
              <CatalogTab
                catalog={catalog}
                canManage={canManage}
                onOpen={(key) => void openPack(key)}
                onInstall={(key) => void installPack(key)}
                onSelect={(key) => setShowSelect(key)}
              />
            )}
            {tab === "workflows" && (
              <WorkflowsTab installed={installed} onOpen={(key) => void openPack(key)} />
            )}
          </div>
        </>
      )}

      <Modal
        open={showSelect !== null}
        onClose={() => setShowSelect(null)}
        title="Configure industry selection"
        description={`Tailor the ${catalog.find((p) => p.key === showSelect)?.name ?? ""} pack to your company.`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowSelect(null)}>
              Cancel
            </Button>
            <Button onClick={() => void selectPack()} loading={busy}>
              Save selection
            </Button>
          </>
        }
      >
        <div className="grid gap-3">
          <Input
            label="Business type"
            placeholder="e.g. boutique firm, enterprise, startup"
            value={selectForm.business_type}
            onChange={(e) => setSelectForm({ ...selectForm, business_type: e.target.value })}
          />
          <Input
            label="Company size"
            placeholder="e.g. 11-50, 51-200, 201-1000"
            value={selectForm.company_size}
            onChange={(e) => setSelectForm({ ...selectForm, company_size: e.target.value })}
          />
          <Input
            label="Country"
            placeholder="e.g. US, UK, IN"
            value={selectForm.country}
            onChange={(e) => setSelectForm({ ...selectForm, country: e.target.value })}
          />
        </div>
      </Modal>
    </div>
  );
}

function installedStatus(cat: IndustryPackSummary[]): number {
  return cat.filter((p) => p.installed).length;
}

function OverviewTab({
  catalog,
  installed,
  selections,
  canManage,
  onOpen,
  onInstall,
  onSelect,
  onUninstall,
}: {
  catalog: IndustryPackSummary[];
  installed: InstalledIndustryPack[];
  selections: IndustrySelection[];
  canManage: boolean;
  onOpen: (key: string) => void;
  onInstall: (key: string) => void;
  onSelect: (key: string) => void;
  onUninstall: (key: string) => void;
}) {
  const installedCount = installedStatus(catalog);
  const running = installed.filter(
    (p) => p.status === "active" || p.status === "enabled"
  ).length;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Installed packs" value={installedCount} hint="Active industry solutions" icon={Boxes} />
        <StatCard label="Active modules" value={installed.reduce((n, p) => n + (p.modules_enabled?.length ?? 0), 0)} hint="Across installed packs" icon={Zap} />
        <StatCard label="Selections" value={selections.length} hint="Company industry profiles" icon={Store} />
        <StatCard label="Active packs" value={running} hint="Status active" icon={CheckCircle2} />
      </div>

      {selections.length > 0 && (
        <Card title="Company selections">
          <Table
            head={
              <>
                <Th>Industry</Th>
                <Th>Business type</Th>
                <Th>Size</Th>
                <Th>Country</Th>
                <Th>Regulations</Th>
                <Th>Status</Th>
              </>
            }
            empty={selections.length === 0 && <EmptyState title="No selections" description="Choose an industry pack to get started." />}
          >
            {selections.map((s) => (
              <Tr key={`${s.industry_key}-${s.role}`} onClick={() => onOpen(s.industry_key)}>
                <Td className="font-medium">{s.industry_key}</Td>
                <Td>{s.business_type ?? "—"}</Td>
                <Td>{s.company_size ?? "—"}</Td>
                <Td>{s.country ?? "—"}</Td>
                <Td>{(s.regulations ?? []).length}</Td>
                <Td>
                  <Badge tone={statusTone(s.status)}>{s.status}</Badge>
                </Td>
              </Tr>
            ))}
          </Table>
        </Card>
      )}

      <Card title="Installed packs">
        <Table
          head={
            <>
              <Th>Pack</Th>
              <Th>Modules</Th>
              <Th>Workflows</Th>
              <Th>Frameworks</Th>
              <Th>Status</Th>
              <Th></Th>
            </>
          }
          empty={
            installed.length === 0 && (
              <EmptyState
                title="No packs installed"
                description="Browse the catalog and install an industry pack to activate modules, workflows and compliance."
              />
            )
          }
        >
          {installed.map((p) => {
            const summary = catalog.find((c) => c.key === p.industry_key);
            return (
              <Tr key={p.id} onClick={() => onOpen(p.industry_key)}>
                <Td>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-faint">{p.industry_key}</div>
                </Td>
                <Td>{p.modules_enabled?.length ?? 0}</Td>
                <Td>{summary?.workflows.length ?? 0}</Td>
                <Td>{(summary?.compliance_frameworks ?? []).join(", ")}</Td>
                <Td>
                  <Badge tone={statusTone(p.status)}>{p.status}</Badge>
                </Td>
                <Td className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpen(p.industry_key);
                    }}
                  >
                    Manage <ChevronRight className="h-4 w-4" />
                  </Button>
                  {canManage && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        onUninstall(p.industry_key);
                      }}
                    >
                      Uninstall
                    </Button>
                  )}
                </Td>
              </Tr>
            );
          })}
        </Table>
      </Card>

      <Card title="Explore catalog">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {catalog.slice(0, 6).map((p) => (
            <div key={p.key} className="rounded-lg border border-line p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-ink">{p.name}</p>
                  <p className="mt-0.5 text-xs text-faint">{p.modules.length} modules · {p.workflows.length} workflows</p>
                </div>
                <Badge tone={p.installed ? "success" : "neutral"}>
                  {p.installed ?? "available"}
                </Badge>
              </div>
              <p className="mt-2 line-clamp-2 text-xs text-muted">{p.description}</p>
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => onOpen(p.key)}>
                  View
                </Button>
                {canManage && !p.installed && (
                  <Button size="sm" onClick={() => onSelect(p.key)}>
                    Select
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function CatalogTab({
  catalog,
  canManage,
  onOpen,
  onInstall,
  onSelect,
}: {
  catalog: IndustryPackSummary[];
  canManage: boolean;
  onOpen: (key: string) => void;
  onInstall: (key: string) => void;
  onSelect: (key: string) => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = catalog.filter(
    (p) =>
      !search ||
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.key.includes(search.toLowerCase()) ||
      (p.business_types ?? []).some((b) => b.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-4">
      <Input placeholder="Search packs by name, key or business type…" value={search} onChange={(e) => setSearch(e.target.value)} />
      {filtered.length === 0 ? (
        <EmptyState title="No packs match" description="Try a different search term." />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((p) => (
            <Card key={p.key} className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <Boxes className="h-5 w-5" />
                </div>
                <Badge tone={p.installed ? "success" : "neutral"}>{p.installed ?? "not installed"}</Badge>
              </div>
              <h3 className="mt-3 font-semibold text-ink">{p.name}</h3>
              <p className="mt-1 text-xs text-muted">{p.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Badge tone="brand">{p.modules.length} modules</Badge>
                <Badge tone="brand">{p.workflows.length} workflows</Badge>
                <Badge tone="brand">{p.ai_models.length} AI models</Badge>
              </div>
              {(p.business_types ?? []).length > 0 && (
                <p className="mt-2 text-xs text-faint">For {p.business_types.join(", ")}</p>
              )}
              <div className="mt-4 flex flex-1 items-end gap-2">
                <Button variant="secondary" size="sm" className="flex-1" onClick={() => onOpen(p.key)}>
                  View
                </Button>
                {canManage &&
                  (p.installed ? (
                    <Button variant="ghost" size="sm" className="flex-1" onClick={() => onOpen(p.key)}>
                      Manage
                    </Button>
                  ) : (
                    <Button size="sm" className="flex-1" onClick={() => onSelect(p.key)}>
                      Select
                    </Button>
                  ))}
                {canManage && !p.installed && (
                  <Button variant="ghost" size="sm" onClick={() => onInstall(p.key)}>
                    <Plus className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function WorkflowsTab({
  installed,
  onOpen,
}: {
  installed: InstalledIndustryPack[];
  onOpen: (key: string) => void;
}) {
  const [runs, setRuns] = useState<{ pack: string; runs: IndustryWorkflowRun[] }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const results = await Promise.all(
          installed.map(async (p) => ({ pack: p.industry_key, runs: await industryWorkflows(p.industry_key) }))
        );
        if (!cancelled) setRuns(results);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [installed]);

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Spinner label="Loading workflow runs" />
      </div>
    );
  }

  const all = runs.flatMap((r) => r.runs.map((w) => ({ pack: r.pack, ...w })));
  if (all.length === 0) {
    return (
      <EmptyState
        title="No workflow runs yet"
        description="Open a pack to activate its industry workflows, then track progress here."
      />
    );
  }

  return (
    <Card title="Industry workflow runs">
      <Table
        head={
          <>
            <Th>Workflow</Th>
            <Th>Pack</Th>
            <Th>Status</Th>
            <Th>Step</Th>
            <Th>Progress</Th>
            <Th>Started</Th>
            <Th></Th>
          </>
        }
      >
        {all.map((w) => (
          <Tr key={`${w.pack}-${w.id}`}>
            <Td className="font-medium">{w.name}</Td>
            <Td>
              <button onClick={() => onOpen(w.pack)} className="text-brand hover:underline">
                {w.pack}
              </button>
            </Td>
            <Td>
              <Badge tone={FLOW_STATUS_TONE(w.status)}>{w.status}</Badge>
            </Td>
            <Td>{w.current_step ?? "—"}</Td>
            <Td>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, w.progress ?? 0)}%` }} />
                </div>
                <span className="text-xs text-faint">{w.progress ?? 0}%</span>
              </div>
            </Td>
            <Td>{fmtDate(w.started_at)}</Td>
            <Td className="text-right">
              <Button variant="ghost" size="sm" onClick={() => onOpen(w.pack)}>
                View
              </Button>
            </Td>
          </Tr>
        ))}
      </Table>
    </Card>
  );
}

const PACK_TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "modules", label: "Modules", icon: Boxes },
  { id: "workflows", label: "Workflows", icon: Workflow },
  { id: "templates", label: "Templates", icon: FileText },
  { id: "compliance", label: "Compliance", icon: ShieldCheck },
  { id: "ai", label: "AI Profiles", icon: Brain },
  { id: "analytics", label: "Analytics", icon: TrendingUp },
];

function PackDetail({
  industryKey,
  pack,
  summary,
  canManage,
  onBack,
  onChanged,
}: {
  industryKey: string;
  pack: IndustryPackOverview | null;
  summary: IndustryPackSummary | null;
  canManage: boolean;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [subTab, setSubTab] = useState("overview");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const notify = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 4000);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" /> All packs
        </Button>
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-ink">
            {summary?.name ?? industryKey}
          </h2>
          <p className="text-xs text-faint">
            {industryKey} pack {pack?.status ? `· status ${pack.status}` : ""}
          </p>
        </div>
        {pack?.status && (
          <Badge tone={statusTone(pack.status)}>{pack.status}</Badge>
        )}
      </div>

      {error && <ErrorState title="Something went wrong" message={error} />}
      {notice && (
        <div className="flex items-center justify-between rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          <span className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" /> {notice}
          </span>
          <button onClick={() => setNotice(null)} className="text-success/70 hover:text-success">
            <XCircle className="h-4 w-4" />
          </button>
        </div>
      )}

      <Tabs tabs={PACK_TABS} active={subTab} onChange={setSubTab} />

      <div className="mt-5">
        {subTab === "overview" && (
          <PackOverviewBody pack={pack} summary={summary} canManage={canManage} onChanged={onChanged} notify={notify} />
        )}
        {subTab === "modules" && (
          <PackModulesBody industryKey={industryKey} canManage={canManage} notify={notify} onError={setError} />
        )}
        {subTab === "workflows" && (
          <PackWorkflowsBody industryKey={industryKey} canManage={canManage} notify={notify} onError={setError} />
        )}
        {subTab === "templates" && (
          <PackTemplatesBody industryKey={industryKey} canManage={canManage} notify={notify} onError={setError} />
        )}
        {subTab === "compliance" && (
          <PackComplianceBody industryKey={industryKey} canManage={canManage} notify={notify} onError={setError} />
        )}
        {subTab === "ai" && (
          <PackAIBody industryKey={industryKey} canManage={canManage} notify={notify} onError={setError} />
        )}
        {subTab === "analytics" && (
          <PackAnalyticsBody industryKey={industryKey} canManage={canManage} notify={notify} onError={setError} />
        )}
      </div>
    </div>
  );
}

function PackOverviewBody({
  pack,
  summary,
  canManage,
  onChanged,
  notify,
}: {
  pack: IndustryPackOverview | null;
  summary: IndustryPackSummary | null;
  canManage: boolean;
  onChanged: () => void;
  notify: (m: string) => void;
}) {
  if (!pack) return <Spinner label="Loading pack" />;
  const [busy, setBusy] = useState(false);

  return (
    <div className="space-y-5">
      <Card title="About this pack">
        <p className="text-sm text-muted">{summary?.description ?? ""}</p>
        {pack.selection ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone="brand">{pack.selection.business_type ?? "No business type"}</Badge>
            <Badge tone="brand">{pack.selection.company_size ?? "No size"}</Badge>
            <Badge tone="brand">{pack.selection.country ?? "No country"}</Badge>
          </div>
        ) : (
          <p className="mt-3 text-xs text-faint">No company selection recorded yet — select this pack to configure it.</p>
        )}
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Modules" value={pack.modules.length} icon={Boxes} />
        <StatCard label="Workflows" value={pack.workflows.length} icon={Workflow} />
        <StatCard label="KPIs" value={pack.kpis.length} icon={TrendingUp} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card title="Compliance frameworks">
          {pack.compliance.length === 0 ? (
            <p className="text-sm text-faint">No compliance frameworks in this pack.</p>
          ) : (
            <div className="space-y-3">
              {pack.compliance.map((f) => (
                <div key={`${f.framework}-${f.region}`} className="rounded-lg border border-line p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-ink">{f.framework}</p>
                    <Badge tone="brand">{f.region}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-faint">{f.rules.length} rules</p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="KPI definitions">
          {pack.kpis.length === 0 ? (
            <p className="text-sm text-faint">No KPIs defined.</p>
          ) : (
            <Table
              head={
                <>
                  <Th>KPI</Th>
                  <Th>Unit</Th>
                  <Th>Benchmark</Th>
                </>
              }
            >
              {pack.kpis.map((k: IndustryKPI) => (
                <Tr key={k.key}>
                  <Td className="font-medium">{k.name}</Td>
                  <Td>{k.unit ?? "—"}</Td>
                  <Td>{k.benchmark ?? "—"}</Td>
                </Tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      {canManage && (
        <Card title="Quick actions">
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              loading={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await industryRunCompliance(pack.industry_key);
                  notify("Compliance check started");
                  onChanged();
                } catch {
                  notify("Compliance check failed");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <ShieldCheck className="h-4 w-4" /> Run compliance check
            </Button>
            {pack.workflows[0] && (
              <Button
                variant="secondary"
                loading={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await industryActivateWorkflow(pack.industry_key, pack.workflows[0].key);
                    notify(`Workflow "${pack.workflows[0].name}" activated`);
                    onChanged();
                  } catch {
                    notify("Failed to activate workflow");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <Play className="h-4 w-4" /> Start {pack.workflows[0].name}
              </Button>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}

function PackModulesBody({
  industryKey,
  canManage,
  notify,
  onError,
}: {
  industryKey: string;
  canManage: boolean;
  notify: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [modules, setModules] = useState<IndustryModule[] | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    industryPackModules(industryKey)
      .then((m) => {
        if (!cancelled) setModules(m);
      })
      .catch((err) => onError(err instanceof Error ? err.message : "Failed to load modules"));
    return () => {
      cancelled = true;
    };
  }, [industryKey, onError]);

  if (!modules) return <Spinner label="Loading modules" />;

  return (
    <Card title="Modules">
      <div className="grid gap-3 sm:grid-cols-2">
        {modules.map((m) => (
          <div key={m.key} className="rounded-lg border border-line p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-medium text-ink">{m.name}</p>
                <p className="text-xs text-faint">{m.category}</p>
              </div>
              {canManage ? (
                <Button
                  variant={m.enabled ? "secondary" : "primary"}
                  size="sm"
                  loading={busyKey === m.key}
                  onClick={async () => {
                    setBusyKey(m.key);
                    try {
                      await industryToggleModule(industryKey, m.key, !m.enabled);
                      setModules((prev) =>
                        (prev ?? []).map((x) => (x.key === m.key ? { ...x, enabled: !m.enabled } : x))
                      );
                      notify(`${m.name} ${m.enabled ? "disabled" : "enabled"}`);
                    } catch (err) {
                      onError(err instanceof Error ? err.message : "Toggle failed");
                    } finally {
                      setBusyKey(null);
                    }
                  }}
                >
                  {m.enabled ? "Enabled" : "Enable"}
                </Button>
              ) : (
                <Badge tone={m.enabled ? "success" : "neutral"}>{m.enabled ? "enabled" : "disabled"}</Badge>
              )}
            </div>
            <p className="mt-2 text-xs text-muted">{m.description}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {m.entities.map((e) => (
                <Badge key={e} tone="neutral">
                  {e}
                </Badge>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function PackWorkflowsBody({
  industryKey,
  canManage,
  notify,
  onError,
}: {
  industryKey: string;
  canManage: boolean;
  notify: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [templates, setTemplates] = useState<IndustryWorkflowTemplate[]>([]);
  const [runs, setRuns] = useState<IndustryWorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [t, r] = await Promise.all([
        industryWorkflowTemplates(industryKey),
        industryWorkflows(industryKey),
      ]);
      setTemplates(t);
      setRuns(r);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load workflows");
    } finally {
      setLoading(false);
    }
  }, [industryKey, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <Spinner label="Loading workflows" />;

  return (
    <div className="space-y-5">
      <Card title="Workflow templates">
        <Table
          head={
            <>
              <Th>Workflow</Th>
              <Th>Steps</Th>
              <Th></Th>
            </>
          }
          empty={templates.length === 0 && <EmptyState title="No workflow templates" />}
        >
          {templates.map((t) => (
            <Tr key={t.key}>
              <Td>
                <div className="font-medium">{t.name}</div>
                <div className="text-xs text-faint">{t.description ?? t.key}</div>
              </Td>
              <Td>{t.steps.length} steps</Td>
              <Td className="text-right">
                {canManage && (
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={busy === t.key}
                    onClick={async () => {
                      setBusy(t.key);
                      try {
                        await industryActivateWorkflow(industryKey, t.key);
                        notify(`Workflow "${t.name}" started`);
                        await load();
                      } catch (err) {
                        onError(err instanceof Error ? err.message : "Activation failed");
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    <Play className="h-4 w-4" /> Start
                  </Button>
                )}
              </Td>
            </Tr>
          ))}
        </Table>
      </Card>

      <Card title="Runs">
        <Table
          head={
            <>
              <Th>Workflow</Th>
              <Th>Status</Th>
              <Th>Step</Th>
              <Th>Progress</Th>
              <Th>Started</Th>
              <Th></Th>
            </>
          }
          empty={runs.length === 0 && <EmptyState title="No runs yet" description="Start a workflow template above." />}
        >
          {runs.map((w) => (
            <Tr key={w.id}>
              <Td className="font-medium">{w.name}</Td>
              <Td>
                <Badge tone={FLOW_STATUS_TONE(w.status)}>{w.status}</Badge>
              </Td>
              <Td>{w.current_step ?? "—"}</Td>
              <Td>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, w.progress ?? 0)}%` }} />
                  </div>
                  <span className="text-xs text-faint">{w.progress ?? 0}%</span>
                </div>
              </Td>
              <Td>{fmtDate(w.started_at)}</Td>
              <Td className="text-right">
                {canManage && (
                  <div className="flex justify-end gap-1">
                    {w.status === "running" || w.status === "active" ? (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          loading={busy === `${w.id}-advance`}
                          onClick={async () => {
                            setBusy(`${w.id}-advance`);
                            try {
                              await industryAdvanceWorkflow(industryKey, w.id);
                              await load();
                            } catch (err) {
                              onError(err instanceof Error ? err.message : "Advance failed");
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          Advance
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={async () => {
                            try {
                              await industryWorkflowAction(industryKey, w.id, "pause");
                              notify("Workflow paused");
                              await load();
                            } catch (err) {
                              onError(err instanceof Error ? err.message : "Pause failed");
                            }
                          }}
                        >
                          Pause
                        </Button>
                      </>
                    ) : null}
                    {w.status === "paused" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={async () => {
                          try {
                            await industryWorkflowAction(industryKey, w.id, "resume");
                            notify("Workflow resumed");
                            await load();
                          } catch (err) {
                            onError(err instanceof Error ? err.message : "Resume failed");
                          }
                        }}
                      >
                        Resume
                      </Button>
                    )}
                    {(w.status === "running" || w.status === "active" || w.status === "paused" || w.status === "pending") && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-danger"
                        onClick={async () => {
                          try {
                            await industryWorkflowAction(industryKey, w.id, "cancel");
                            notify("Workflow cancelled");
                            await load();
                          } catch (err) {
                            onError(err instanceof Error ? err.message : "Cancel failed");
                          }
                        }}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                )}
              </Td>
            </Tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

function PackTemplatesBody({
  industryKey,
  canManage,
  notify,
  onError,
}: {
  industryKey: string;
  canManage: boolean;
  notify: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [templates, setTemplates] = useState<IndustryTemplate[] | null>(null);
  const [kind, setKind] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    industryTemplates(industryKey, kind || undefined)
      .then((t) => {
        if (!cancelled) setTemplates(t);
      })
      .catch((err) => onError(err instanceof Error ? err.message : "Failed to load templates"));
    return () => {
      cancelled = true;
    };
  }, [industryKey, kind, onError]);

  if (!templates) return <Spinner label="Loading templates" />;

  return (
    <div className="space-y-4">
      <Select
        label="Filter by kind"
        options={[
          { value: "document", label: "Documents" },
          { value: "workflow", label: "Workflows" },
          { value: "policy", label: "Policies" },
          { value: "sop", label: "SOPs" },
        ]}
        value={kind}
        onChange={(e) => setKind(e.target.value)}
      />
      <Card title="Templates">
        <Table
          head={
            <>
              <Th>Template</Th>
              <Th>Kind</Th>
              <Th>Version</Th>
              <Th>Tags</Th>
              <Th></Th>
            </>
          }
          empty={templates.length === 0 && <EmptyState title="No templates" />}
        >
          {templates.map((t) => (
            <Tr key={t.key}>
              <Td>
                <div className="font-medium">{t.name}</div>
                <div className="text-xs text-faint">{t.description ?? t.key}</div>
              </Td>
              <Td>
                <Badge tone="brand">{t.kind}</Badge>
              </Td>
              <Td>{t.version}</Td>
              <Td>{(t.tags ?? []).join(", ") || "—"}</Td>
              <Td className="text-right">
                {canManage && (
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={busyKey === t.key}
                    onClick={async () => {
                      setBusyKey(t.key);
                      try {
                        await industryApplyTemplate(industryKey, t.key);
                        notify(`Template "${t.name}" applied`);
                      } catch (err) {
                        onError(err instanceof Error ? err.message : "Apply failed");
                      } finally {
                        setBusyKey(null);
                      }
                    }}
                  >
                    <UploadCloud className="h-4 w-4" /> Apply
                  </Button>
                )}
              </Td>
            </Tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

function PackComplianceBody({
  industryKey,
  canManage,
  notify,
  onError,
}: {
  industryKey: string;
  canManage: boolean;
  notify: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [data, setData] = useState<{ rules: IndustryComplianceRule[]; posture: IndustryCompliancePosture | null } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await industryPackCompliance(industryKey);
      setData(d);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load compliance");
    }
  }, [industryKey, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!data) return <Spinner label="Loading compliance" />;

  const posture = data.posture;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard label="Total controls" value={posture?.total ?? 0} icon={ShieldCheck} />
        <StatCard label="Passed" value={posture?.passed ?? 0} hint="Compliant controls" />
        <StatCard label="Warnings" value={posture?.warned ?? 0} />
        <StatCard label="Failed" value={posture?.failed ?? 0} />
        <StatCard label="Score" value={posture?.score != null ? `${posture.score}%` : "—"} />
      </div>

      {canManage && (
        <div className="flex gap-2">
          <Button
            variant="secondary"
            loading={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await industryRunCompliance(industryKey);
                notify("Compliance check completed");
                await load();
              } catch (err) {
                onError(err instanceof Error ? err.message : "Run failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            <ShieldAlert className="h-4 w-4" /> Run compliance check
          </Button>
        </div>
      )}

      <Card title="Policies">
        <Table
          head={
            <>
              <Th>Policy</Th>
              <Th>Framework</Th>
              <Th>Region</Th>
              <Th>Severity</Th>
              <Th>Cadence</Th>
              <Th>Status</Th>
            </>
          }
          empty={data.rules.length === 0 && <EmptyState title="No policies" />}
        >
          {data.rules.map((r) => (
            <Tr key={r.policy_id}>
              <Td>
                <div className="font-medium">{r.name}</div>
                <div className="text-xs text-faint">{r.policy_key}</div>
              </Td>
              <Td>{r.framework}</Td>
              <Td>{r.region}</Td>
              <Td>
                <Badge tone={SEVERITY_TONE(r.severity)}>{r.severity}</Badge>
              </Td>
              <Td>{r.cadence_days}d</Td>
              <Td>
                <Badge tone={r.enabled ? "success" : "neutral"}>{r.enabled ? "enabled" : "disabled"}</Badge>
              </Td>
            </Tr>
          ))}
        </Table>
      </Card>
    </div>
  );
}

interface AIPackStatus {
  industry_key: string;
  profiles: {
    model_key: string;
    name: string;
    enabled: boolean;
    provider: string;
    terminology: string[];
    knowledge_scope: Record<string, unknown>;
    guardrails: string[];
    skills: string[];
    temperature: number;
  }[];
  gateway: { provider: string; available: boolean };
}

function PackAIBody({
  industryKey,
  canManage,
  notify,
  onError,
}: {
  industryKey: string;
  canManage: boolean;
  notify: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [status, setStatus] = useState<AIPackStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = (await industryPackAI(industryKey)) as unknown as AIPackStatus;
      setStatus(s);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load AI status");
    }
  }, [industryKey, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!status) return <Spinner label="Loading AI profiles" />;

  const ask = async () => {
    if (!question.trim()) return;
    setBusy(true);
    setAnswer(null);
    try {
      const result = await industryAIChat(industryKey, question);
      setAnswer(result.content);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <Card title="Gateway">
        <div className="flex items-center gap-3">
          <Badge tone={status.gateway.available ? "success" : "danger"}>
            {status.gateway.available ? "available" : "unavailable"}
          </Badge>
          <span className="text-sm text-muted">Provider: {status.gateway.provider}</span>
        </div>
      </Card>

      <Card title="AI model profiles">
        <div className="grid gap-3 sm:grid-cols-2">
          {status.profiles.map((p) => (
            <div key={p.model_key} className="rounded-lg border border-line p-4">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-medium text-ink">{p.name}</p>
                  <p className="text-xs text-faint">
                    {p.provider} · {p.temperature} temp · {p.terminology.length} terms
                  </p>
                </div>
                {canManage ? (
                  <Button
                    variant={p.enabled ? "secondary" : "primary"}
                    size="sm"
                    onClick={async () => {
                      try {
                        await industryAIToggle(industryKey, p.model_key, !p.enabled);
                        setStatus((prev) =>
                          prev
                            ? {
                                ...prev,
                                profiles: prev.profiles.map((x) =>
                                  x.model_key === p.model_key ? { ...x, enabled: !p.enabled } : x
                                ),
                              }
                            : prev
                        );
                        notify(`${p.name} ${p.enabled ? "disabled" : "enabled"}`);
                      } catch (err) {
                        onError(err instanceof Error ? err.message : "Toggle failed");
                      }
                    }}
                  >
                    {p.enabled ? "Enabled" : "Enable"}
                  </Button>
                ) : (
                  <Badge tone={p.enabled ? "success" : "neutral"}>{p.enabled ? "enabled" : "disabled"}</Badge>
                )}
              </div>
              {(p.guardrails ?? []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {p.guardrails.slice(0, 4).map((g) => (
                    <Badge key={g} tone="neutral">
                      {g}
                    </Badge>
                  ))}
                </div>
              )}
              {(p.skills ?? []).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {p.skills.map((s) => (
                    <Badge key={s} tone="brand">
                      {s}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Ask the industry AI">
        <div className="flex gap-2">
          <Input
            placeholder={`Ask a question about ${industryKey} operations…`}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void ask();
            }}
          />
          <Button onClick={() => void ask()} loading={busy}>
            <Send className="h-4 w-4" /> Ask
          </Button>
        </div>
        {answer && (
          <div className="mt-4 rounded-lg border border-line bg-canvas p-4">
            <div className="flex items-center gap-2 text-xs text-faint">
              <Sparkles className="h-3.5 w-3.5 text-brand" /> Industry AI response
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm text-ink">{answer}</p>
          </div>
        )}
      </Card>
    </div>
  );
}

function PackAnalyticsBody({
  industryKey,
  canManage,
  notify,
  onError,
}: {
  industryKey: string;
  canManage: boolean;
  notify: (m: string) => void;
  onError: (m: string) => void;
}) {
  const [dash, setDash] = useState<{ metrics: IndustryMetricCard[]; tracked: number } | null>(null);
  const [kpis, setKpis] = useState<IndustryKPI[]>([]);
  const [metricKey, setMetricKey] = useState("");
  const [value, setValue] = useState("");
  const [period, setPeriod] = useState("daily");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, k] = await Promise.all([industryAnalytics(industryKey), industryPackOverview(industryKey)]);
      setDash(d);
      setKpis(k.kpis);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load analytics");
    }
  }, [industryKey, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!dash) return <Spinner label="Loading analytics" />;

  const metricTone = (m: IndustryMetricCard) =>
    m.status === "good" ? "success" : m.status === "warning" ? "warning" : m.status === "critical" ? "danger" : "neutral";

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {dash.metrics.map((m) => (
          <div key={m.metric_key} className="card p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-faint">{m.name}</p>
              <Badge tone={metricTone(m)}>{m.status}</Badge>
            </div>
            <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">
              {m.value != null ? `${m.value}` : "—"}
              {m.unit ? <span className="ml-1 text-sm text-faint">{m.unit}</span> : null}
            </p>
            <p className="mt-1 text-xs text-muted">
              Benchmark {m.benchmark ?? "—"}
              {m.delta_pct != null ? ` · ${m.delta_pct > 0 ? "+" : ""}${m.delta_pct}%` : ""}
            </p>
          </div>
        ))}
        {dash.metrics.length === 0 && (
          <div className="sm:col-span-2 lg:col-span-3">
            <EmptyState title="No metric data yet" description="Record metrics below to start tracking performance." />
          </div>
        )}
      </div>

      {canManage && (
        <Card title="Record metrics">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-44 flex-1">
              <Select
                label="Metric"
                options={kpis.map((k) => ({ value: k.key, label: `${k.name} (${k.key})` }))}
                value={metricKey}
                onChange={(e) => setMetricKey(e.target.value)}
              />
            </div>
            <div className="min-w-32">
              <Input label="Value" type="number" value={value} onChange={(e) => setValue(e.target.value)} />
            </div>
            <div className="min-w-36">
              <Select
                label="Period"
                options={["daily", "weekly", "monthly", "quarterly"].map((p) => ({ value: p, label: p }))}
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
              />
            </div>
            <Button
              loading={busy}
              disabled={!metricKey || value === ""}
              onClick={async () => {
                setBusy(true);
                try {
                  await industryRecordMetrics(industryKey, [{ metric_key: metricKey, value: Number(value) }], period);
                  notify("Metric recorded");
                  setValue("");
                  await load();
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Record failed");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <UploadCloud className="h-4 w-4" /> Record
            </Button>
          </div>
        </Card>
      )}

      <Card title="Tracked metrics">
        <p className="text-sm text-muted">
          {dash.tracked} metric values tracked in the last 30 days.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {dash.metrics.map((m) => (
            <Badge key={m.metric_key} tone={metricTone(m)}>
              {m.name} · {m.points} pts
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}
