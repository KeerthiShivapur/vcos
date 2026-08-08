"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeftRight,
  Banknote,
  FileText,
  Handshake,
  LayoutDashboard,
  LineChart,
  Package,
  PieChart,
  Plus,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Wallet,
} from "lucide-react";

import {
  askFinanceAi,
  createBudget,
  createExpense,
  createIntegration,
  createInvoice,
  createPayment,
  createPurchaseOrder,
  createPurchaseRequest,
  createVendor,
  createVendorContract,
  decideExpense,
  decidePurchaseRequest,
  generateForecasts,
  getBudgetSummary,
  getFinanceDashboard,
  getInvoiceSummary,
  getIntegrationsHealth,
  getRiskSummary,
  getVendorSummary,
  listBudgets,
  listExpenses,
  listForecasts,
  listInvoices,
  listIntegrations,
  listPayments,
  listPurchaseOrders,
  listPurchaseRequests,
  listVendors,
  listVendorContracts,
  markInvoicesOverdue,
  renewVendorContract,
  scanFinanceRisks,
  syncIntegration,
  updatePurchaseOrder,
} from "@/lib/api";
import type {
  Budget,
  Expense,
  FinanceAiReply,
  FinanceDashboard,
  FinanceIntegration,
  FinancialForecast,
  Invoice,
  Payment,
  PurchaseOrder,
  PurchaseRequest,
  RiskItem,
  RiskSummary,
  Vendor,
  VendorContract,
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
import { Textarea } from "@/components/ui/Textarea";
import { Modal } from "@/components/ui/Modal";
import { Table, Th, Td, Tr } from "@/components/ui/Table";

export default function FinancePage() {
  return (
    <Suspense fallback={null}>
      <FinanceContent />
    </Suspense>
  );
}

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "budgets", label: "Budgets", icon: PieChart },
  { id: "expenses", label: "Expenses", icon: Wallet },
  { id: "procurement", label: "Procurement", icon: Package },
  { id: "vendors", label: "Vendors", icon: Handshake },
  { id: "invoices", label: "Invoices", icon: FileText },
  { id: "forecasting", label: "Forecasting", icon: LineChart },
  { id: "ai", label: "Finance AI", icon: Sparkles },
];

const fmtMoney = (value?: number | null) =>
  value == null ? "—" : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const severityTone = (level?: string | null) =>
  level === "critical" ? "danger" : level === "high" ? "danger" : level === "medium" ? "warning" : level === "low" ? "neutral" : "brand";

const riskLevelTone = (level?: string | null) =>
  level === "critical" || level === "high" ? "danger" : level === "medium" ? "warning" : "success";

const EXPENSE_TYPES = [
  "travel", "food", "office_supplies", "software", "hardware", "training",
  "marketing", "client_entertainment", "professional_services", "miscellaneous",
].map((v) => ({ value: v, label: v.replace(/_/g, " ") }));

const REQUEST_CATEGORIES = [
  "laptop", "monitor", "software", "furniture", "services", "cloud",
  "training", "equipment", "marketing", "other",
].map((v) => ({ value: v, label: v }));

const BUDGET_TYPES = ["department", "project", "team", "company"].map((v) => ({ value: v, label: v }));

function FinanceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.FINANCE_MANAGE);

  const tab = searchParams.get("tab") ?? "overview";
  const setTab = (id: string) => router.replace(`/finance?tab=${id}`);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [dashboard, setDashboard] = useState<FinanceDashboard | null>(null);
  const [budgetSummary, setBudgetSummary] = useState<{ total_budgets: number; allocated: number; used: number; remaining: number; usage_pct: number; risk_counts: Record<string, number> } | null>(null);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [vendorSummary, setVendorSummary] = useState<{ total: number; active: number; high_risk: number; by_kind: Record<string, number> } | null>(null);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [contracts, setContracts] = useState<VendorContract[]>([]);
  const [invoiceSummary, setInvoiceSummary] = useState<{ total: number; payable: { count: number; due: number; paid: number; overdue: number }; receivable: { count: number; due: number; paid: number; overdue: number }; overdue: number } | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [requests, setRequests] = useState<PurchaseRequest[]>([]);
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [forecasts, setForecasts] = useState<FinancialForecast[]>([]);
  const [integrations, setIntegrations] = useState<FinanceIntegration[]>([]);
  const [integrationHealth, setIntegrationHealth] = useState<{ connected: number; total: number } | null>(null);
  const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);

  const [ai, setAi] = useState<FinanceAiReply | null>(null);
  const [aiQuestion, setAiQuestion] = useState("");

  const [selectedVendor, setSelectedVendor] = useState<Vendor | null>(null);
  const [selectedBudget, setSelectedBudget] = useState<Budget | null>(null);
  const [selectedRequest, setSelectedRequest] = useState<PurchaseRequest | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<PurchaseOrder | null>(null);

  const [showBudget, setShowBudget] = useState(false);
  const [showExpense, setShowExpense] = useState(false);
  const [showVendor, setShowVendor] = useState(false);
  const [showContract, setShowContract] = useState(false);
  const [showInvoice, setShowInvoice] = useState(false);
  const [showRequest, setShowRequest] = useState(false);
  const [showIntegration, setShowIntegration] = useState(false);

  const [form, setForm] = useState<Record<string, string>>({});

  const loadAll = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    setError(null);
    try {
      const [
        dashRes, budgetSumRes, budgetsRes, expensesRes, vendorSumRes, vendorsRes,
        contractsRes, invoiceSumRes, invoicesRes, paymentsRes, requestsRes, ordersRes,
        forecastsRes, integrationsRes, healthRes, risksRes,
      ] = await Promise.allSettled([
        getFinanceDashboard(),
        getBudgetSummary(),
        listBudgets({}),
        listExpenses({}),
        getVendorSummary(),
        listVendors({}),
        listVendorContracts({}),
        getInvoiceSummary(),
        listInvoices({}),
        listPayments({}),
        listPurchaseRequests({}),
        listPurchaseOrders({}),
        listForecasts({}),
        listIntegrations(),
        getIntegrationsHealth(),
        getRiskSummary(),
      ]);
      const ok = <T,>(r: PromiseSettledResult<T>): T | null => (r.status === "fulfilled" ? r.value : null);
      setDashboard(ok(dashRes));
      setBudgetSummary(ok(budgetSumRes));
      setBudgets(ok(budgetsRes) ?? []);
      setExpenses(ok(expensesRes) ?? []);
      setVendorSummary(ok(vendorSumRes));
      setVendors(ok(vendorsRes) ?? []);
      setContracts(ok(contractsRes) ?? []);
      setInvoiceSummary(ok(invoiceSumRes));
      setInvoices(ok(invoicesRes) ?? []);
      setPayments(ok(paymentsRes) ?? []);
      setRequests(ok(requestsRes) ?? []);
      setOrders(ok(ordersRes) ?? []);
      setForecasts(ok(forecastsRes) ?? []);
      setIntegrations(ok(integrationsRes) ?? []);
      setIntegrationHealth(ok(healthRes));
      setRiskSummary(ok(risksRes));
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

  const run = async (fn: () => Promise<unknown>, okMessage: string, then?: () => void) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(okMessage);
      await loadAll();
      then?.();
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
      const res = await askFinanceAi(aiQuestion);
      setAi(res);
      setAiQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const openVendor = async (vendorId: string) => {
    try {
      const detail = await import("@/lib/api").then((m) => m.getVendor(vendorId));
      setSelectedVendor(detail);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const vendorOptions = useMemo(
    () => vendors.map((v) => ({ value: v.id, label: v.name })),
    [vendors]
  );

  const budgetOptions = useMemo(
    () =>
      budgets
        .filter((b) => b.status === "active")
        .map((b) => ({ value: b.id, label: `${b.name} (${fmtMoney(b.remaining_amount)} left)` })),
    [budgets]
  );

  const approvedRequests = useMemo(
    () => requests.filter((r) => r.status === "approved"),
    [requests]
  );

  // ---------------------------------------------------------------- handlers

  const onCreateBudget = async () => {
    if (!form.name?.trim()) {
      setError("Name is required.");
      return;
    }
    await run(
      () => createBudget({ ...form, allocated_amount: Number(form.allocated_amount || 0) }),
      "Budget created."
    );
    setShowBudget(false);
    setForm({});
  };

  const onCreateExpense = async () => {
    if (!form.description?.trim()) {
      setError("Description is required.");
      return;
    }
    await run(
      () => createExpense({ ...form, amount: Number(form.amount || 0) }),
      "Expense submitted."
    );
    setShowExpense(false);
    setForm({});
  };

  const onDecideExpense = async (expense: Expense, decision: string) => {
    await run(() => decideExpense(expense.id, decision), `Expense ${decision}.`);
  };

  const onCreateVendor = async () => {
    if (!form.name?.trim()) {
      setError("Name is required.");
      return;
    }
    await run(() => createVendor(form), "Vendor created.");
    setShowVendor(false);
    setForm({});
  };

  const onCreateContract = async () => {
    if (!form.title?.trim()) {
      setError("Title is required.");
      return;
    }
    await run(
      () => createVendorContract({ ...form, value: form.value ? Number(form.value) : null }),
      "Contract created."
    );
    setShowContract(false);
    setForm({});
  };

  const onRenewContract = async (contract: VendorContract) => {
    const months = Number(window.prompt(`Renew for how many months? (current: ${contract.days_left ?? "?"} days left)`, "12") ?? 12);
    if (!months || months <= 0) return;
    await run(() => renewVendorContract(contract.id, { months }), "Contract renewed.");
  };

  const onCreateInvoice = async () => {
    if (!form.title?.trim()) {
      setError("Title is required.");
      return;
    }
    await run(
      () => createInvoice({ ...form, amount: Number(form.amount || 0), tax_amount: Number(form.tax_amount || 0) }),
      "Invoice created."
    );
    setShowInvoice(false);
    setForm({});
  };

  const onPayInvoice = async (invoice: Invoice) => {
    await run(
      () => createPayment({ invoice_id: invoice.id, amount: invoice.amount, currency: invoice.currency, method: "bank_transfer" }),
      "Payment recorded."
    );
  };

  const onCreateRequest = async () => {
    if (!form.title?.trim()) {
      setError("Title is required.");
      return;
    }
    await run(
      () => createPurchaseRequest({ ...form, estimated_cost: form.estimated_cost ? Number(form.estimated_cost) : null, quantity: Number(form.quantity || 1) }),
      "Purchase request submitted."
    );
    setShowRequest(false);
    setForm({});
  };

  const onDecideRequest = async (request: PurchaseRequest, decision: string) => {
    await run(() => decidePurchaseRequest(request.id, decision), `Request ${decision === "approve" ? "approved" : decision}d.`);
  };

  const onCreateOrder = async (request: PurchaseRequest) => {
    await run(
      () => createPurchaseOrder({ purchase_request_id: request.id, vendor_id: request.vendor_id, total_amount: request.estimated_cost ?? 0, currency: request.currency }),
      "Purchase order issued."
    );
  };

  const onMarkDelivered = async (order: PurchaseOrder) => {
    await run(() => updatePurchaseOrder(order.id, { status: "delivered" }), "Order marked delivered.");
  };

  const onGenerateForecasts = async () => {
    await run(() => generateForecasts({ kind: "all", horizon_months: 6 }), "Forecasts generated.");
  };

  const onScanRisks = async () => {
    await run(() => scanFinanceRisks(), "Risk scan complete.");
  };

  const onMarkOverdue = async () => {
    await run(() => markInvoicesOverdue(), "Overdue invoices marked.");
  };

  const onSyncIntegration = async (integration: FinanceIntegration) => {
    await run(() => syncIntegration(integration.id, false), `${integration.provider} synced.`);
  };

  const onCreateIntegration = async () => {
    if (!form.platform?.trim()) {
      setError("Platform is required.");
      return;
    }
    await run(
      () => createIntegration({ platform: form.platform, display_name: form.display_name || form.platform, config: { expenses_count: 0 } }),
      "Integration connected."
    );
    setShowIntegration(false);
    setForm({});
  };

  if (loading) return <Spinner label="Loading finance…" />;
  if (error && !notice) return <ErrorState message={error} onRetry={() => loadAll(true)} />;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Finance"
        title="Finance & Business Operations"
        description="Budgets, expenses, procurement, vendors, invoices, forecasting, integrations and financial intelligence."
        actions={
          canManage ? (
            <>
              <Button variant="secondary" loading={busy} onClick={() => { setShowBudget(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> Budget
              </Button>
              <Button variant="secondary" loading={busy} onClick={() => { setShowExpense(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> Expense
              </Button>
            </>
          ) : undefined
        }
      />

      {notice && (
        <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-2.5 text-sm text-success">{notice}</div>
      )}
      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">{error}</div>
      )}

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Budget remaining" value={fmtMoney(dashboard?.budget_remaining)} hint={`${dashboard?.budget_usage_pct ?? 0}% used`} icon={PieChart} />
            <StatCard label="Operating costs" value={fmtMoney(dashboard?.operating_costs)} hint={`${dashboard?.high_risk_budgets ?? 0} budgets at risk`} icon={Wallet} />
            <StatCard label="Revenue" value={fmtMoney(dashboard?.revenue)} hint={`${dashboard?.receivable_due ?? 0} receivable due`} icon={TrendingUp} />
            <StatCard label="Pending approvals" value={dashboard?.pending_approvals ?? 0} hint="expenses + purchase requests" icon={ShieldAlert} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="Financial risk scan"
              subtitle={`Health score ${riskSummary?.health_score ?? 0} · ${riskSummary?.total ?? 0} risks`}
              actions={
                canManage ? (
                  <Button size="sm" variant="ghost" loading={busy} onClick={onScanRisks}>
                    <RefreshCw className="h-3.5 w-3.5" /> Scan
                  </Button>
                ) : undefined
              }
              bodyClassName="p-0"
            >
              <Table head={<><Th>Type</Th><Th>Severity</Th><Th>Detail</Th></>}>
                {(riskSummary?.risks ?? []).slice(0, 6).map((risk) => (
                  <Tr key={risk.id}>
                    <Td className="font-medium">{risk.type}</Td>
                    <Td><Badge tone={severityTone(risk.severity)}>{risk.severity}</Badge></Td>
                    <Td className="text-muted">{risk.message}</Td>
                  </Tr>
                ))}
              </Table>
              {(riskSummary?.risks ?? []).length === 0 && (
                <EmptyState title="No risks detected" description="Run a scan to review budgets, payments, invoices and vendors." />
              )}
            </Card>

            <Card
              title="Approvals pipeline"
              subtitle="Expenses and purchase requests waiting on decisions"
              bodyClassName="p-0"
            >
              <Table head={<><Th>Item</Th><Th>Kind</Th><Th>Status</Th><Th>Amount</Th></>}>
                {expenses.filter((e) => e.status === "submitted" || e.status === "pending").slice(0, 4).map((e) => (
                  <Tr key={`e-${e.id}`}>
                    <Td className="font-medium">{e.description}</Td>
                    <Td>expense</Td>
                    <Td><Badge tone="warning">{e.status}</Badge></Td>
                    <Td>{fmtMoney(e.amount)}</Td>
                  </Tr>
                ))}
                {requests.filter((r) => r.status === "submitted" || r.status === "manager_approved").slice(0, 4).map((r) => (
                  <Tr key={`r-${r.id}`}>
                    <Td className="font-medium">{r.title}</Td>
                    <Td>request</Td>
                    <Td><Badge tone="warning">{r.status}</Badge></Td>
                    <Td>{fmtMoney(r.estimated_cost)}</Td>
                  </Tr>
                ))}
              </Table>
              {expenses.filter((e) => e.status === "submitted" || e.status === "pending").length === 0 &&
                requests.filter((r) => r.status === "submitted" || r.status === "manager_approved").length === 0 && (
                  <EmptyState title="Nothing pending" description="All approvals are up to date." />
                )}
            </Card>
          </div>

          <Card title="Budgets" subtitle={`${budgetSummary?.total_budgets ?? 0} budgets · ${fmtMoney(budgetSummary?.remaining)} remaining`} bodyClassName="p-0">
            <Table head={<><Th>Budget</Th><Th>Allocated</Th><Th>Used</Th><Th>Remaining</Th><Th>Usage</Th><Th>Risk</Th></>}>
              {budgets.slice(0, 8).map((b) => (
                <Tr key={b.id} onClick={() => setSelectedBudget(b)}>
                  <Td className="font-medium">{b.name}</Td>
                  <Td>{fmtMoney(b.allocated_amount)}</Td>
                  <Td>{fmtMoney(b.used_amount)}</Td>
                  <Td>{fmtMoney(b.remaining_amount)}</Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-canvas">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, b.usage_pct)}%` }} />
                      </div>
                      <span className="text-xs text-faint">{b.usage_pct}%</span>
                    </div>
                  </Td>
                  <Td><Badge tone={riskLevelTone(b.risk_level)}>{b.risk_level}</Badge></Td>
                </Tr>
              ))}
            </Table>
            {budgets.length === 0 && <EmptyState title="No budgets yet" description="Create budgets to track spend." />}
          </Card>
        </div>
      )}

      {tab === "budgets" && (
        <Card
          title="Budgets"
          subtitle={`${budgetSummary?.total_budgets ?? 0} budgets · ${fmtMoney(budgetSummary?.allocated)} allocated`}
          actions={
            canManage ? (
              <Button size="sm" variant="secondary" onClick={() => { setShowBudget(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> New budget
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table head={<><Th>Budget</Th><Th>Type</Th><Th>Allocated</Th><Th>Used</Th><Th>Remaining</Th><Th>Usage</Th><Th>Risk</Th><Th>Status</Th></>}>
            {budgets.map((b) => (
              <Tr key={b.id} onClick={() => setSelectedBudget(b)}>
                <Td className="font-medium">{b.name}</Td>
                <Td><Badge tone="brand">{b.budget_type}</Badge></Td>
                <Td>{fmtMoney(b.allocated_amount)}</Td>
                <Td>{fmtMoney(b.used_amount)}</Td>
                <Td>{fmtMoney(b.remaining_amount)}</Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 overflow-hidden rounded-full bg-canvas">
                      <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, b.usage_pct)}%` }} />
                    </div>
                    <span className="text-xs text-faint">{b.usage_pct}%</span>
                  </div>
                </Td>
                <Td><Badge tone={riskLevelTone(b.risk_level)}>{b.risk_level}</Badge></Td>
                <Td><Badge tone={statusTone(b.status)}>{b.status}</Badge></Td>
              </Tr>
            ))}
          </Table>
          {budgets.length === 0 && <EmptyState title="No budgets yet" description="Create your first budget to get started." />}
        </Card>
      )}

      {tab === "expenses" && (
        <Card
          title="Expenses"
          subtitle={`${expenses.length} expenses`}
          actions={
            canManage ? (
              <Button size="sm" variant="secondary" onClick={() => { setShowExpense(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> New expense
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table head={<><Th>Description</Th><Th>Type</Th><Th>Merchant</Th><Th>Amount</Th><Th>Status</Th><Th>Flags</Th><Th /></>}>
            {expenses.map((e) => {
              const flagged = Boolean(e.policy_flags?.flagged);
              return (
                <Tr key={e.id}>
                  <Td className="font-medium">{e.description}</Td>
                  <Td><Badge tone="brand">{e.expense_type}</Badge></Td>
                  <Td className="text-muted">{e.merchant ?? "—"}</Td>
                  <Td>{fmtMoney(e.amount)}</Td>
                  <Td><Badge tone={statusTone(e.status)}>{e.status}</Badge></Td>
                  <Td>{flagged ? <Badge tone="danger">flagged</Badge> : <span className="text-xs text-faint">clean</span>}</Td>
                  <Td className="text-right">
                    {canManage && (e.status === "submitted" || e.status === "pending") && (
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="secondary" loading={busy} onClick={() => onDecideExpense(e, "approved")}>Approve</Button>
                        <Button size="sm" variant="ghost" loading={busy} onClick={() => onDecideExpense(e, "rejected")}>Reject</Button>
                      </div>
                    )}
                  </Td>
                </Tr>
              );
            })}
          </Table>
          {expenses.length === 0 && <EmptyState title="No expenses" description="Submit an expense to start tracking spend." />}
        </Card>
      )}

      {tab === "procurement" && (
        <div className="space-y-5">
          <Card
            title="Purchase requests"
            subtitle={`${requests.length} requests · ${approvedRequests.length} approved`}
            actions={
              canManage ? (
                <Button size="sm" variant="secondary" onClick={() => { setShowRequest(true); setForm({}); }}>
                  <Plus className="h-3.5 w-3.5" /> New request
                </Button>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Title</Th><Th>Category</Th><Th>Est. cost</Th><Th>Status</Th><Th /></>}>
              {requests.map((r) => (
                <Tr key={r.id} onClick={() => setSelectedRequest(r)}>
                  <Td className="font-medium">{r.title}</Td>
                  <Td><Badge tone="brand">{r.category}</Badge></Td>
                  <Td>{fmtMoney(r.estimated_cost)}</Td>
                  <Td><Badge tone={statusTone(r.status)}>{r.status}</Badge></Td>
                  <Td className="text-right">
                    {canManage && r.status === "submitted" && (
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onDecideRequest(r, "approve")}>Manager approve</Button>
                    )}
                    {canManage && r.status === "manager_approved" && (
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onDecideRequest(r, "approve")}>Finance approve</Button>
                    )}
                    {canManage && r.status === "approved" && (
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onCreateOrder(r)}>
                        <Package className="h-3.5 w-3.5" /> Issue PO
                      </Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {requests.length === 0 && <EmptyState title="No purchase requests" description="Requests flow through manager and finance approval before ordering." />}
          </Card>

          <Card title="Purchase orders" subtitle={`${orders.length} orders`} bodyClassName="p-0">
            <Table head={<><Th>PO number</Th><Th>Title</Th><Th>Vendor</Th><Th>Total</Th><Th>Status</Th><Th /></>}>
              {orders.map((o) => (
                <Tr key={o.id} onClick={() => setSelectedOrder(o)}>
                  <Td className="font-medium">{o.po_number}</Td>
                  <Td>{o.title}</Td>
                  <Td className="text-muted">{o.vendor_name ?? "—"}</Td>
                  <Td>{fmtMoney(o.total_amount)}</Td>
                  <Td><Badge tone={statusTone(o.status)}>{o.status}</Badge></Td>
                  <Td className="text-right">
                    {canManage && (o.status === "issued" || o.status === "accepted" || o.status === "partially_delivered") && (
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onMarkDelivered(o)}>Delivered</Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {orders.length === 0 && <EmptyState title="No purchase orders" description="Issue POs from approved requests." />}
          </Card>
        </div>
      )}

      {tab === "vendors" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Vendors" value={vendorSummary?.total ?? 0} hint={`${vendorSummary?.active ?? 0} active`} icon={Handshake} />
            <StatCard label="High risk" value={vendorSummary?.high_risk ?? 0} hint="medium or high risk profile" icon={ShieldAlert} />
            <StatCard label="Contracts" value={contracts.length} hint={`${contracts.filter((c) => c.renewal_status === "due_soon" || c.renewal_status === "overdue").length} renewing soon`} icon={FileText} />
            <StatCard label="Integrations" value={integrationHealth?.connected ?? 0} hint={`${integrationHealth?.total ?? 0} connected systems`} icon={ArrowLeftRight} />
          </div>

          <Card
            title="Vendors"
            subtitle={`${vendors.length} vendors`}
            actions={
              canManage ? (
                <>
                  <Button size="sm" variant="secondary" onClick={() => { setShowVendor(true); setForm({}); }}>
                    <Plus className="h-3.5 w-3.5" /> New vendor
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { setShowContract(true); setForm({}); }}>
                    <Plus className="h-3.5 w-3.5" /> Contract
                  </Button>
                </>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Name</Th><Th>Kind</Th><Th>Status</Th><Th>Rating</Th><Th>Risk</Th><Th>Spend</Th></>}>
              {vendors.map((v) => (
                <Tr key={v.id} onClick={() => openVendor(v.id)}>
                  <Td className="font-medium">{v.name}</Td>
                  <Td><Badge tone="brand">{v.kind}</Badge></Td>
                  <Td><Badge tone={statusTone(v.status)}>{v.status}</Badge></Td>
                  <Td>{v.rating ?? "—"}</Td>
                  <Td>
                    {v.risk ? (
                      <Badge tone={riskLevelTone(v.risk.level)}>{v.risk.level} · {v.risk.score}</Badge>
                    ) : <span className="text-xs text-faint">—</span>}
                  </Td>
                  <Td>{fmtMoney(v.total_spend)}</Td>
                </Tr>
              ))}
            </Table>
            {vendors.length === 0 && <EmptyState title="No vendors" description="Track suppliers, consultants, contractors and partners." />}
          </Card>

          {integrations.length > 0 && (
            <Card title="ERP integrations" subtitle="Connected finance platforms" bodyClassName="p-0">
              <Table head={<><Th>Provider</Th><Th>Type</Th><Th>Status</Th><Th>Last sync</Th><Th /></>}>
                {integrations.map((i) => (
                  <Tr key={i.id}>
                    <Td className="font-medium">{i.provider}</Td>
                    <Td><Badge tone="brand">{i.integration_type}</Badge></Td>
                    <Td><Badge tone={statusTone(i.status)}>{i.status}</Badge></Td>
                    <Td>{i.last_synced_at ? i.last_synced_at.slice(0, 10) : "never"}</Td>
                    <Td className="text-right">
                      {canManage && (
                        <Button size="sm" variant="secondary" loading={busy} onClick={() => onSyncIntegration(i)}>
                          <RefreshCw className="h-3.5 w-3.5" /> Sync
                        </Button>
                      )}
                    </Td>
                  </Tr>
                ))}
              </Table>
            </Card>
          )}
        </div>
      )}

      {tab === "invoices" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Overdue" value={invoiceSummary?.overdue ?? 0} icon={ShieldAlert} />
            <StatCard label="Payable due" value={fmtMoney(invoiceSummary?.payable.due)} hint={`${invoiceSummary?.payable.count ?? 0} open`} icon={ArrowLeftRight} />
            <StatCard label="Receivable due" value={fmtMoney(invoiceSummary?.receivable.due)} hint={`${invoiceSummary?.receivable.count ?? 0} open`} icon={TrendingUp} />
            <StatCard label="Paid (payable)" value={fmtMoney(invoiceSummary?.payable.paid)} icon={Banknote} />
          </div>

          <Card
            title="Invoices"
            subtitle={`${invoices.length} invoices`}
            actions={
              canManage ? (
                <>
                  <Button size="sm" variant="ghost" loading={busy} onClick={onMarkOverdue}>
                    <RefreshCw className="h-3.5 w-3.5" /> Mark overdue
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => { setShowInvoice(true); setForm({}); }}>
                    <Plus className="h-3.5 w-3.5" /> New invoice
                  </Button>
                </>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Title</Th><Th>Direction</Th><Th>Counterparty</Th><Th>Amount</Th><Th>Due</Th><Th>Status</Th><Th /></>}>
              {invoices.map((inv) => (
                <Tr key={inv.id}>
                  <Td className="font-medium">{inv.title}</Td>
                  <Td><Badge tone={inv.direction === "payable" ? "warning" : "success"}>{inv.direction}</Badge></Td>
                  <Td className="text-muted">{inv.vendor_name ?? inv.customer_name ?? "—"}</Td>
                  <Td>{fmtMoney(inv.amount)}</Td>
                  <Td>{inv.due_at ?? "—"}</Td>
                  <Td><Badge tone={statusTone(inv.status)}>{inv.status}</Badge></Td>
                  <Td className="text-right">
                    {canManage && inv.status === "pending" && (
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onPayInvoice(inv)}>Pay</Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {invoices.length === 0 && <EmptyState title="No invoices" description="Create payable and receivable invoices." />}
          </Card>

          {payments.length > 0 && (
            <Card title="Recent payments" bodyClassName="p-0">
              <Table head={<><Th>Method</Th><Th>Reference</Th><Th>Amount</Th><Th>Status</Th><Th>Paid at</Th></>}>
                {payments.slice(0, 8).map((p) => (
                  <Tr key={p.id}>
                    <Td><Badge tone="brand">{p.method}</Badge></Td>
                    <Td className="text-muted">{p.reference ?? "—"}</Td>
                    <Td>{fmtMoney(p.amount)}</Td>
                    <Td><Badge tone={statusTone(p.status)}>{p.status}</Badge></Td>
                    <Td>{p.paid_at ? p.paid_at.slice(0, 10) : "—"}</Td>
                  </Tr>
                ))}
              </Table>
            </Card>
          )}
        </div>
      )}

      {tab === "forecasting" && (
        <div className="space-y-5">
          <Card
            title="Financial forecasting"
            subtitle="Explainable cash flow, budget usage, expense, revenue and project profitability projections"
            actions={
              canManage ? (
                <Button size="sm" variant="secondary" loading={busy} onClick={onGenerateForecasts}>
                  <LineChart className="h-3.5 w-3.5" /> Generate forecasts
                </Button>
              ) : undefined
            }
          >
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {["cash_flow", "budget_usage", "expense", "revenue"].map((kind) => {
                const forecast = forecasts.find((f) => f.kind === kind);
                const points = (forecast?.forecast_data?.monthly ?? []) as { month: string; value: number }[];
                const latest = points[points.length - 1];
                return (
                  <div key={kind} className="rounded-xl border border-line bg-surface p-4">
                    <p className="text-xs font-medium text-faint">{kind.replace(/_/g, " ")}</p>
                    <p className="mt-1 text-xl font-semibold text-ink">
                      {forecast ? fmtMoney(latest?.value) : "—"}
                    </p>
                    <p className="mt-1 text-[11px] text-muted">
                      {forecast ? `${forecast.horizon_months} months · ${forecast.confidence}% confidence` : "Not generated yet"}
                    </p>
                    {points.length > 0 && (
                      <div className="mt-3 flex items-end gap-1">
                        {points.slice(-10).map((point, index) => (
                          <div
                            key={index}
                            className="flex-1 rounded-t bg-brand/70"
                            style={{ height: `${Math.max(4, (point.value / Math.max(1, ...points.map((p) => p.value))) * 40)}px` }}
                            title={`${point.month}: ${fmtMoney(point.value)}`}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-4 text-xs text-faint">
              Forecasts are computed from paid invoices, approved expenses and budgets, with variance-based confidence.
            </div>
          </Card>

          <Card title="Project profitability" subtitle="Margin outlook per project" bodyClassName="p-0">
            <Table head={<><Th>Kind</Th><Th>Horizon</Th><Th>Confidence</Th><Th>Generated</Th></>}>
              {forecasts.map((f) => (
                <Tr key={f.id}>
                  <Td className="font-medium">{f.kind}</Td>
                  <Td>{f.horizon_months} months</Td>
                  <Td><Badge tone="success">{f.confidence}%</Badge></Td>
                  <Td>{f.created_at ? f.created_at.slice(0, 10) : "—"}</Td>
                </Tr>
              ))}
            </Table>
            {forecasts.length === 0 && <EmptyState title="No forecasts" description="Generate forecasts to see projections." />}
          </Card>
        </div>
      )}

      {tab === "ai" && (
        <div className="mx-auto max-w-3xl space-y-5">
          <Card title="Finance AI Companion" subtitle="Ask about budget headroom, pending approvals, at-risk projects, next quarter spend and recommendations.">
            <div className="flex gap-2">
              <Input
                placeholder="e.g. How much budget is remaining? What needs approval? Cost-saving recommendations"
                value={aiQuestion}
                onChange={(e) => setAiQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") askAi(); }}
              />
              <Button loading={busy} onClick={askAi}><Send className="h-3.5 w-3.5" /> Ask</Button>
            </div>
            {ai && (
              <div className="mt-4 rounded-xl border border-line bg-surface p-4">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-faint">{ai.intent}</p>
                <p className="whitespace-pre-line text-sm leading-relaxed text-ink">{ai.reply}</p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Budget detail modal */}
      <Modal
        open={selectedBudget !== null}
        onClose={() => setSelectedBudget(null)}
        title={selectedBudget?.name ?? "Budget"}
        description={selectedBudget ? `${selectedBudget.budget_type} · ${selectedBudget.status}` : undefined}
      >
        {selectedBudget && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs text-faint">Allocated</p>
                <p className="font-medium text-ink">{fmtMoney(selectedBudget.allocated_amount)}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Used</p>
                <p className="font-medium text-ink">{fmtMoney(selectedBudget.used_amount)}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Remaining</p>
                <p className="font-medium text-ink">{fmtMoney(selectedBudget.remaining_amount)}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Usage</p>
                <p className="font-medium text-ink">{selectedBudget.usage_pct}%</p>
              </div>
              <div>
                <p className="text-xs text-faint">Period</p>
                <p className="font-medium text-ink">{selectedBudget.period_start ?? "—"} → {selectedBudget.period_end ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Risk</p>
                <p className="font-medium text-ink"><Badge tone={riskLevelTone(selectedBudget.risk_level)}>{selectedBudget.risk_level}</Badge></p>
              </div>
            </div>
            {selectedBudget.description && <p className="text-sm text-muted">{selectedBudget.description}</p>}
            <div>
              <p className="label">Spend against this budget</p>
              <div className="mt-2 space-y-2">
                {expenses.filter((e) => e.budget_id === selectedBudget.id).slice(0, 6).map((e) => (
                  <div key={e.id} className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2 text-sm">
                    <span className="text-ink">{e.description}</span>
                    <span className="text-muted">{fmtMoney(e.amount)} · {e.status}</span>
                  </div>
                ))}
                {expenses.filter((e) => e.budget_id === selectedBudget.id).length === 0 && (
                  <p className="text-sm text-faint">No expenses linked yet.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Vendor detail modal */}
      <Modal
        open={selectedVendor !== null}
        onClose={() => setSelectedVendor(null)}
        title={selectedVendor?.name ?? "Vendor"}
        description={selectedVendor ? `${selectedVendor.kind} · ${selectedVendor.status}` : undefined}
        size="lg"
      >
        {selectedVendor && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs text-faint">Contact</p>
                <p className="font-medium text-ink">{selectedVendor.contact_name ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Email</p>
                <p className="font-medium text-ink">{selectedVendor.email ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Country</p>
                <p className="font-medium text-ink">{selectedVendor.country ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Payment terms</p>
                <p className="font-medium text-ink">{selectedVendor.payment_terms ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Risk score</p>
                <p className="font-medium text-ink">
                  {selectedVendor.risk ? (
                    <Badge tone={riskLevelTone(selectedVendor.risk.level)}>{selectedVendor.risk.level} · {selectedVendor.risk.score}</Badge>
                  ) : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-faint">Total spend</p>
                <p className="font-medium text-ink">{fmtMoney(selectedVendor.total_spend)}</p>
              </div>
            </div>

            <div>
              <p className="label">Contracts</p>
              <div className="mt-2 space-y-2">
                {(selectedVendor.contracts ?? []).slice(0, 6).map((c) => (
                  <div key={c.id} className="flex items-center justify-between rounded-lg border border-line bg-surface px-3 py-2 text-sm">
                    <span className="font-medium text-ink">{c.title}</span>
                    <span className="flex items-center gap-2 text-muted">
                      {fmtMoney(c.value)}
                      <Badge tone={statusTone(c.renewal_status)}>{c.renewal_status}</Badge>
                    </span>
                  </div>
                ))}
                {(selectedVendor.contracts ?? []).length === 0 && <p className="text-sm text-faint">No contracts.</p>}
              </div>
            </div>

            <div>
              <p className="label">Risk factors</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {Object.keys(selectedVendor.risk?.factors ?? {}).length === 0 && (
                  <Badge tone="success">No risk factors</Badge>
                )}
                {Object.entries(selectedVendor.risk?.factors ?? {}).map(([key, value]) => (
                  <Badge key={key} tone="warning">
                    {key}: {String((value as Record<string, unknown>).count ?? (value as Record<string, unknown>).level ?? "")}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Purchase request detail modal */}
      <Modal
        open={selectedRequest !== null}
        onClose={() => setSelectedRequest(null)}
        title={selectedRequest?.title ?? "Request"}
        description={selectedRequest ? `#${selectedRequest.id.slice(0, 8)} · ${selectedRequest.status}` : undefined}
      >
        {selectedRequest && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              <div>
                <p className="text-xs text-faint">Category</p>
                <p className="font-medium text-ink">{selectedRequest.category}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Quantity</p>
                <p className="font-medium text-ink">{selectedRequest.quantity}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Est. cost</p>
                <p className="font-medium text-ink">{fmtMoney(selectedRequest.estimated_cost)}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Requested by</p>
                <p className="font-medium text-ink">{selectedRequest.employee_name ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Vendor</p>
                <p className="font-medium text-ink">{selectedRequest.vendor_label ?? selectedRequest.vendor_name ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-faint">Budget</p>
                <p className="font-medium text-ink">{selectedRequest.budget_name ?? "—"}</p>
              </div>
            </div>
            {selectedRequest.description && <p className="text-sm text-muted">{selectedRequest.description}</p>}
            {Object.keys(selectedRequest.policy_flags ?? {}).filter((k) => k !== "flagged").length > 0 && (
              <div>
                <p className="label">Policy flags</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {Object.keys(selectedRequest.policy_flags).map((key) => key !== "flagged" && (
                    <Badge key={key} tone="warning">{key}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Purchase order detail modal */}
      <Modal
        open={selectedOrder !== null}
        onClose={() => setSelectedOrder(null)}
        title={selectedOrder ? `${selectedOrder.po_number} — ${selectedOrder.title}` : "Order"}
        description={selectedOrder ? selectedOrder.status : undefined}
      >
        {selectedOrder && (
          <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
            <div>
              <p className="text-xs text-faint">Vendor</p>
              <p className="font-medium text-ink">{selectedOrder.vendor_name ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-faint">Total</p>
              <p className="font-medium text-ink">{fmtMoney(selectedOrder.total_amount)}</p>
            </div>
            <div>
              <p className="text-xs text-faint">Expected delivery</p>
              <p className="font-medium text-ink">{selectedOrder.expected_delivery_at ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-faint">Issued</p>
              <p className="font-medium text-ink">{selectedOrder.issued_at ? selectedOrder.issued_at.slice(0, 10) : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-faint">External reference</p>
              <p className="font-medium text-ink">{selectedOrder.external_reference ?? "—"}</p>
            </div>
          </div>
        )}
      </Modal>

      {/* Create modals */}
      <Modal open={showBudget} onClose={() => setShowBudget(false)} title="New budget" description="Allocate a budget for a department, project, team or the company">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name *" className="col-span-2" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label="Type" value={form.budget_type ?? "department"} onChange={(e) => setForm({ ...form, budget_type: e.target.value })} options={BUDGET_TYPES} />
          <Input label="Allocated amount *" type="number" value={form.allocated_amount ?? ""} onChange={(e) => setForm({ ...form, allocated_amount: e.target.value })} />
          <Input label="Fiscal year" type="number" value={form.fiscal_year ?? "2026"} onChange={(e) => setForm({ ...form, fiscal_year: e.target.value })} />
          <Input label="Currency" value={form.currency ?? "USD"} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          <Input label="Period start" type="date" value={form.period_start ?? ""} onChange={(e) => setForm({ ...form, period_start: e.target.value })} />
          <Input label="Period end" type="date" value={form.period_end ?? ""} onChange={(e) => setForm({ ...form, period_end: e.target.value })} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowBudget(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateBudget}>Create budget</Button>
        </div>
      </Modal>

      <Modal open={showExpense} onClose={() => setShowExpense(false)} title="New expense" description="Submit an expense for approval and reimbursement">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Description *" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <Input label="Amount *" type="number" value={form.amount ?? ""} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          <Select label="Type" value={form.expense_type ?? "miscellaneous"} onChange={(e) => setForm({ ...form, expense_type: e.target.value })} options={EXPENSE_TYPES} />
          <Input label="Merchant" value={form.merchant ?? ""} onChange={(e) => setForm({ ...form, merchant: e.target.value })} />
          <Input label="Incurred on" type="date" value={form.incurred_at ?? ""} onChange={(e) => setForm({ ...form, incurred_at: e.target.value })} />
          <Select label="Budget" value={form.budget_id ?? ""} onChange={(e) => setForm({ ...form, budget_id: e.target.value })} options={budgetOptions} />
          <Input label="Receipt URL" value={form.receipt_url ?? ""} onChange={(e) => setForm({ ...form, receipt_url: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowExpense(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateExpense}>Submit expense</Button>
        </div>
      </Modal>

      <Modal open={showVendor} onClose={() => setShowVendor(false)} title="New vendor" description="Add a supplier, consultant, contractor or partner">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label="Kind" value={form.kind ?? "vendor"} onChange={(e) => setForm({ ...form, kind: e.target.value })}
            options={[
              { value: "supplier", label: "Supplier" },
              { value: "vendor", label: "Vendor" },
              { value: "consultant", label: "Consultant" },
              { value: "contractor", label: "Contractor" },
              { value: "partner", label: "Partner" },
            ]} />
          <Input label="Contact name" value={form.contact_name ?? ""} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} />
          <Input label="Email" value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <Input label="Phone" value={form.phone ?? ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <Input label="Website" value={form.website ?? ""} onChange={(e) => setForm({ ...form, website: e.target.value })} />
          <Input label="Country" value={form.country ?? ""} onChange={(e) => setForm({ ...form, country: e.target.value })} />
          <Input label="Payment terms" value={form.payment_terms ?? "net30"} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowVendor(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateVendor}>Create vendor</Button>
        </div>
      </Modal>

      <Modal open={showContract} onClose={() => setShowContract(false)} title="New vendor contract" description="Record contract terms and renewal tracking">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Title *" className="col-span-2" value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <Select label="Vendor" value={form.vendor_id ?? ""} onChange={(e) => setForm({ ...form, vendor_id: e.target.value })} options={vendorOptions} />
          <Input label="Value" type="number" value={form.value ?? ""} onChange={(e) => setForm({ ...form, value: e.target.value })} />
          <Input label="Currency" value={form.currency ?? "USD"} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          <Input label="Effective from" type="date" value={form.effective_from ?? ""} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
          <Input label="Expires at" type="date" value={form.expires_at ?? ""} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} />
          <Input label="Auto renew" value={form.auto_renew ?? "false"} onChange={(e) => setForm({ ...form, auto_renew: e.target.value })} />
          <Textarea label="Notes" className="col-span-2" value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowContract(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateContract}>Create contract</Button>
        </div>
      </Modal>

      <Modal open={showInvoice} onClose={() => setShowInvoice(false)} title="New invoice" description="Record a payable (vendor bill) or receivable (customer bill)">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Title *" className="col-span-2" value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <Select label="Direction" value={form.direction ?? "payable"} onChange={(e) => setForm({ ...form, direction: e.target.value })}
            options={[
              { value: "payable", label: "Payable (we owe)" },
              { value: "receivable", label: "Receivable (customer owes)" },
            ]} />
          <Select label="Vendor" value={form.vendor_id ?? ""} onChange={(e) => setForm({ ...form, vendor_id: e.target.value })} options={vendorOptions} />
          <Input label="Amount *" type="number" value={form.amount ?? ""} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          <Input label="Tax amount" type="number" value={form.tax_amount ?? "0"} onChange={(e) => setForm({ ...form, tax_amount: e.target.value })} />
          <Input label="Invoice number" value={form.invoice_number ?? ""} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} />
          <Input label="Currency" value={form.currency ?? "USD"} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          <Input label="Issued on" type="date" value={form.issued_at ?? ""} onChange={(e) => setForm({ ...form, issued_at: e.target.value })} />
          <Input label="Due on" type="date" value={form.due_at ?? ""} onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowInvoice(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateInvoice}>Create invoice</Button>
        </div>
      </Modal>

      <Modal open={showRequest} onClose={() => setShowRequest(false)} title="New purchase request" description="Requests flow through manager then finance approval">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Title *" className="col-span-2" value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <Select label="Category" value={form.category ?? "other"} onChange={(e) => setForm({ ...form, category: e.target.value })} options={REQUEST_CATEGORIES} />
          <Input label="Estimated cost" type="number" value={form.estimated_cost ?? ""} onChange={(e) => setForm({ ...form, estimated_cost: e.target.value })} />
          <Input label="Quantity" type="number" value={form.quantity ?? "1"} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
          <Select label="Budget" value={form.budget_id ?? ""} onChange={(e) => setForm({ ...form, budget_id: e.target.value })} options={budgetOptions} />
          <Input label="Vendor name" value={form.vendor_name ?? ""} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })} />
          <Input label="Currency" value={form.currency ?? "USD"} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowRequest(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateRequest}>Submit request</Button>
        </div>
      </Modal>

      {canManage && (
        <Modal open={showIntegration} onClose={() => setShowIntegration(false)} title="Connect ERP" description="Link a finance platform to sync expenses, invoices and purchase orders">
          <div className="grid grid-cols-2 gap-3">
            <Select label="Platform *" value={form.platform ?? "QuickBooks"} onChange={(e) => setForm({ ...form, platform: e.target.value })}
              options={["SAP", "Oracle", "NetSuite", "Dynamics 365", "QuickBooks", "Xero", "Tally", "Zoho Books"].map((p) => ({ value: p, label: p }))} />
            <Input label="Display name" value={form.display_name ?? ""} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowIntegration(false)}>Cancel</Button>
            <Button loading={busy} onClick={onCreateIntegration}>Connect</Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
