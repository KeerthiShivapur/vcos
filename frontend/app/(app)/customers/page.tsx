"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  Building2,
  FileSignature,
  Handshake,
  HeartPulse,
  LayoutDashboard,
  MessageSquarePlus,
  PieChart,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  TrendingUp,
  UserPlus,
  Users,
} from "lucide-react";

import {
  addCustomerNote,
  askCustomerAI,
  buildRelationshipGraph,
  createContract,
  createCustomer,
  createLead,
  createOpportunity,
  createPartner,
  createTicket,
  getCustomer,
  getCustomerAnalytics,
  getCustomerDashboard,
  getCustomerHealth,
  getCustomerRenewals,
  getOpportunityPipeline,
  getPartnerSummary,
  getRelationshipRisks,
  getSupportSummary,
  listContracts,
  listCustomers,
  listLeads,
  listOpportunities,
  listPartners,
  listTickets,
  recomputeCustomerHealth,
  updateLead,
  updateOpportunity,
  updateTicket,
} from "@/lib/api";
import type {
  Contract,
  Customer,
  CustomerAnalytics,
  CustomerDashboard,
  CustomerHealthRow,
  CustomerRenewal,
  Lead,
  Opportunity,
  OpportunityPipeline,
  Partner,
  SupportTicket,
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
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Modal } from "@/components/ui/Modal";
import { Table, Th, Td, Tr } from "@/components/ui/Table";

export default function CustomersPage() {
  return (
    <Suspense fallback={null}>
      <CustomersContent />
    </Suspense>
  );
}

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "customers", label: "Customers", icon: Building2 },
  { id: "leads", label: "Leads", icon: UserPlus },
  { id: "pipeline", label: "Pipeline", icon: PieChart },
  { id: "contracts", label: "Contracts", icon: FileSignature },
  { id: "support", label: "Support", icon: Activity },
  { id: "partners", label: "Partners", icon: Handshake },
  { id: "analytics", label: "Analytics", icon: TrendingUp },
  { id: "ai", label: "CRM AI", icon: Sparkles },
];

const fmtMoney = (value?: number | null) =>
  value == null
    ? "—"
    : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const healthTone = (status?: string | null) => {
  if (status === "healthy") return "success";
  if (status === "at_risk") return "warning";
  if (status === "critical") return "danger";
  return "neutral";
};

function CustomersContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.CRM_MANAGE);

  const tab = searchParams.get("tab") ?? "overview";
  const setTab = (id: string) => router.replace(`/customers?tab=${id}`);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [dashboard, setDashboard] = useState<CustomerDashboard | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [pipeline, setPipeline] = useState<OpportunityPipeline | null>(null);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [renewals, setRenewals] = useState<CustomerRenewal[]>([]);
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [supportSummary, setSupportSummary] = useState<{
    total: number;
    open: number;
    escalated: number;
    overdue: number;
    by_priority: Record<string, number>;
  } | null>(null);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [partnerSummary, setPartnerSummary] = useState<{
    total: number;
    active: number;
    by_kind: Record<string, number>;
  } | null>(null);
  const [health, setHealth] = useState<CustomerHealthRow[]>([]);
  const [analytics, setAnalytics] = useState<CustomerAnalytics | null>(null);
  const [risks, setRisks] = useState<{
    single_points_of_failure: Record<string, unknown>[];
    total: number;
  } | null>(null);

  const [ai, setAi] = useState<{ answer: string } | null>(null);
  const [aiQuestion, setAiQuestion] = useState("");

  const [selected, setSelected] = useState<Customer | null>(null);
  const [noteText, setNoteText] = useState("");

  const [showCustomer, setShowCustomer] = useState(false);
  const [showLead, setShowLead] = useState(false);
  const [showOpp, setShowOpp] = useState(false);
  const [showContract, setShowContract] = useState(false);
  const [showTicket, setShowTicket] = useState(false);
  const [showPartner, setShowPartner] = useState(false);

  const [form, setForm] = useState<Record<string, string>>({});

  const loadAll = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    setError(null);
    try {
      const [
        dashRes,
        customersRes,
        leadsRes,
        oppsRes,
        pipelineRes,
        contractsRes,
        renewalsRes,
        ticketsRes,
        supportRes,
        partnersRes,
        partnerSumRes,
        healthRes,
        analyticsRes,
        risksRes,
      ] = await Promise.allSettled([
        getCustomerDashboard(),
        listCustomers({}),
        listLeads({}),
        listOpportunities({}),
        getOpportunityPipeline(),
        listContracts({}),
        getCustomerRenewals(),
        listTickets({}),
        getSupportSummary(),
        listPartners({}),
        getPartnerSummary(),
        getCustomerHealth(),
        getCustomerAnalytics(),
        getRelationshipRisks(),
      ]);
      const ok = <T,>(r: PromiseSettledResult<T>): T | null =>
        r.status === "fulfilled" ? r.value : null;
      setDashboard(ok(dashRes));
      setCustomers(ok(customersRes) ?? []);
      setLeads(ok(leadsRes) ?? []);
      setOpportunities(ok(oppsRes) ?? []);
      setPipeline(ok(pipelineRes));
      setContracts(ok(contractsRes) ?? []);
      setRenewals(ok(renewalsRes)?.contracts ?? []);
      setTickets(ok(ticketsRes) ?? []);
      setSupportSummary(ok(supportRes));
      setPartners(ok(partnersRes) ?? []);
      setPartnerSummary(ok(partnerSumRes));
      setHealth(ok(healthRes) ?? []);
      setAnalytics(ok(analyticsRes));
      setRisks(ok(risksRes));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll(true);
  }, [loadAll]);

  useEffect(() => {
    const t = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(t);
  }, [notice]);

  const run = async (fn: () => Promise<unknown>, okMessage: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(okMessage);
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const askAi = async () => {
    if (!aiQuestion.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await askCustomerAI(aiQuestion);
      setAi(res);
      setAiQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openDetail = async (customerId: string) => {
    try {
      const detail = await getCustomer(customerId);
      setSelected(detail);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const onCreateCustomer = async () => {
    if (!form.company_name?.trim()) {
      setError("Company name is required.");
      return;
    }
    await run(
      () =>
        createCustomer({
          ...form,
          annual_value: form.annual_value ? Number(form.annual_value) : null,
        }),
      "Customer created.",
    );
    setShowCustomer(false);
    setForm({});
  };

  const onCreateLead = async () => {
    if (!form.company_name?.trim()) {
      setError("Company name is required.");
      return;
    }
    await run(() => createLead(form), "Lead created.");
    setShowLead(false);
    setForm({});
  };

  const onCreateOpp = async () => {
    if (!form.title?.trim()) {
      setError("Title is required.");
      return;
    }
    await run(
      () =>
        createOpportunity({
          ...form,
          value: form.value ? Number(form.value) : null,
          probability: form.probability ? Number(form.probability) : null,
        }),
      "Opportunity created.",
    );
    setShowOpp(false);
    setForm({});
  };

  const onCreateContract = async () => {
    if (!form.title?.trim()) {
      setError("Title is required.");
      return;
    }
    await run(
      () =>
        createContract({
          ...form,
          value: form.value ? Number(form.value) : null,
        }),
      "Contract created.",
    );
    setShowContract(false);
    setForm({});
  };

  const onCreateTicket = async () => {
    if (!form.subject?.trim()) {
      setError("Subject is required.");
      return;
    }
    await run(() => createTicket(form), "Ticket created.");
    setShowTicket(false);
    setForm({});
  };

  const onCreatePartner = async () => {
    if (!form.name?.trim()) {
      setError("Name is required.");
      return;
    }
    await run(() => createPartner(form), "Partner created.");
    setShowPartner(false);
    setForm({});
  };

  const onQualify = async (lead: Lead) => {
    await run(
      () => updateLead(lead.id, { status: "qualified" }),
      `${lead.company_name} qualified.`,
    );
  };

  const onWin = async (opp: Opportunity) => {
    await run(
      () => updateOpportunity(opp.id, { stage: "won" }),
      `${opp.title} marked won.`,
    );
  };

  const onResolveTicket = async (ticket: SupportTicket) => {
    await run(
      () => updateTicket(ticket.id, { status: "resolved" }),
      "Ticket resolved.",
    );
  };

  const onRecompute = async () => {
    await run(async () => {
      await recomputeCustomerHealth();
    }, "Customer health recomputed.");
  };

  const onBuildGraph = async () => {
    await run(async () => {
      await buildRelationshipGraph();
    }, "Relationship graph rebuilt.");
  };

  const onAddNote = async () => {
    if (!selected || !noteText.trim()) return;
    await addCustomerNote(selected.id, noteText.trim());
    setNoteText("");
    await openDetail(selected.id);
    setNotice("Note added.");
  };

  const customerOptions = useMemo(
    () =>
      customers.map((c) => ({
        value: c.id,
        label: c.company_name,
      })),
    [customers],
  );

  if (loading) return <Spinner label="Loading customers…" />;
  if (error && !notice)
    return <ErrorState message={error} onRetry={() => loadAll(true)} />;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Customers & CRM"
        title="Customers, CRM & External Relationships"
        description="Customers, leads, opportunities, contracts, support, partners and portfolio intelligence."
        actions={
          canManage ? (
            <>
              <Button
                variant="secondary"
                loading={busy}
                onClick={() => {
                  setShowCustomer(true);
                  setForm({});
                }}
              >
                <Plus className="h-3.5 w-3.5" /> Customer
              </Button>
              <Button
                variant="secondary"
                loading={busy}
                onClick={() => {
                  setShowLead(true);
                  setForm({});
                }}
              >
                <Plus className="h-3.5 w-3.5" /> Lead
              </Button>
            </>
          ) : undefined
        }
      />

      {notice && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-2.5 text-sm text-success">
          {notice}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
          {error}
        </div>
      )}

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard
              label="Customers"
              value={dashboard?.total_customers ?? 0}
              hint={`${dashboard?.active_customers ?? 0} active`}
              icon={Building2}
            />
            <StatCard
              label="Prospects"
              value={dashboard?.prospects ?? 0}
              hint="lead pipeline"
              icon={UserPlus}
            />
            <StatCard
              label="Health risk"
              value={dashboard?.health_risk ?? 0}
              hint={`${dashboard?.health_good ?? 0} healthy`}
              icon={HeartPulse}
            />
            <StatCard
              label="Contracts"
              value={dashboard?.contracts ?? 0}
              hint={`${analytics?.renewals_due ?? 0} renewing soon`}
              icon={FileSignature}
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="Health watch"
              subtitle="Customers that need attention right now"
              actions={
                <Button
                  size="sm"
                  variant="ghost"
                  loading={busy}
                  onClick={onRecompute}
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Recompute
                </Button>
              }
              bodyClassName="p-0"
            >
              <Table
                head={
                  <>
                    <Th>Customer</Th>
                    <Th>Score</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {health
                  .filter((h) => h.status !== "healthy" && h.status !== "new")
                  .slice(0, 6)
                  .map((h) => (
                    <Tr key={h.customer_id}>
                      <Td className="font-medium">{h.company_name}</Td>
                      <Td>{h.score}</Td>
                      <Td>
                        <Badge tone={healthTone(h.status)}>{h.status}</Badge>
                      </Td>
                    </Tr>
                  ))}
              </Table>
              {health.filter(
                (h) => h.status !== "healthy" && h.status !== "new",
              ).length === 0 && (
                <EmptyState
                  title="No at-risk customers"
                  description="All customers are in good standing."
                />
              )}
            </Card>

            <Card
              title="Renewals"
              subtitle="Contracts expiring in the next 120 days"
              bodyClassName="p-0"
            >
              <Table
                head={
                  <>
                    <Th>Contract</Th>
                    <Th>Customer</Th>
                    <Th>Days</Th>
                    <Th>Value</Th>
                  </>
                }
              >
                {renewals.slice(0, 6).map((c) => (
                  <Tr key={c.id}>
                    <Td className="font-medium">{c.title}</Td>
                    <Td>{c.customer_name ?? "—"}</Td>
                    <Td>
                      <Badge
                        tone={(c.days_left ?? 999) <= 30 ? "danger" : "warning"}
                      >
                        {c.days_left ?? "?"}d
                      </Badge>
                    </Td>
                    <Td>{fmtMoney(c.value)}</Td>
                  </Tr>
                ))}
              </Table>
              {renewals.length === 0 && (
                <EmptyState
                  title="No renewals due"
                  description="Nothing expires in the next 120 days."
                />
              )}
            </Card>
          </div>

          <Card
            title="Relationship intelligence"
            subtitle="Single points of failure across your portfolio"
            bodyClassName="p-0"
          >
            <Table
              head={
                <>
                  <Th>Exposure</Th>
                  <Th>Kind</Th>
                  <Th>Detail</Th>
                </>
              }
            >
              {(risks?.single_points_of_failure ?? [])
                .slice(0, 5)
                .map((risk, index) => (
                  <Tr key={index}>
                    <Td className="font-medium">{String(risk.owner ?? "—")}</Td>
                    <Td>
                      <Badge tone="warning">{String(risk.kind ?? "—")}</Badge>
                    </Td>
                    <Td>{String(risk.detail ?? "—")}</Td>
                  </Tr>
                ))}
            </Table>
            {(risks?.single_points_of_failure ?? []).length === 0 && (
              <EmptyState
                title="No relationship risks"
                description="No single points of failure detected."
              />
            )}
          </Card>
        </div>
      )}

      {tab === "customers" && (
        <Card
          title="Customers"
          subtitle={`${customers.length} companies`}
          actions={
            canManage ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setShowCustomer(true);
                  setForm({});
                }}
              >
                <Plus className="h-3.5 w-3.5" /> New customer
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table
            head={
              <>
                <Th>Company</Th>
                <Th>Status</Th>
                <Th>Tier</Th>
                <Th>Health</Th>
                <Th>Annual value</Th>
                <Th>Owner</Th>
              </>
            }
          >
            {customers.map((c) => (
              <Tr key={c.id} onClick={() => openDetail(c.id)}>
                <Td className="font-medium">{c.company_name}</Td>
                <Td>
                  <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                </Td>
                <Td>{c.tier}</Td>
                <Td>
                  <Badge tone={healthTone(c.health_status)}>
                    {c.health_score}
                  </Badge>
                </Td>
                <Td>{fmtMoney(c.annual_value)}</Td>
                <Td className="text-faint">{c.owner_name ?? "—"}</Td>
              </Tr>
            ))}
          </Table>
          {customers.length === 0 && (
            <EmptyState
              title="No customers yet"
              description="Create your first customer to get started."
            />
          )}
        </Card>
      )}

      {tab === "leads" && (
        <Card
          title="Leads"
          subtitle={`${leads.length} leads`}
          actions={
            canManage ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setShowLead(true);
                  setForm({});
                }}
              >
                <Plus className="h-3.5 w-3.5" /> New lead
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table
            head={
              <>
                <Th>Company</Th>
                <Th>Contact</Th>
                <Th>Status</Th>
                <Th>Score</Th>
                <Th>Source</Th>
                <Th />
              </>
            }
          >
            {leads.map((l) => (
              <Tr key={l.id}>
                <Td className="font-medium">{l.company_name}</Td>
                <Td>{l.contact_name ?? "—"}</Td>
                <Td>
                  <Badge tone={statusTone(l.status)}>{l.status}</Badge>
                </Td>
                <Td>{l.score ?? "—"}</Td>
                <Td>{l.source}</Td>
                <Td className="text-right">
                  {l.status === "new" && canManage && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={busy}
                      onClick={() => onQualify(l)}
                    >
                      Qualify
                    </Button>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
          {leads.length === 0 && (
            <EmptyState
              title="No leads"
              description="Capture leads from marketing, referrals and events."
            />
          )}
        </Card>
      )}

      {tab === "pipeline" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard
              label="Open deals"
              value={pipeline?.total_count ?? 0}
              icon={PieChart}
            />
            <StatCard
              label="Pipeline value"
              value={fmtMoney(pipeline?.total_value)}
              hint="open opportunities"
              icon={TrendingUp}
            />
            <StatCard
              label="Weighted"
              value={fmtMoney(pipeline?.weighted_value)}
              hint="probability adjusted"
              icon={Activity}
            />
            <StatCard
              label="Won"
              value={pipeline?.won_value ? fmtMoney(pipeline.won_value) : "—"}
              icon={Handshake}
            />
          </div>

          <Card
            title="Pipeline by stage"
            subtitle="Value per stage"
            actions={
              canManage ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setShowOpp(true);
                    setForm({});
                  }}
                >
                  <Plus className="h-3.5 w-3.5" /> New opportunity
                </Button>
              ) : undefined
            }
          >
            <div className="space-y-3">
              {Object.entries(pipeline?.stages ?? {}).map(([stage, data]) => (
                <div key={stage} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-sm font-medium text-muted">
                    {stage}
                  </span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-canvas">
                    <div
                      className="h-full rounded-full bg-brand"
                      style={{
                        width: `${pipeline?.total_value ? Math.max(3, ((data.value ?? 0) / pipeline.total_value) * 100) : 0}%`,
                      }}
                    />
                  </div>
                  <span className="w-24 shrink-0 text-right text-sm text-ink">
                    {fmtMoney(data.value)}
                  </span>
                  <span className="w-10 shrink-0 text-right text-xs text-faint">
                    {data.count}
                  </span>
                </div>
              ))}
            </div>
            {!pipeline || pipeline.total_count === 0 ? (
              <EmptyState
                title="Empty pipeline"
                description="Add opportunities to track your deals."
              />
            ) : null}
          </Card>

          <Card title="Deals" bodyClassName="p-0">
            <Table
              head={
                <>
                  <Th>Deal</Th>
                  <Th>Customer</Th>
                  <Th>Stage</Th>
                  <Th>Probability</Th>
                  <Th>Value</Th>
                  <Th />
                </>
              }
            >
              {opportunities.map((o) => (
                <Tr key={o.id}>
                  <Td className="font-medium">{o.title}</Td>
                  <Td>{o.customer_name ?? "—"}</Td>
                  <Td>
                    <Badge tone={statusTone(o.stage)}>{o.stage}</Badge>
                  </Td>
                  <Td>{o.probability ?? 0}%</Td>
                  <Td>{fmtMoney(o.value)}</Td>
                  <Td className="text-right">
                    {canManage && o.stage === "negotiation" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={busy}
                        onClick={() => onWin(o)}
                      >
                        Won
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {opportunities.length === 0 && (
              <EmptyState
                title="No deals"
                description="Create opportunities to build your pipeline."
              />
            )}
          </Card>
        </div>
      )}

      {tab === "contracts" && (
        <Card
          title="Contracts"
          subtitle={`${contracts.length} contracts · ${contracts.filter((c) => c.status === "active").length} active`}
          actions={
            canManage ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setShowContract(true);
                  setForm({});
                }}
              >
                <Plus className="h-3.5 w-3.5" /> New contract
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table
            head={
              <>
                <Th>Title</Th>
                <Th>Customer</Th>
                <Th>Status</Th>
                <Th>Renewal</Th>
                <Th>Value</Th>
                <Th>Expires</Th>
              </>
            }
          >
            {contracts.map((c) => (
              <Tr key={c.id}>
                <Td className="font-medium">{c.title}</Td>
                <Td>{c.customer_name ?? "—"}</Td>
                <Td>
                  <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                </Td>
                <Td>
                  <Badge tone={statusTone(c.renewal_status)}>
                    {c.renewal_status}
                  </Badge>
                </Td>
                <Td>{fmtMoney(c.value)}</Td>
                <Td>{c.expires_at ? c.expires_at.slice(0, 10) : "—"}</Td>
              </Tr>
            ))}
          </Table>
          {contracts.length === 0 && (
            <EmptyState
              title="No contracts"
              description="Record customer contracts and renewal terms."
            />
          )}
        </Card>
      )}

      {tab === "support" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard
              label="Open tickets"
              value={supportSummary?.open ?? 0}
              icon={Activity}
            />
            <StatCard
              label="Escalated"
              value={supportSummary?.escalated ?? 0}
              icon={HeartPulse}
            />
            <StatCard
              label="Overdue SLA"
              value={supportSummary?.overdue ?? 0}
              icon={RefreshCw}
            />
            <StatCard
              label="Total"
              value={supportSummary?.total ?? 0}
              icon={Users}
            />
          </div>

          <Card
            title="Support tickets"
            actions={
              canManage ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setShowTicket(true);
                    setForm({});
                  }}
                >
                  <Plus className="h-3.5 w-3.5" /> New ticket
                </Button>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table
              head={
                <>
                  <Th>Subject</Th>
                  <Th>Customer</Th>
                  <Th>Priority</Th>
                  <Th>Status</Th>
                  <Th>Created</Th>
                  <Th />
                </>
              }
            >
              {tickets.map((t) => (
                <Tr key={t.id}>
                  <Td className="font-medium">{t.subject}</Td>
                  <Td>{t.customer_name ?? "—"}</Td>
                  <Td>
                    <Badge
                      tone={
                        t.priority === "high"
                          ? "danger"
                          : t.priority === "medium"
                            ? "warning"
                            : "neutral"
                      }
                    >
                      {t.priority}
                    </Badge>
                  </Td>
                  <Td>
                    <Badge tone={statusTone(t.status)}>{t.status}</Badge>
                  </Td>
                  <Td>{t.created_at ? t.created_at.slice(0, 10) : "—"}</Td>
                  <Td className="text-right">
                    {canManage && t.status === "open" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={busy}
                        onClick={() => onResolveTicket(t)}
                      >
                        Resolve
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {tickets.length === 0 && (
              <EmptyState
                title="No tickets"
                description="Support tickets from customers appear here."
              />
            )}
          </Card>
        </div>
      )}

      {tab === "partners" && (
        <Card
          title="Partners & vendors"
          subtitle={`${partnerSummary?.total ?? 0} partners · ${partnerSummary?.active ?? 0} active`}
          actions={
            canManage ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setShowPartner(true);
                  setForm({});
                }}
              >
                <Plus className="h-3.5 w-3.5" /> New partner
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table
            head={
              <>
                <Th>Name</Th>
                <Th>Kind</Th>
                <Th>Status</Th>
                <Th>Contact</Th>
                <Th>Country</Th>
              </>
            }
          >
            {partners.map((p) => (
              <Tr key={p.id}>
                <Td className="font-medium">{p.name}</Td>
                <Td>
                  <Badge tone="brand">{p.kind}</Badge>
                </Td>
                <Td>
                  <Badge tone={statusTone(p.status)}>{p.status}</Badge>
                </Td>
                <Td>{p.contact_name ?? "—"}</Td>
                <Td>{p.country ?? "—"}</Td>
              </Tr>
            ))}
          </Table>
          {partners.length === 0 && (
            <EmptyState
              title="No partners"
              description="Track channel, reseller, technology and vendor partners."
            />
          )}
        </Card>
      )}

      {tab === "analytics" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard
              label="Recognized revenue"
              value={fmtMoney(analytics?.revenue)}
              hint="active contracts"
              icon={TrendingUp}
            />
            <StatCard
              label="Top customer share"
              value={`${analytics?.concentration_risk.top_customer_share ?? 0}%`}
              hint="concentration risk"
              icon={PieChart}
            />
            <StatCard
              label="Active contracts"
              value={analytics?.contracts_active ?? 0}
              icon={FileSignature}
            />
            <StatCard
              label="Renewals due soon"
              value={analytics?.renewals_due ?? 0}
              icon={RefreshCw}
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="Portfolio growth"
              subtitle="Customers created per month"
            >
              <div className="flex items-end gap-2">
                {Object.entries(analytics?.growth ?? {}).map(
                  ([month, count]) => (
                    <div
                      key={month}
                      className="flex flex-1 flex-col items-center gap-1"
                    >
                      <span className="text-xs font-semibold text-ink">
                        {count}
                      </span>
                      <div
                        className="w-full rounded-t-md bg-brand"
                        style={{
                          height: `${Math.max(6, (count / Math.max(1, ...Object.values(analytics?.growth ?? {}))) * 72)}px`,
                        }}
                      />
                      <span className="text-[10px] text-faint">
                        {month.slice(5)}
                      </span>
                    </div>
                  ),
                )}
              </div>
            </Card>

            <Card
              title="Top customers by value"
              subtitle="Contract value concentration"
            >
              <div className="space-y-2.5">
                {analytics?.top_customers.map((c) => (
                  <div
                    key={c.customer_id}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="font-medium text-ink">
                      {c.company_name}
                    </span>
                    <span className="text-muted">{fmtMoney(c.value)}</span>
                  </div>
                ))}
              </div>
              {analytics?.top_customers.length === 0 && (
                <EmptyState
                  title="No contract revenue yet"
                  description="Sign contracts to see top accounts."
                />
              )}
            </Card>
          </div>

          <Card
            title="Relationship graph"
            subtitle="Customer–project–meeting–contract intelligence"
            actions={
              <Button
                size="sm"
                variant="ghost"
                loading={busy}
                onClick={onBuildGraph}
              >
                <RefreshCw className="h-3.5 w-3.5" /> Rebuild graph
              </Button>
            }
          >
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-line bg-surface p-4">
                <p className="text-xs text-faint">Customers in graph</p>
                <p className="mt-1 text-xl font-semibold text-ink">
                  {customers.length}
                </p>
              </div>
              <div className="rounded-xl border border-line bg-surface p-4">
                <p className="text-xs text-faint">Single points of failure</p>
                <p className="mt-1 text-xl font-semibold text-ink">
                  {risks?.total ?? 0}
                </p>
              </div>
            </div>
          </Card>
        </div>
      )}

      {tab === "ai" && (
        <div className="mx-auto max-w-3xl space-y-5">
          <Card
            title="CRM AI Companion"
            subtitle="Ask about renewals, at-risk accounts, next meetings and the pipeline."
          >
            <div className="flex gap-2">
              <Input
                placeholder="e.g. Which customers are at risk? Who should I meet next? Summarize StarCorp"
                value={aiQuestion}
                onChange={(e) => setAiQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") askAi();
                }}
              />
              <Button loading={busy} onClick={askAi}>
                <Send className="h-3.5 w-3.5" /> Ask
              </Button>
            </div>
            {ai && (
              <div className="mt-4 rounded-xl border border-line bg-surface p-4">
                <p className="text-sm leading-relaxed text-ink">{ai.answer}</p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Customer detail modal */}
      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.company_name ?? "Customer"}
        description={
          selected
            ? `${selected.segment} · ${selected.tier} · health ${selected.health_score}`
            : undefined
        }
        size="lg"
      >
        {selected && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs text-faint">Status</p>
                <p className="font-medium text-ink">{selected.status}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Industry</p>
                <p className="font-medium text-ink">
                  {selected.industry ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-faint">Country</p>
                <p className="font-medium text-ink">
                  {selected.country ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-faint">Annual value</p>
                <p className="font-medium text-ink">
                  {fmtMoney(selected.annual_value)}
                </p>
              </div>
              <div>
                <p className="text-xs text-faint">Owner</p>
                <p className="font-medium text-ink">
                  {selected.owner_name ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-faint">Health</p>
                <p className="font-medium text-ink">
                  {selected.health_score}{" "}
                  <span className="text-faint">· {selected.health_status}</span>
                </p>
              </div>
            </div>

            {selected.health?.signals && selected.health.signals.length > 0 && (
              <div>
                <p className="label">Signals</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {selected.health.signals.map((s) => (
                    <Badge key={s} tone="brand">
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <div>
              <p className="label">Notes</p>
              <div className="mt-2 space-y-2">
                {(selected.notes ?? []).slice(0, 5).map((n) => (
                  <div
                    key={n.id}
                    className="rounded-lg border border-line bg-surface p-3 text-sm"
                  >
                    <p className="text-ink">{n.content}</p>
                    <p className="mt-1 text-[11px] text-faint">
                      {n.kind} · {n.created_at ? n.created_at.slice(0, 10) : ""}
                    </p>
                  </div>
                ))}
                {selected.notes?.length === 0 && (
                  <p className="text-sm text-faint">No notes yet.</p>
                )}
              </div>
              <div className="mt-3 flex gap-2">
                <Textarea
                  placeholder="Add a note…"
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                />
                <Button variant="secondary" loading={busy} onClick={onAddNote}>
                  <MessageSquarePlus className="h-3.5 w-3.5" /> Add
                </Button>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Create modals */}
      <Modal
        open={showCustomer}
        onClose={() => setShowCustomer(false)}
        title="New customer"
        description="Add a company to the CRM"
      >
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Company name *"
            value={form.company_name ?? ""}
            onChange={(e) => setForm({ ...form, company_name: e.target.value })}
          />
          <Select
            label="Status"
            value={form.status ?? "customer"}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
            options={[
              { value: "customer", label: "Customer" },
              { value: "prospect", label: "Prospect" },
              { value: "inactive", label: "Inactive" },
            ]}
          />
          <Select
            label="Segment"
            value={form.segment ?? "mid_market"}
            onChange={(e) => setForm({ ...form, segment: e.target.value })}
            options={[
              { value: "enterprise", label: "Enterprise" },
              { value: "mid_market", label: "Mid market" },
              { value: "smb", label: "SMB" },
              { value: "startup", label: "Startup" },
              { value: "government", label: "Government" },
              { value: "nonprofit", label: "Nonprofit" },
            ]}
          />
          <Select
            label="Tier"
            value={form.tier ?? "basic"}
            onChange={(e) => setForm({ ...form, tier: e.target.value })}
            options={[
              { value: "basic", label: "Basic" },
              { value: "silver", label: "Silver" },
              { value: "gold", label: "Gold" },
              { value: "platinum", label: "Platinum" },
              { value: "enterprise", label: "Enterprise" },
            ]}
          />
          <Input
            label="Industry"
            value={form.industry ?? ""}
            onChange={(e) => setForm({ ...form, industry: e.target.value })}
          />
          <Input
            label="Country"
            value={form.country ?? ""}
            onChange={(e) => setForm({ ...form, country: e.target.value })}
          />
          <Input
            label="Website"
            value={form.website ?? ""}
            onChange={(e) => setForm({ ...form, website: e.target.value })}
          />
          <Input
            label="Annual value"
            type="number"
            value={form.annual_value ?? ""}
            onChange={(e) => setForm({ ...form, annual_value: e.target.value })}
          />
          <Input
            label="Description"
            className="col-span-2"
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowCustomer(false)}>
            Cancel
          </Button>
          <Button loading={busy} onClick={onCreateCustomer}>
            Create customer
          </Button>
        </div>
      </Modal>

      <Modal
        open={showLead}
        onClose={() => setShowLead(false)}
        title="New lead"
        description="Capture an inbound or sourced lead"
      >
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Company name *"
            value={form.company_name ?? ""}
            onChange={(e) => setForm({ ...form, company_name: e.target.value })}
          />
          <Input
            label="Contact name"
            value={form.contact_name ?? ""}
            onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
          />
          <Input
            label="Email"
            value={form.email ?? ""}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            label="Phone"
            value={form.phone ?? ""}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <Select
            label="Source"
            value={form.source ?? "website"}
            onChange={(e) => setForm({ ...form, source: e.target.value })}
            options={[
              { value: "website", label: "Website" },
              { value: "referral", label: "Referral" },
              { value: "marketing", label: "Marketing" },
              { value: "events", label: "Events" },
              { value: "cold_outreach", label: "Cold outreach" },
              { value: "partner", label: "Partner" },
            ]}
          />
          <Input
            label="Industry"
            value={form.industry ?? ""}
            onChange={(e) => setForm({ ...form, industry: e.target.value })}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowLead(false)}>
            Cancel
          </Button>
          <Button loading={busy} onClick={onCreateLead}>
            Create lead
          </Button>
        </div>
      </Modal>

      <Modal
        open={showOpp}
        onClose={() => setShowOpp(false)}
        title="New opportunity"
        description="Add a deal to the pipeline"
      >
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Title *"
            className="col-span-2"
            value={form.title ?? ""}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <Select
            label="Customer"
            value={form.customer_id ?? ""}
            onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
            options={customerOptions}
          />
          <Select
            label="Stage"
            value={form.stage ?? "qualified"}
            onChange={(e) => setForm({ ...form, stage: e.target.value })}
            options={[
              { value: "discovery", label: "Discovery" },
              { value: "qualified", label: "Qualified" },
              { value: "proposal", label: "Proposal" },
              { value: "negotiation", label: "Negotiation" },
            ]}
          />
          <Input
            label="Value"
            type="number"
            value={form.value ?? ""}
            onChange={(e) => setForm({ ...form, value: e.target.value })}
          />
          <Input
            label="Probability (%)"
            type="number"
            value={form.probability ?? ""}
            onChange={(e) => setForm({ ...form, probability: e.target.value })}
          />
          <Input
            label="Expected close"
            type="date"
            value={form.expected_close_at ?? ""}
            onChange={(e) =>
              setForm({ ...form, expected_close_at: e.target.value })
            }
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowOpp(false)}>
            Cancel
          </Button>
          <Button loading={busy} onClick={onCreateOpp}>
            Create opportunity
          </Button>
        </div>
      </Modal>

      <Modal
        open={showContract}
        onClose={() => setShowContract(false)}
        title="New contract"
        description="Record a customer contract"
      >
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Title *"
            className="col-span-2"
            value={form.title ?? ""}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <Select
            label="Customer"
            value={form.customer_id ?? ""}
            onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
            options={customerOptions}
          />
          <Select
            label="Kind"
            value={form.kind ?? "subscription"}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
            options={[
              { value: "subscription", label: "Subscription" },
              { value: "retainer", label: "Retainer" },
              { value: "project", label: "Project" },
              { value: "maintenance", label: "Maintenance" },
            ]}
          />
          <Input
            label="Value"
            type="number"
            value={form.value ?? ""}
            onChange={(e) => setForm({ ...form, value: e.target.value })}
          />
          <Input
            label="Effective from"
            type="date"
            value={form.effective_from ?? ""}
            onChange={(e) =>
              setForm({ ...form, effective_from: e.target.value })
            }
          />
          <Input
            label="Expires at"
            type="date"
            value={form.expires_at ?? ""}
            onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
          />
          <Input
            label="Currency"
            value={form.currency ?? "USD"}
            onChange={(e) => setForm({ ...form, currency: e.target.value })}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowContract(false)}>
            Cancel
          </Button>
          <Button loading={busy} onClick={onCreateContract}>
            Create contract
          </Button>
        </div>
      </Modal>

      <Modal
        open={showTicket}
        onClose={() => setShowTicket(false)}
        title="New support ticket"
        description="Log a customer support request"
      >
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Subject *"
            className="col-span-2"
            value={form.subject ?? ""}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
          />
          <Select
            label="Customer"
            value={form.customer_id ?? ""}
            onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
            options={customerOptions}
          />
          <Select
            label="Category"
            value={form.category ?? "other"}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            options={[
              { value: "bug", label: "Bug" },
              { value: "feature", label: "Feature request" },
              { value: "billing", label: "Billing" },
              { value: "access", label: "Access" },
              { value: "training", label: "Training" },
              { value: "other", label: "Other" },
            ]}
          />
          <Select
            label="Priority"
            value={form.priority ?? "medium"}
            onChange={(e) => setForm({ ...form, priority: e.target.value })}
            options={[
              { value: "low", label: "Low" },
              { value: "medium", label: "Medium" },
              { value: "high", label: "High" },
              { value: "critical", label: "Critical" },
            ]}
          />
          <Textarea
            label="Description"
            className="col-span-2"
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowTicket(false)}>
            Cancel
          </Button>
          <Button loading={busy} onClick={onCreateTicket}>
            Create ticket
          </Button>
        </div>
      </Modal>

      <Modal
        open={showPartner}
        onClose={() => setShowPartner(false)}
        title="New partner"
        description="Add a partner, reseller or vendor"
      >
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Name *"
            value={form.name ?? ""}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Select
            label="Kind"
            value={form.kind ?? "channel"}
            onChange={(e) => setForm({ ...form, kind: e.target.value })}
            options={[
              { value: "channel", label: "Channel" },
              { value: "reseller", label: "Reseller" },
              { value: "technology", label: "Technology" },
              { value: "vendor", label: "Vendor" },
            ]}
          />
          <Input
            label="Contact name"
            value={form.contact_name ?? ""}
            onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
          />
          <Input
            label="Email"
            value={form.email ?? ""}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <Input
            label="Phone"
            value={form.phone ?? ""}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
          <Input
            label="Website"
            value={form.website ?? ""}
            onChange={(e) => setForm({ ...form, website: e.target.value })}
          />
          <Input
            label="Country"
            value={form.country ?? ""}
            onChange={(e) => setForm({ ...form, country: e.target.value })}
          />
          <Textarea
            label="Description"
            className="col-span-2"
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowPartner(false)}>
            Cancel
          </Button>
          <Button loading={busy} onClick={onCreatePartner}>
            Create partner
          </Button>
        </div>
      </Modal>
    </div>
  );
}
