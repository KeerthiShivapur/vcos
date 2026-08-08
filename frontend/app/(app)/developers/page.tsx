"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import {
  ArrowLeftRight,
  Banknote,
  Bot,
  Boxes,
  CheckCircle2,
  Copy,
  KeyRound,
  Package,
  Palette,
  Plus,
  Send,
  ShieldCheck,
  Store,
  Trash2,
  Webhook,
} from "lucide-react";
import { useSearchParams } from "next/navigation";

import { Badge, statusTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader, StatCard } from "@/components/ui/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { useAuth } from "@/hooks/useAuth";
import { PERMISSIONS, roleCan } from "@/lib/permissions";
import {
  activateTheme,
  addListingReview,
  attemptCertification,
  changeDeveloperPlan,
  createAgent,
  createDeveloperApiKey,
  createApplication,
  createTheme,
  createWebhook,
  deleteTheme,
  deleteWebhook,
  executeAgent,
  getDeveloperAnalytics,
  getDeveloperMe,
  installExtension,
  listAgents,
  listInstalledExtensions,
  listListings,
  listMyApplications,
  listMyCertifications,
  listThemes,
  listWebhookDeliveries,
  listWebhooks,
  publishApplication,
  publishListing,
  registerDeveloper,
  revokeDeveloperApiKey,
  setAgentStatus,
  setWebhookStatus,
  uninstallExtension,
  updateTheme,
  type AIAgent,
  type DeveloperApiKey,
  type DeveloperApplication,
  type DeveloperCertification,
  type DeveloperProfile,
  type DeveloperSubscription,
  type DeveloperUsageSummary,
  type ExtensionInstall,
  type MarketplaceListing,
  type MarketplaceReview,
  type Theme,
  type WebhookDelivery,
  type WebhookEndpoint,
} from "@/lib/api";
import { classNames } from "@/lib/utils";

type TabId = "overview" | "apps" | "agents" | "marketplace" | "webhooks" | "themes" | "billing";

const TABS: { id: TabId; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "overview", label: "Overview", icon: Boxes },
  { id: "apps", label: "Applications", icon: Package },
  { id: "agents", label: "AI Agents", icon: Bot },
  { id: "marketplace", label: "Marketplace", icon: Store },
  { id: "webhooks", label: "Webhooks", icon: ArrowLeftRight },
  { id: "themes", label: "Themes", icon: Palette },
  { id: "billing", label: "Billing", icon: Banknote },
];

const EVENT_CHOICES = [
  "twin.updated",
  "digital_twin.updated",
  "memory.recorded",
  "project.created",
  "project.updated",
  "task.completed",
  "document.uploaded",
  "decision.analyzed",
  "usage.recorded",
  "subscription.changed",
];

export default function DevelopersPage() {
  return (
    <Suspense fallback={null}>
      <DevelopersContent />
    </Suspense>
  );
}

function DevelopersContent() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const canManage = user ? roleCan(user.role, PERMISSIONS.DEVELOPERS_MANAGE) : false;
  const canAgents = user ? roleCan(user.role, PERMISSIONS.AGENTS_MANAGE) : false;
  const canInstall = user ? roleCan(user.role, PERMISSIONS.MARKETPLACE_INSTALL) : false;
  const canThemes = user ? roleCan(user.role, PERMISSIONS.THEME_MANAGE) : false;
  const initial = (searchParams.get("tab") as TabId) || "overview";
  const [active, setActive] = useState<TabId>(TABS.some((t) => t.id === initial) ? initial : "overview");

  const [me, setMe] = useState<{ profile: DeveloperProfile; subscription: DeveloperSubscription } | null>(null);
  const [analytics, setAnalytics] = useState<DeveloperUsageSummary | null>(null);
  const [apps, setApps] = useState<DeveloperApplication[]>([]);
  const [keys, setKeys] = useState<Record<string, DeveloperApiKey[]>>({});
  const [agents, setAgents] = useState<AIAgent[]>([]);
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [installed, setInstalled] = useState<ExtensionInstall[]>([]);
  const [reviews, setReviews] = useState<Record<string, MarketplaceReview[]>>({});
  const [webhooks, setWebhooks] = useState<WebhookEndpoint[]>([]);
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDelivery[]>>({});
  const [themes, setThemes] = useState<Theme[]>([]);
  const [certs, setCerts] = useState<DeveloperCertification[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // create forms
  const [regForm, setRegForm] = useState({ name: "", email: "", bio: "", website: "" });
  const [appForm, setAppForm] = useState({ name: "", app_type: "app", description: "" });
  const [keyName, setKeyName] = useState("");
  const [agentForm, setAgentForm] = useState({ name: "", role: "assistant", description: "" });
  const [agentInput, setAgentInput] = useState<Record<string, string>>({});
  const [agentResult, setAgentResult] = useState<Record<string, string>>({});
  const [hookForm, setHookForm] = useState({ name: "", url: "", events: "twin.updated" });
  const [themeForm, setThemeForm] = useState({ name: "", primary: "#4f46e5" });
  const [reviewForm, setReviewForm] = useState<Record<string, { rating: number; comment: string }>>({});
  const [examForm, setExamForm] = useState({ exam: "", score: 80 });
  const [planForm, setPlanForm] = useState("pro");

  const loadMe = useCallback(async () => {
    try {
      const [meRes, analyticsRes, certsRes] = await Promise.all([
        getDeveloperMe().catch(() => null),
        getDeveloperAnalytics(30).catch(() => null),
        listMyCertifications().catch(() => ({ total: 0, certifications: [] as DeveloperCertification[] })),
      ]);
      if (meRes) setMe(meRes);
      if (analyticsRes) setAnalytics(analyticsRes);
      setCerts(certsRes.certifications);
    } catch (error) {
      console.error("developer load failed", error);
    }
  }, []);

  const loadWorkspace = useCallback(async () => {
    setBusy(true);
    try {
      const [appsRes, agentsRes, listingsRes, installedRes, hooksRes, themesRes] = await Promise.all([
        listMyApplications().catch(() => ({ total: 0, applications: [] as DeveloperApplication[] })),
        listAgents().catch(() => ({ total: 0, agents: [] as AIAgent[] })),
        listListings().catch(() => ({ total: 0, listings: [] as MarketplaceListing[] })),
        listInstalledExtensions().catch(() => ({ total: 0, installed: [] as ExtensionInstall[] })),
        listWebhooks().catch(() => ({ total: 0, endpoints: [] as WebhookEndpoint[] })),
        listThemes().catch(() => ({ total: 0, themes: [] as Theme[] })),
      ]);
      setApps(appsRes.applications);
      setAgents(agentsRes.agents);
      setListings(listingsRes.listings);
      setInstalled(installedRes.installed);
      setWebhooks(hooksRes.endpoints);
      setThemes(themesRes.themes);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
    void loadWorkspace();
  }, [loadMe, loadWorkspace]);

  const flash = (text: string) => {
    setMessage(text);
    window.setTimeout(() => setMessage(null), 4000);
  };

  const doRegister = async () => {
    if (!regForm.name.trim() || !regForm.email.trim()) return;
    const profile = await registerDeveloper({
      name: regForm.name,
      email: regForm.email,
      bio: regForm.bio || undefined,
      website: regForm.website || undefined,
    });
    setMe({ profile, subscription: me?.subscription ?? (await getDeveloperMe()).subscription });
    flash("Developer profile created");
  };

  const doCreateApp = async () => {
    if (!appForm.name.trim()) return;
    const app = await createApplication({
      name: appForm.name,
      app_type: appForm.app_type,
      description: appForm.description || undefined,
    });
    setApps((prev) => [app, ...prev]);
    setAppForm({ name: "", app_type: "app", description: "" });
    flash("Application created");
  };

  const doCreateKey = async (applicationId: string) => {
    if (!keyName.trim()) return;
    const key = await createDeveloperApiKey(applicationId, { name: keyName, scopes: [], rate_limit_per_minute: 60 });
    setKeys((prev) => ({ ...prev, [applicationId]: [key, ...(prev[applicationId] ?? [])] }));
    setCopiedKey(key.api_key ?? null);
    setKeyName("");
  };

  const doRevokeKey = async (applicationId: string, keyId: string) => {
    await revokeDeveloperApiKey(keyId);
    setKeys((prev) => ({ ...prev, [applicationId]: (prev[applicationId] ?? []).filter((k) => k.id !== keyId) }));
  };

  const doCreateAgent = async () => {
    if (!agentForm.name.trim()) return;
    const agent = await createAgent({
      name: agentForm.name,
      role: agentForm.role,
      description: agentForm.description || undefined,
      capabilities: ["search", "summarize"],
    });
    setAgents((prev) => [agent, ...prev]);
    setAgentForm({ name: "", role: "assistant", description: "" });
    flash("Agent created");
  };

  const doExecuteAgent = async (id: string) => {
    const inputText = agentInput[id] ?? "";
    if (!inputText.trim()) return;
    const result = await executeAgent(id, inputText);
    setAgentResult((prev) => ({ ...prev, [id]: String(result.response ?? JSON.stringify(result)) }));
  };

  const doToggleAgent = async (agent: AIAgent) => {
    const next = await setAgentStatus(agent.id, agent.status === "active" ? "disabled" : "active");
    setAgents((prev) => prev.map((a) => (a.id === agent.id ? next : a)));
  };

  const doInstall = async (listing: MarketplaceListing) => {
    const install = await installExtension(listing.id);
    setInstalled((prev) => [install, ...prev]);
    flash(`Installed ${listing.name}`);
  };

  const doUninstall = async (itemId: string) => {
    await uninstallExtension(itemId);
    setInstalled((prev) => prev.filter((i) => i.marketplace_item_id !== itemId));
  };

  const doReview = async (itemId: string) => {
    const form = reviewForm[itemId] ?? { rating: 5, comment: "" };
    await addListingReview(itemId, form.rating, form.comment || undefined);
    const rows = await import("@/lib/api").then((m) => m.listingReviews(itemId));
    setReviews((prev) => ({ ...prev, [itemId]: rows.reviews }));
    setReviewForm((prev) => ({ ...prev, [itemId]: { rating: 5, comment: "" } }));
    flash("Review submitted");
  };

  const doPublishListing = async (app: DeveloperApplication) => {
    await publishListing({ application_id: app.id, name: app.name, price: 0, category: app.app_type, description: app.description });
    flash("Listing published");
    void loadWorkspace();
  };

  const doCreateWebhook = async () => {
    if (!hookForm.name.trim() || !hookForm.url.trim()) return;
    const hook = await createWebhook({
      name: hookForm.name,
      url: hookForm.url,
      events: [hookForm.events],
    });
    setWebhooks((prev) => [hook, ...prev]);
    setHookForm({ name: "", url: "", events: "twin.updated" });
    flash("Webhook created");
  };

  const doToggleWebhook = async (hook: WebhookEndpoint) => {
    const next = await setWebhookStatus(hook.id, hook.status === "active" ? "paused" : "active");
    setWebhooks((prev) => prev.map((h) => (h.id === hook.id ? next : h)));
  };

  const doDeleteWebhook = async (hook: WebhookEndpoint) => {
    await deleteWebhook(hook.id);
    setWebhooks((prev) => prev.filter((h) => h.id !== hook.id));
  };

  const loadDeliveries = async (endpointId: string) => {
    const res = await listWebhookDeliveries(endpointId);
    setDeliveries((prev) => ({ ...prev, [endpointId]: res.deliveries }));
  };

  const doCreateTheme = async () => {
    if (!themeForm.name.trim()) return;
    const theme = await createTheme({
      name: themeForm.name,
      config: { primary: themeForm.primary },
    });
    setThemes((prev) => [theme, ...prev]);
    setThemeForm({ name: "", primary: "#4f46e5" });
    flash("Theme created");
  };

  const doActivateTheme = async (id: string) => {
    const theme = await activateTheme(id);
    setThemes((prev) => prev.map((t) => ({ ...t, active: t.id === id })));
    void theme;
    flash("Theme activated");
  };

  const doDeleteTheme = async (id: string) => {
    await deleteTheme(id);
    setThemes((prev) => prev.filter((t) => t.id !== id));
  };

  const doUpdateTheme = async (id: string) => {
    const theme = await updateTheme(id, { config: { primary: themeForm.primary } });
    setThemes((prev) => prev.map((t) => (t.id === id ? theme : t)));
    flash("Theme updated");
  };

  const doCertify = async () => {
    if (!examForm.exam.trim()) return;
    const cert = await attemptCertification(examForm.exam, examForm.score);
    setCerts((prev) => [cert, ...prev]);
    flash(`Certification issued (${cert.status})`);
  };

  const doChangePlan = async () => {
    const sub = await changeDeveloperPlan(planForm);
    setMe((prev) => (prev ? { ...prev, subscription: sub } : prev));
    flash(`Plan changed to ${sub.plan}`);
  };

  const totals = analytics?.totals;
  const installedIds = new Set(installed.map((i) => i.marketplace_item_id));

  return (
    <div>
      <PageHeader
        breadcrumb="Phase 18 · Developer Ecosystem"
        title="Developer Portal"
        description="Build applications, AI agents and extensions on the VCOS platform."
        actions={
          canManage ? (
            <Button onClick={loadWorkspace} disabled={busy} variant="primary" >
              Refresh
            </Button>
          ) : undefined
        }
      />

      {message && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
          <CheckCircle2 className="h-4 w-4" />
          {message}
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Applications" value={apps.length} icon={Package} />
        <StatCard label="AI Agents" value={agents.length} icon={Bot} />
        <StatCard label="Webhook endpoints" value={webhooks.length} icon={ArrowLeftRight} />
        <StatCard label="Requests (30d)" value={Math.round(totals?.requests ?? 0)} icon={KeyRound} />
      </div>

      <Tabs tabs={TABS} active={active} onChange={(id) => setActive(id as TabId)} />

      <div className="mt-6 space-y-6">
        {active === "overview" && (
          <>
            {!me && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">Register as a developer</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  <input value={regForm.name} onChange={(e) => setRegForm({ ...regForm, name: e.target.value })} placeholder="Full name" className="input" />
                  <input value={regForm.email} onChange={(e) => setRegForm({ ...regForm, email: e.target.value })} placeholder="Email" className="input" />
                  <input value={regForm.website} onChange={(e) => setRegForm({ ...regForm, website: e.target.value })} placeholder="Website (optional)" className="input" />
                  <input value={regForm.bio} onChange={(e) => setRegForm({ ...regForm, bio: e.target.value })} placeholder="Short bio (optional)" className="input" />
                </div>
                <Button className="mt-3" onClick={doRegister} >Register</Button>
              </Card>
            )}

            {me && (
              <>
                <div className="grid gap-3 lg:grid-cols-3">
                  <Card>
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-ink">Profile</h3>
                      <Badge tone={me.profile.verified ? "success" : "warning"}>{me.profile.verified ? "Verified" : "Unverified"}</Badge>
                    </div>
                    <p className="text-base font-medium text-ink">{me.profile.name}</p>
                    <p className="text-sm text-muted">{me.profile.email}</p>
                    {me.profile.website && <p className="text-sm text-muted">{me.profile.website}</p>}
                    {me.profile.bio && <p className="mt-2 text-sm text-muted">{me.profile.bio}</p>}
                    <div className="mt-3 rounded-lg bg-surface p-2 font-mono text-xs text-faint">key: {me.profile.developer_key}</div>
                  </Card>
                  <Card>
                    <div className="mb-2 flex items-center justify-between">
                      <h3 className="text-sm font-semibold text-ink">Subscription</h3>
                      <Badge tone={statusTone(me.subscription.status)}>{me.subscription.status}</Badge>
                    </div>
                    <p className="text-2xl font-semibold capitalize text-ink">{me.subscription.plan}</p>
                    <p className="text-sm text-muted">
                      {me.subscription.monthly_quota ?? 0} requests/mo · {Math.round(me.subscription.revenue_share * 100)}% revenue share
                    </p>
                    <p className="mt-1 text-xs text-faint">
                      Period {me.subscription.current_period_start ?? "—"} → {me.subscription.current_period_end ?? "—"}
                    </p>
                  </Card>
                  <Card>
                    <h3 className="mb-2 text-sm font-semibold text-ink">Usage (30 days)</h3>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between"><span className="text-muted">Requests</span><span className="font-medium text-ink">{Math.round(totals?.requests ?? 0)}</span></div>
                      <div className="flex justify-between"><span className="text-muted">Errors</span><span className="font-medium text-ink">{Math.round(totals?.errors ?? 0)}</span></div>
                      <div className="flex justify-between"><span className="text-muted">Latency (ms)</span><span className="font-medium text-ink">{Math.round(totals?.latency_ms ?? 0)}</span></div>
                      <div className="flex justify-between"><span className="text-muted">Installs</span><span className="font-medium text-ink">{Math.round(totals?.installs ?? 0)}</span></div>
                    </div>
                  </Card>
                </div>

                <Card>
                  <h3 className="mb-3 text-sm font-semibold text-ink">Certifications</h3>
                  {certs.length === 0 ? (
                    <EmptyState title="No certifications yet" />
                  ) : (
                    <div className="space-y-2">
                      {certs.map((c) => (
                        <div key={c.id} className="flex items-center justify-between rounded-lg border border-line p-3 text-sm">
                          <div>
                            <p className="font-medium text-ink">{c.exam}</p>
                            <p className="text-xs text-faint">{c.badge} · score {c.score}</p>
                          </div>
                          <Badge tone={statusTone(c.status)}>{c.status}</Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              </>
            )}
          </>
        )}

        {active === "apps" && (
          <>
            {me && canManage && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">New application</h3>
                <div className="grid gap-3 md:grid-cols-3">
                  <input value={appForm.name} onChange={(e) => setAppForm({ ...appForm, name: e.target.value })} placeholder="Application name" className="input" />
                  <select value={appForm.app_type} onChange={(e) => setAppForm({ ...appForm, app_type: e.target.value })} className="input">
                    <option value="app">App</option>
                    <option value="integration">Integration</option>
                    <option value="agent">Agent</option>
                  </select>
                  <input value={appForm.description} onChange={(e) => setAppForm({ ...appForm, description: e.target.value })} placeholder="Description (optional)" className="input" />
                </div>
                <Button className="mt-3" onClick={doCreateApp} >Create application</Button>
              </Card>
            )}

            {apps.map((app) => {
              const appKeys = keys[app.id] ?? [];
              return (
                <Card key={app.id}>
                  <div className="mb-2 flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-ink">{app.name}</h3>
                        <Badge tone={app.verified ? "success" : "neutral"}>{app.verified ? "Verified" : "Pending"}</Badge>
                        <Badge tone={statusTone(app.status)}>{app.status}</Badge>
                      </div>
                      <p className="text-xs text-faint">{app.application_key} · v{app.version} · {app.app_type}</p>
                      {app.description && <p className="mt-1 text-sm text-muted">{app.description}</p>}
                    </div>
                    <div className="flex shrink-0 gap-2">
                      {app.status === "draft" && canManage && (
                        <Button size="sm" onClick={() => publishApplication(app.id)}>Publish</Button>
                      )}
                      {app.status === "published" && canManage && (
                        <Button size="sm" variant="secondary" onClick={() => doPublishListing(app)}>List on marketplace</Button>
                      )}
                    </div>
                  </div>

                  {appKeys.length > 0 && (
                    <div className="mb-3 space-y-1">
                      {appKeys.map((key) => (
                        <div key={key.id} className="flex items-center justify-between rounded-lg bg-surface px-3 py-2 text-xs">
                          <div className="flex items-center gap-2">
                            <KeyRound className="h-3 w-3 text-faint" />
                            <span className="font-medium text-ink">{key.name}</span>
                            <span className="font-mono text-faint">{key.key_prefix}…</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge tone={statusTone(key.status)}>{key.status}</Badge>
                            {canManage && key.status === "active" && (
                              <button className="text-faint hover:text-danger" onClick={() => doRevokeKey(app.id, key.id)}>
                                <Trash2 className="h-3 w-3" />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {copiedKey && (
                    <div className="mb-3 flex items-center justify-between rounded-lg border border-brand/40 bg-brand-soft px-3 py-2 text-xs text-brand">
                      <span className="font-mono break-all">New API key: {copiedKey}</span>
                      <button
                        onClick={() => {
                          void navigator.clipboard.writeText(copiedKey ?? "");
                          flash("Key copied");
                        }}
                      >
                        <Copy className="h-3 w-3" />
                      </button>
                    </div>
                  )}

                  {canManage && (
                    <div className="flex gap-2">
                      <input value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="Key name" className="input max-w-[200px]" />
                      <Button size="sm" variant="secondary" onClick={() => doCreateKey(app.id)} >Create API key</Button>
                    </div>
                  )}
                </Card>
              );
            })}

            {apps.length === 0 && <EmptyState title="No applications" description={me ? "Create your first application to get API keys." : "Register as a developer first."} />}
          </>
        )}

        {active === "agents" && (
          <>
            {canAgents && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">New agent</h3>
                <div className="grid gap-3 md:grid-cols-3">
                  <input value={agentForm.name} onChange={(e) => setAgentForm({ ...agentForm, name: e.target.value })} placeholder="Agent name" className="input" />
                  <select value={agentForm.role} onChange={(e) => setAgentForm({ ...agentForm, role: e.target.value })} className="input">
                    <option value="assistant">Assistant</option>
                    <option value="analyst">Analyst</option>
                    <option value="automation">Automation</option>
                  </select>
                  <input value={agentForm.description} onChange={(e) => setAgentForm({ ...agentForm, description: e.target.value })} placeholder="Description (optional)" className="input" />
                </div>
                <Button className="mt-3" onClick={doCreateAgent} >Create agent</Button>
              </Card>
            )}

            {agents.map((agent) => (
              <Card key={agent.id}>
                <div className="mb-2 flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-ink">{agent.name}</h3>
                      <Badge tone={agent.verified ? "success" : "neutral"}>{agent.verified ? "Verified" : "Unverified"}</Badge>
                      <Badge tone={statusTone(agent.status)}>{agent.status}</Badge>
                    </div>
                    <p className="text-xs text-faint">{agent.role} · {agent.agent_key} · v{agent.version}</p>
                    {agent.description && <p className="mt-1 text-sm text-muted">{agent.description}</p>}
                    {agent.capabilities && agent.capabilities.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {agent.capabilities.map((c) => (
                          <Badge key={c} tone="neutral">{c}</Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  {canAgents && (
                    <Button size="sm" variant="secondary" onClick={() => doToggleAgent(agent)}>
                      {agent.status === "active" ? "Disable" : "Enable"}
                    </Button>
                  )}
                </div>
                {agent.status === "active" && (
                  <div className="mt-3 space-y-2">
                    <div className="flex gap-2">
                      <input
                        value={agentInput[agent.id] ?? ""}
                        onChange={(e) => setAgentInput((prev) => ({ ...prev, [agent.id]: e.target.value }))}
                        placeholder={`Ask ${agent.name}…`}
                        className="input flex-1"
                      />
                      <Button size="sm" onClick={() => doExecuteAgent(agent.id)} >Run</Button>
                    </div>
                    {agentResult[agent.id] && (
                      <div className="rounded-lg bg-surface p-3 text-sm text-muted">{agentResult[agent.id]}</div>
                    )}
                  </div>
                )}
              </Card>
            ))}

            {agents.length === 0 && <EmptyState title="No agents" description="Create your first AI agent." />}
          </>
        )}

        {active === "marketplace" && (
          <>
            <div className="grid gap-3 lg:grid-cols-2">
              {listings.map((listing) => (
                <Card key={listing.id}>
                  <div className="mb-2 flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-ink">{listing.name}</h3>
                        {listing.verified && <Badge tone="success">Verified</Badge>}
                      </div>
                      <p className="text-xs text-faint">{listing.category} · v{listing.version} · {listing.plugin_key}</p>
                    </div>
                    <Badge tone={listing.published ? "success" : "neutral"}>{listing.published ? "Published" : "Draft"}</Badge>
                  </div>
                  {listing.description && <p className="text-sm text-muted">{listing.description}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-faint">
                    <span>★ {listing.rating.toFixed(1)} ({listing.review_count})</span>
                    <span>{listing.downloads} installs</span>
                    <span>{listing.price > 0 ? `$${listing.price}` : "Free"}</span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    {canInstall && !installedIds.has(listing.id) && (
                      <Button size="sm" onClick={() => doInstall(listing)}>Install</Button>
                    )}
                    {installedIds.has(listing.id) && (
                      <Button size="sm" variant="secondary" onClick={() => doUninstall(listing.id)}>Uninstall</Button>
                    )}
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        void import("@/lib/api").then((m) => m.listingReviews(listing.id)).then((rows) =>
                          setReviews((prev) => ({ ...prev, [listing.id]: rows.reviews }))
                        );
                      }}
                    >
                      Reviews ({listing.review_count})
                    </Button>
                  </div>
                  {(reviews[listing.id] ?? []).length > 0 && (
                    <div className="mt-3 space-y-2 border-t border-line pt-3">
                      {(reviews[listing.id] ?? []).map((r) => (
                        <div key={r.id} className="text-sm">
                          <span className="font-medium text-ink">★ {r.rating}</span>
                          <span className="text-xs text-faint"> · {new Date(r.created_at ?? "").toLocaleDateString()}</span>
                          {r.comment && <p className="text-muted">{r.comment}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex gap-2 border-t border-line pt-3">
                    <input
                      value={reviewForm[listing.id]?.comment ?? ""}
                      onChange={(e) =>
                        setReviewForm((prev) => ({
                          ...prev,
                          [listing.id]: { rating: prev[listing.id]?.rating ?? 5, comment: e.target.value },
                        }))
                      }
                      placeholder="Add a review…"
                      className="input flex-1"
                    />
                    <select
                      value={reviewForm[listing.id]?.rating ?? 5}
                      onChange={(e) =>
                        setReviewForm((prev) => ({
                          ...prev,
                          [listing.id]: { rating: Number(e.target.value), comment: prev[listing.id]?.comment ?? "" },
                        }))
                      }
                      className="input w-20"
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>{n}★</option>
                      ))}
                    </select>
                    <Button size="sm" variant="secondary" onClick={() => doReview(listing.id)}>Post</Button>
                  </div>
                </Card>
              ))}
            </div>
            {listings.length === 0 && <EmptyState title="Marketplace is empty" description="Publish an application to seed the marketplace." />}
          </>
        )}

        {active === "webhooks" && (
          <>
            {canManage && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">New webhook endpoint</h3>
                <div className="grid gap-3 md:grid-cols-3">
                  <input value={hookForm.name} onChange={(e) => setHookForm({ ...hookForm, name: e.target.value })} placeholder="Endpoint name" className="input" />
                  <input value={hookForm.url} onChange={(e) => setHookForm({ ...hookForm, url: e.target.value })} placeholder="https://example.com/hook" className="input" />
                  <select value={hookForm.events} onChange={(e) => setHookForm({ ...hookForm, events: e.target.value })} className="input">
                    {EVENT_CHOICES.map((ev) => (
                      <option key={ev} value={ev}>{ev}</option>
                    ))}
                  </select>
                </div>
                <Button className="mt-3" onClick={doCreateWebhook} >Create webhook</Button>
              </Card>
            )}

            {webhooks.map((hook) => (
              <Card key={hook.id}>
                <div className="mb-2 flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-ink">{hook.name}</h3>
                      <Badge tone={statusTone(hook.status)}>{hook.status}</Badge>
                    </div>
                    <p className="text-xs font-mono text-faint">{hook.url}</p>
                    <p className="text-xs text-faint">
                      {hook.events?.join(", ")} · {hook.success_count} ok / {hook.failure_count} failed
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button size="sm" variant="secondary" onClick={() => loadDeliveries(hook.id)}>Deliveries</Button>
                    {canManage && (
                      <>
                        <Button size="sm" variant="secondary" onClick={() => doToggleWebhook(hook)}>
                          {hook.status === "active" ? "Pause" : "Resume"}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => doDeleteWebhook(hook)}><Trash2 className="h-4 w-4" /></Button>
                      </>
                    )}
                  </div>
                </div>
                {(deliveries[hook.id] ?? []).length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-line pt-3">
                    {(deliveries[hook.id] ?? []).slice(0, 5).map((d) => (
                      <div key={d.id} className="flex items-center justify-between rounded-lg bg-surface px-3 py-2 text-xs">
                        <span className="text-muted">{d.event_name}</span>
                        <span className="flex items-center gap-2">
                          <span className="text-faint">attempts {d.attempts}</span>
                          <Badge tone={statusTone(d.status)}>{d.status}</Badge>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            ))}

            {webhooks.length === 0 && <EmptyState title="No webhook endpoints" description="Receive real-time platform events at your URL." />}
          </>
        )}

        {active === "themes" && (
          <>
            {canThemes && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">New theme</h3>
                <div className="flex flex-wrap items-end gap-3">
                  <input value={themeForm.name} onChange={(e) => setThemeForm({ ...themeForm, name: e.target.value })} placeholder="Theme name" className="input max-w-[220px]" />
                  <label className="flex items-center gap-2 text-sm text-muted">
                    Primary
                    <input
                      type="color"
                      value={themeForm.primary}
                      onChange={(e) => setThemeForm({ ...themeForm, primary: e.target.value })}
                      className="h-9 w-14 cursor-pointer rounded border border-line bg-surface"
                    />
                  </label>
                  <Button onClick={doCreateTheme} >Create theme</Button>
                </div>
              </Card>
            )}

            {themes.map((theme) => (
              <Card key={theme.id}>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg border border-line" style={{ backgroundColor: String((theme.config as Record<string, unknown>)?.primary ?? "#4f46e5") }} />
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-ink">{theme.name}</h3>
                        {theme.active && <Badge tone="success">Active</Badge>}
                      </div>
                      <p className="text-xs text-faint">{theme.source} · {new Date(theme.created_at ?? "").toLocaleDateString()}</p>
                    </div>
                  </div>
                  {canThemes && !theme.active && (
                    <Button size="sm" onClick={() => doActivateTheme(theme.id)}>Activate</Button>
                  )}
                  {canThemes && theme.active && (
                    <div className="flex gap-2">
                      <Button size="sm" variant="secondary" onClick={() => doUpdateTheme(theme.id)}>Apply palette</Button>
                      <Button size="sm" variant="secondary" onClick={() => doDeleteTheme(theme.id)}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  )}
                </div>
              </Card>
            ))}

            {themes.length === 0 && <EmptyState title="No themes" description="Brand your workspace with custom themes." />}
          </>
        )}

        {active === "billing" && (
          <div className="grid gap-3 lg:grid-cols-2">
            {me && (
              <Card>
                <h3 className="mb-3 text-sm font-semibold text-ink">Change plan</h3>
                <div className="flex items-end gap-3">
                  <select value={planForm} onChange={(e) => setPlanForm(e.target.value)} className="input max-w-[200px]">
                    <option value="free">Free — 1,000 req/mo</option>
                    <option value="pro">Pro — 100,000 req/mo</option>
                    <option value="business">Business — 1M req/mo</option>
                  </select>
                  <Button onClick={doChangePlan}>Change plan</Button>
                </div>
                <p className="mt-3 text-xs text-faint">
                  Current: <span className="capitalize text-ink">{me.subscription.plan}</span> · quota {me.subscription.monthly_quota ?? 0} requests/month · revenue share {Math.round(me.subscription.revenue_share * 100)}%
                </p>
              </Card>
            )}

            <Card>
              <h3 className="mb-3 text-sm font-semibold text-ink">Take a certification</h3>
              <div className="flex flex-wrap items-end gap-3">
                <input value={examForm.exam} onChange={(e) => setExamForm({ ...examForm, exam: e.target.value })} placeholder="Exam name (e.g. VCOS Developer)" className="input max-w-[240px]" />
                <input type="number" value={examForm.score} min={0} max={100} onChange={(e) => setExamForm({ ...examForm, score: Number(e.target.value) })} className="input w-24" />
                <Button onClick={doCertify}>Attempt</Button>
              </div>
              <p className="mt-3 text-xs text-faint">Score ≥ 80 issues a certification credential; otherwise a study recommendation.</p>
            </Card>

            {analytics && (
              <Card className="lg:col-span-2">
                <h3 className="mb-3 text-sm font-semibold text-ink">Usage analytics</h3>
                <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <StatCard label="Requests" value={Math.round(totals?.requests ?? 0)} icon={KeyRound} />
                  <StatCard label="Errors" value={Math.round(totals?.errors ?? 0)} icon={Send} />
                  <StatCard label="Median latency" value={`${Math.round(totals?.latency_ms ?? 0)} ms`} icon={Webhook} />
                  <StatCard label="Installs" value={Math.round(totals?.installs ?? 0)} icon={Store} />
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line text-left text-xs text-faint">
                        <th className="pb-2 pr-4">Date</th>
                        <th className="pb-2 pr-4">Requests</th>
                        <th className="pb-2 pr-4">Errors</th>
                        <th className="pb-2">Latency (ms)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(analytics.by_day)
                        .sort(([a], [b]) => (a < b ? 1 : -1))
                        .slice(0, 14)
                        .map(([date, day]) => (
                          <tr key={date} className="border-b border-line last:border-0">
                            <td className="py-2 pr-4 text-muted">{date}</td>
                            <td className="py-2 pr-4 font-medium text-ink">{Math.round(day.requests ?? 0)}</td>
                            <td className="py-2 pr-4 font-medium text-ink">{Math.round(day.errors ?? 0)}</td>
                            <td className="py-2 font-medium text-ink">{Math.round(day.latency_ms ?? 0)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
