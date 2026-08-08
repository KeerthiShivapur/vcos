"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  ArrowLeftRight,
  BarChart3,
  Bot,
  Boxes,
  Building2,
  Fingerprint,
  Flag,
  KeyRound,
  LayoutDashboard,
  Lock,
  Package,
  Plus,
  RefreshCw,
  Rocket,
  ScrollText,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Store,
  ToggleLeft,
  UploadCloud,
  UserPlus,
} from "lucide-react";

import {
  aiMemorySettings,
  aiModels,
  aiUsage,
  changeLicensePlan,
  checkIp,
  complianceFrameworks,
  complianceReport,
  createApiKey,
  createAuthPolicy,
  createEnterpriseIntegration,
  createFeatureFlag,
  createIdentityProvider,
  deleteIdentityProvider,
  deleteFeatureFlag,
  deleteIntegration,
  detectFailedLogin,
  disablePlugin,
  enrollMfa,
  enablePlugin,
  enterpriseOverview,
  evaluateFeatureFlag,
  gatewayVersions,
  getAuthPolicy,
  getLicense,
  ingestLog,
  ingestMetric,
  installMarketplaceItem,
  installPlugin,
  licensePlans,
  listApiKeys,
  listComplianceRecords,
  listDevices,
  listEnterpriseIntegrations,
  listFeatureFlags,
  listIdentityBindings,
  listIdentityProviders,
  listMarketplaceItems,
  listMetrics,
  listPlugins,
  listSecurityEvents,
  monitoringAlerts,
  monitoringHealth,
  publishMarketplaceItem,
  queryLogs,
  recordSecurityEvent,
  refreshLicense,
  removePlugin,
  resolveSecurityEvent,
  revokeApiKey,
  rotateApiKey,
  scimCreateGroup,
  scimCreateUser,
  scimDeleteGroup,
  scimDeleteUser,
  scimListGroups,
  scimListUsers,
  scimUpdateUser,
  securityRules,
  setAiConsent,
  ssoInitiate,
  syncEnterpriseIntegration,
  testEnterpriseIntegration,
  trustDevice,
  updateComplianceRecord,
  updateFeatureFlag,
  updateIdentityProvider,
  updateMarketplaceItem,
  updatePlugin,
  upsertComplianceRecord,
  verifyMfa,
} from "@/lib/api";
import type {
  ApiKeyRow,
  AuthPolicy,
  ComplianceControl,
  EnterpriseOverview,
  FeatureFlag,
  GatewayVersionInfo,
  IdentityBinding,
  IdentityProvider,
  IntegrationConnection,
  MarketplaceItem,
  MonitoringAlert,
  MonitoringHealth,
  ObservabilityLog,
  OrganizationLicense,
  Plugin,
  ScimGroupResource,
  ScimUserResource,
  SecurityEvent,
  SecurityRules,
  SystemMetric,
  TrustedDevice,
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

export default function EnterprisePage() {
  return (
    <Suspense fallback={null}>
      <EnterpriseContent />
    </Suspense>
  );
}

const TABS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "identity", label: "Identity", icon: Fingerprint },
  { id: "plugins", label: "Plugins", icon: Boxes },
  { id: "marketplace", label: "Marketplace", icon: Store },
  { id: "gateway", label: "API Gateway", icon: KeyRound },
  { id: "integrations", label: "Integrations", icon: ArrowLeftRight },
  { id: "monitoring", label: "Monitoring", icon: Activity },
  { id: "observability", label: "Observability", icon: ScrollText },
  { id: "security", label: "Security", icon: ShieldCheck },
  { id: "compliance", label: "Compliance", icon: ShieldAlert },
  { id: "licensing", label: "Licensing", icon: Building2 },
  { id: "flags", label: "Feature Flags", icon: Flag },
  { id: "ai", label: "Governed AI", icon: Bot },
];

const PROVIDER_TYPES = ["saml", "oidc", "oauth2", "ldap"].map((v) => ({ value: v, label: v }));
const INTEGRATION_KINDS = ["webhook", "api", "datasource"].map((v) => ({ value: v, label: v }));
const SEVERITIES = ["low", "medium", "high", "critical"].map((v) => ({ value: v, label: v }));
const CONTROL_STATUSES = ["pass", "warn", "fail", "pending"].map((v) => ({ value: v, label: v }));
const PLANS = ["starter", "professional", "enterprise", "custom"].map((v) => ({ value: v, label: v }));

const severityTone = (level?: string | null) =>
  level === "critical" ? "danger" : level === "high" ? "danger" : level === "medium" ? "warning" : level === "low" ? "neutral" : "brand";

const checkTone = (status?: string | null) =>
  status === "healthy" || status === "active" || status === "pass" || status === "installed" || status === "resolved" || status === "enabled"
    ? "success"
    : status === "degraded" || status === "warn" || status === "error" || status === "disabled" || status === "open"
      ? "warning"
      : status === "critical" || status === "fail" || status === "revoked"
        ? "danger"
        : "brand";

function EnterpriseContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const canManage = roleCan(user?.role, PERMISSIONS.ENTERPRISE_MANAGE);
  const canIdentity = roleCan(user?.role, PERMISSIONS.IDENTITY_MANAGE);
  const canPlugins = roleCan(user?.role, PERMISSIONS.PLUGINS_MANAGE);
  const canMarketplace = roleCan(user?.role, PERMISSIONS.MARKETPLACE_MANAGE);
  const canApiKeys = roleCan(user?.role, PERMISSIONS.API_KEYS_MANAGE);
  const canIntegrations = roleCan(user?.role, PERMISSIONS.INTEGRATIONS_MANAGE);
  const canSecurity = roleCan(user?.role, PERMISSIONS.SECURITY_MANAGE);
  const canCompliance = roleCan(user?.role, PERMISSIONS.COMPLIANCE_MANAGE);
  const canLicenses = roleCan(user?.role, PERMISSIONS.LICENSES_MANAGE);
  const canFlags = roleCan(user?.role, PERMISSIONS.FEATURE_FLAGS_MANAGE);

  const tab = searchParams.get("tab") ?? "overview";
  const setTab = (id: string) => router.replace(`/enterprise?tab=${id}`);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [overview, setOverview] = useState<EnterpriseOverview | null>(null);
  const [providers, setProviders] = useState<IdentityProvider[]>([]);
  const [bindings, setBindings] = useState<IdentityBinding[]>([]);
  const [devices, setDevices] = useState<TrustedDevice[]>([]);
  const [policy, setPolicy] = useState<AuthPolicy | null>(null);
  const [scimUsers, setScimUsers] = useState<ScimUserResource[]>([]);
  const [scimGroups, setScimGroups] = useState<ScimGroupResource[]>([]);
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceItem[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKeyRow[]>([]);
  const [gateway, setGateway] = useState<GatewayVersionInfo | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationConnection[]>([]);
  const [health, setHealth] = useState<MonitoringHealth | null>(null);
  const [metrics, setMetrics] = useState<SystemMetric[]>([]);
  const [alerts, setAlerts] = useState<MonitoringAlert[]>([]);
  const [logs, setLogs] = useState<ObservabilityLog[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [rules, setRules] = useState<SecurityRules | null>(null);
  const [frameworks, setFrameworks] = useState<Record<string, string[]>>({});
  const [records, setRecords] = useState<ComplianceControl[]>([]);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [license, setLicense] = useState<OrganizationLicense | null>(null);
  const [planCatalog, setPlanCatalog] = useState<Record<string, unknown>>({});
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [aiModelsList, setAiModelsList] = useState<Record<string, unknown>[]>([]);
  const [aiUsageData, setAiUsageData] = useState<Record<string, unknown> | null>(null);
  const [aiMemory, setAiMemory] = useState<Record<string, unknown> | null>(null);

  const [mfa, setMfa] = useState<{ mfa_method: string; mfa_secret: string } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [ssoResult, setSsoResult] = useState<Record<string, unknown> | null>(null);
  const [secret, setSecret] = useState<{ label: string; value: string } | null>(null);

  const [showProvider, setShowProvider] = useState(false);
  const [showPolicy, setShowPolicy] = useState(false);
  const [showScimUser, setShowScimUser] = useState(false);
  const [showScimGroup, setShowScimGroup] = useState(false);
  const [showPlugin, setShowPlugin] = useState(false);
  const [showMarketplaceItem, setShowMarketplaceItem] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [showIntegration, setShowIntegration] = useState(false);
  const [showMetric, setShowMetric] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const [showSecurityEvent, setShowSecurityEvent] = useState(false);
  const [showComplianceRecord, setShowComplianceRecord] = useState(false);
  const [showFlag, setShowFlag] = useState(false);
  const [showAiConsent, setShowAiConsent] = useState(false);

  const [form, setForm] = useState<Record<string, string>>({});

  const loadAll = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    setError(null);
    try {
      const ok = <T,>(r: PromiseSettledResult<T>): T | null => (r.status === "fulfilled" ? r.value : null);
      const [ov, prov, bind, dev, pol, su, sg, pl, mp, ak, gv, it, mh, mm, ma, lg, se, ru, fw, rc, rp, lc, pc, fl, mod, use, mem] =
        await Promise.allSettled([
          enterpriseOverview(),
          listIdentityProviders(),
          listIdentityBindings(),
          listDevices(),
          getAuthPolicy(),
          scimListUsers(),
          scimListGroups(),
          listPlugins(),
          listMarketplaceItems(),
          listApiKeys(),
          gatewayVersions(),
          listEnterpriseIntegrations(),
          monitoringHealth(),
          listMetrics(undefined, 50),
          monitoringAlerts(),
          queryLogs(undefined, undefined, undefined, 50),
          listSecurityEvents(),
          securityRules(),
          complianceFrameworks(),
          listComplianceRecords(),
          complianceReport(),
          getLicense(),
          licensePlans(),
          listFeatureFlags(),
          aiModels(),
          aiUsage(),
          aiMemorySettings(),
        ]);
      setOverview(ok(ov));
      setProviders(ok(prov) ?? []);
      setBindings(ok(bind) ?? []);
      setDevices(ok(dev) ?? []);
      setPolicy(ok(pol)?.policy ?? null);
      setScimUsers(ok(su)?.Resources ?? []);
      setScimGroups(ok(sg)?.Resources ?? []);
      setPlugins(ok(pl) ?? []);
      setMarketplace(ok(mp) ?? []);
      setApiKeys(ok(ak) ?? []);
      setGateway(ok(gv));
      setIntegrations(ok(it) ?? []);
      setHealth(ok(mh));
      setMetrics(ok(mm) ?? []);
      setAlerts(ok(ma) ?? []);
      setLogs(ok(lg) ?? []);
      setEvents(ok(se) ?? []);
      setRules(ok(ru));
      setFrameworks(ok(fw) ?? {});
      setRecords(ok(rc) ?? []);
      setReport(ok(rp));
      setLicense(ok(lc));
      setPlanCatalog(ok(pc) ?? {});
      setFlags(ok(fl) ?? []);
      setAiModelsList(ok(mod) ?? []);
      setAiUsageData(ok(use));
      setAiMemory(ok(mem));
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

  const run = async (fn: () => Promise<unknown>, okMessage: string, then?: (result: unknown) => void) => {
    setBusy(true);
    setError(null);
    try {
      const result = await fn();
      setNotice(okMessage);
      if (then) then(result);
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // --------------------------------------------------------------- handlers

  const onCreateProvider = async () => {
    if (!form.name?.trim()) {
      setError("Provider name is required.");
      return;
    }
    await run(
      () =>
        createIdentityProvider({
          provider_type: form.provider_type || "saml",
          name: form.name,
          description: form.description,
          config: { entity_id: form.entity_id, sso_url: form.sso_url, client_id: form.client_id, server_url: form.server_url },
          enabled: form.enabled === "true",
        }),
      "Identity provider created."
    );
    setShowProvider(false);
    setForm({});
  };

  const onToggleProvider = async (provider: IdentityProvider) => {
    await run(
      () => updateIdentityProvider(provider.id, { enabled: !provider.enabled }),
      provider.enabled ? "Provider disabled." : "Provider enabled."
    );
  };

  const onDeleteProvider = async (provider: IdentityProvider) => {
    if (!window.confirm(`Delete identity provider "${provider.name}"?`)) return;
    await run(() => deleteIdentityProvider(provider.id), "Provider deleted.");
  };

  const onCreatePolicy = async () => {
    if (!form.name?.trim()) {
      setError("Policy name is required.");
      return;
    }
    await run(
      () =>
        createAuthPolicy({
          name: form.name,
          mfa_required: form.mfa_required === "true",
          passkey_required: form.passkey_required === "true",
          session_timeout_minutes: Number(form.session_timeout_minutes || 480),
          ip_restrictions: form.ip_restrictions
            ? form.ip_restrictions.split(",").map((ip) => ip.trim()).filter(Boolean)
            : [],
          password_policy: { min_length: Number(form.min_length || 8) },
        }),
      "Authentication policy created."
    );
    setShowPolicy(false);
    setForm({});
  };

  const onEnrollMfa = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await enrollMfa();
      setMfa(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onVerifyMfa = async () => {
    await run(() => verifyMfa(mfaCode), "MFA enabled.");
    setMfa(null);
    setMfaCode("");
  };

  const onSsoInitiate = async (providerId: string) => {
    setBusy(true);
    setError(null);
    try {
      setSsoResult(await ssoInitiate(providerId, "/enterprise?tab=identity"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onTrustDevice = async () => {
    await run(() => trustDevice({ name: form.name || "New device", device_type: form.device_type || "desktop" }), "Device trusted.");
    setForm({});
  };

  const onCreateScimUser = async () => {
    if (!form.userName?.trim()) {
      setError("Username is required.");
      return;
    }
    await run(
      () => scimCreateUser({ userName: form.userName, emails: form.email ? [{ value: form.email, primary: true }] : [], active: true, externalId: form.externalId || undefined }),
      "SCIM user provisioned."
    );
    setShowScimUser(false);
    setForm({});
  };

  const onDeactivateScimUser = async (scimUser: ScimUserResource) => {
    await run(() => scimUpdateUser(scimUser.id, { active: !scimUser.active }), "User status updated.");
  };

  const onDeleteScimUser = async (scimUser: ScimUserResource) => {
    if (!window.confirm(`Deprovision SCIM user "${scimUser.userName}"?`)) return;
    await run(() => scimDeleteUser(scimUser.id), "SCIM user deprovisioned.");
  };

  const onCreateScimGroup = async () => {
    if (!form.displayName?.trim()) {
      setError("Group name is required.");
      return;
    }
    const memberIds = form.members ? form.members.split(",").map((m) => m.trim()).filter(Boolean) : [];
    await run(
      () => scimCreateGroup({ displayName: form.displayName, externalId: form.externalId || form.displayName, members: memberIds.map((value) => ({ value })) }),
      "SCIM group created."
    );
    setShowScimGroup(false);
    setForm({});
  };

  const onDeleteScimGroup = async (group: ScimGroupResource) => {
    if (!window.confirm(`Delete SCIM group "${group.displayName}"?`)) return;
    await run(() => scimDeleteGroup(group.id), "SCIM group deleted.");
  };

  const onInstallPlugin = async () => {
    if (!form.plugin_key?.trim()) {
      setError("Plugin key is required.");
      return;
    }
    await run(
      () =>
        installPlugin({
          plugin_key: form.plugin_key,
          name: form.name || form.plugin_key,
          description: form.description,
          manifest: { version: "1.0.0", entry: "index.js", code: "function run(input) { return input; }" },
        }),
      "Plugin installed."
    );
    setShowPlugin(false);
    setForm({});
  };

  const onTogglePlugin = async (plugin: Plugin) => {
    await run(
      () => (plugin.status === "disabled" ? enablePlugin(plugin.id) : disablePlugin(plugin.id)),
      plugin.status === "disabled" ? "Plugin enabled." : "Plugin disabled."
    );
  };

  const onUpdatePlugin = async (plugin: Plugin) => {
    await run(
      () => updatePlugin(plugin.id, { version: "2.0.0", changelog: "Routine update" }),
      "Plugin updated."
    );
  };

  const onRemovePlugin = async (plugin: Plugin) => {
    if (!window.confirm(`Remove plugin "${plugin.name}"?`)) return;
    await run(() => removePlugin(plugin.id), "Plugin removed.");
  };

  const onPublishMarketplaceItem = async () => {
    if (!form.plugin_key?.trim() || !form.name?.trim()) {
      setError("Plugin key and name are required.");
      return;
    }
    await run(
      () =>
        publishMarketplaceItem({
          plugin_key: form.plugin_key,
          name: form.name,
          description: form.description,
          category: form.category || "general",
          price: Number(form.price || 0),
          version: form.version || "1.0.0",
          manifest: {},
        }),
      "Marketplace listing published."
    );
    setShowMarketplaceItem(false);
    setForm({});
  };

  const onInstallMarketplaceItem = async (item: MarketplaceItem) => {
    await run(() => installMarketplaceItem(item.id), `${item.name} installed.`);
  };

  const onUnpublishItem = async (item: MarketplaceItem) => {
    await run(() => updateMarketplaceItem(item.id, { published: false }), "Listing unpublished.");
  };

  const onCreateApiKey = async () => {
    if (!form.name?.trim()) {
      setError("Key name is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const key = await createApiKey({
        name: form.name,
        scopes: form.scopes ? form.scopes.split(",").map((s) => s.trim()).filter(Boolean) : [],
        rate_limit_per_minute: Number(form.rate_limit_per_minute || 120),
      });
      setSecret({ label: key.name, value: key.key ?? "" });
      setNotice("API key created — copy the secret now, it is only shown once.");
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
    setShowApiKey(false);
    setForm({});
  };

  const onRotateKey = async (key: ApiKeyRow) => {
    setBusy(true);
    setError(null);
    try {
      const rotated = await rotateApiKey(key.id);
      setSecret({ label: rotated.name, value: rotated.key ?? "" });
      setNotice("API key rotated — copy the new secret now.");
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onRevokeKey = async (key: ApiKeyRow) => {
    if (!window.confirm(`Revoke API key "${key.name}"?`)) return;
    await run(() => revokeApiKey(key.id), "API key revoked.");
  };

  const onCreateIntegration = async () => {
    if (!form.name?.trim()) {
      setError("Integration name is required.");
      return;
    }
    await run(
      () =>
        createEnterpriseIntegration({
          name: form.name,
          provider: form.provider || form.name,
          kind: form.kind || "webhook",
          auth_type: form.auth_type || "oauth2",
          config: { url: form.url, api_key: form.api_key },
        }),
      "Integration connected."
    );
    setShowIntegration(false);
    setForm({});
  };

  const onTestIntegration = async (connection: IntegrationConnection) => {
    await run(() => testEnterpriseIntegration(connection.id), `${connection.name} test passed.`);
  };

  const onSyncIntegration = async (connection: IntegrationConnection) => {
    await run(() => syncEnterpriseIntegration(connection.id), `${connection.name} synced.`);
  };

  const onRemoveIntegration = async (connection: IntegrationConnection) => {
    if (!window.confirm(`Disconnect integration "${connection.name}"?`)) return;
    await run(() => deleteIntegration(connection.id), "Integration disconnected.");
  };

  const onIngestMetric = async () => {
    if (!form.name?.trim()) {
      setError("Metric name is required.");
      return;
    }
    await run(
      () => ingestMetric({ name: form.name, value: Number(form.value || 0), unit: form.unit || undefined, tags: form.tags ? JSON.parse(form.tags) : undefined }),
      "Metric recorded."
    );
    setShowMetric(false);
    setForm({});
  };

  const onIngestLog = async () => {
    if (!form.message?.trim()) {
      setError("Log message is required.");
      return;
    }
    await run(
      () =>
        ingestLog({
          message: form.message,
          level: form.level || "info",
          source: form.source || "app",
          trace_id: form.trace_id || undefined,
        }),
      "Log ingested."
    );
    setShowLog(false);
    setForm({});
  };

  const onRecordSecurityEvent = async () => {
    if (!form.title?.trim()) {
      setError("Title is required.");
      return;
    }
    await run(
      () =>
        recordSecurityEvent({
          event_type: form.event_type || "policy.violation",
          severity: form.severity || "medium",
          title: form.title,
          source_ip: form.source_ip || undefined,
          details: form.details ? { note: form.details } : undefined,
        }),
      "Security event recorded."
    );
    setShowSecurityEvent(false);
    setForm({});
  };

  const onDetectFailedLogin = async () => {
    if (!form.email?.trim()) return;
    await run(
      () => detectFailedLogin(form.email, form.source_ip || "0.0.0.0"),
      "Failed login recorded."
    );
    setForm({});
  };

  const onResolveEvent = async (event: SecurityEvent) => {
    await run(() => resolveSecurityEvent(event.id), "Event resolved.");
  };

  const onCheckIp = async () => {
    if (!form.ip?.trim()) return;
    await run(() => checkIp(form.ip), "IP check complete.");
    setForm({});
  };

  const onUpsertComplianceRecord = async () => {
    if (!form.framework?.trim() || !form.control?.trim()) {
      setError("Framework and control are required.");
      return;
    }
    await run(
      () =>
        upsertComplianceRecord({
          framework: form.framework,
          control: form.control,
          status: form.status || "pending",
          title: form.title || form.control,
          notes: form.notes,
          evidence: form.evidence ? { document: form.evidence } : undefined,
          due_at: form.due_at || undefined,
        }),
      "Compliance control updated."
    );
    setShowComplianceRecord(false);
    setForm({});
  };

  const onUpdateRecordStatus = async (record: ComplianceControl, status: string) => {
    await run(() => updateComplianceRecord(record.id, { status }), `Control marked ${status}.`);
  };

  const onChangePlan = async (plan: string) => {
    await run(() => changeLicensePlan({ plan }), `Plan changed to ${plan}.`);
  };

  const onRefreshLicense = async () => {
    await run(() => refreshLicense(), "License refreshed.");
  };

  const onCreateFlag = async () => {
    if (!form.key?.trim() || !form.name?.trim()) {
      setError("Key and name are required.");
      return;
    }
    await run(
      () =>
        createFeatureFlag({
          key: form.key,
          name: form.name,
          description: form.description,
          enabled: form.enabled === "true",
          rules: { percentage: Number(form.percentage ?? 100), users: form.users ? form.users.split(",").map((u) => u.trim()).filter(Boolean) : [], roles: form.roles ? form.roles.split(",").map((r) => r.trim()).filter(Boolean) : [] },
        }),
      "Feature flag created."
    );
    setShowFlag(false);
    setForm({});
  };

  const onToggleFlag = async (flag: FeatureFlag) => {
    await run(() => updateFeatureFlag(flag.id, { enabled: !flag.enabled }), flag.enabled ? "Flag disabled." : "Flag enabled.");
  };

  const onDeleteFlag = async (flag: FeatureFlag) => {
    if (!window.confirm(`Delete flag "${flag.key}"?`)) return;
    await run(() => deleteFeatureFlag(flag.id), "Flag deleted.");
  };

  const onEvaluateFlag = async (flag: FeatureFlag) => {
    const result = await evaluateFeatureFlag(flag.key, [user?.role ?? ""]);
    setNotice(`${flag.key} → ${result.enabled ? "ON" : "OFF"} (${result.reason})`);
  };

  const onSetConsent = async () => {
    await run(
      () => setAiConsent(form.scope || "model_training", form.granted === "true"),
      "AI consent updated."
    );
    setShowAiConsent(false);
    setForm({});
  };

  if (loading) return <Spinner label="Loading enterprise console…" />;
  if (error && !notice) return <ErrorState message={error} onRetry={() => loadAll(true)} />;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb="Enterprise"
        title="Enterprise Platform"
        description="Identity, SSO/SCIM, plugins, marketplace, API gateway, integrations, monitoring, security, compliance, licensing and governed AI."
        actions={
          canIdentity ? (
            <>
              <Button variant="secondary" loading={busy} onClick={() => { setShowProvider(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> Provider
              </Button>
              <Button variant="secondary" loading={busy} onClick={onEnrollMfa}>
                <Fingerprint className="h-3.5 w-3.5" /> Enroll MFA
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

      {mfa && (
        <Card title="Enroll MFA" subtitle="Scan or save this TOTP secret, then verify with a code">
          <div className="space-y-3">
            <p className="font-mono text-sm text-ink">{mfa.mfa_secret}</p>
            <div className="flex max-w-xs gap-2">
              <Input placeholder="6-digit code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} />
              <Button loading={busy} onClick={onVerifyMfa}>Verify</Button>
            </div>
          </div>
        </Card>
      )}

      {secret && (
        <Card title={`Secret for ${secret.label}`} subtitle="Copy this now — it will not be shown again">
          <p className="break-all font-mono text-sm text-ink">{secret.value}</p>
        </Card>
      )}

      {ssoResult && (
        <Card title="SSO initiation" subtitle="Redirect the user to the provider">
          <p className="break-all font-mono text-xs text-ink">{String(ssoResult.auth_url ?? ssoResult.url ?? JSON.stringify(ssoResult))}</p>
        </Card>
      )}

      {tab === "overview" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Installed plugins" value={overview?.installed_plugins ?? plugins.length} hint={`${overview?.identity_providers ?? providers.length} SSO providers`} icon={Boxes} />
            <StatCard label="Active API keys" value={overview?.active_api_keys ?? apiKeys.length} hint={`${overview?.metric_samples ?? metrics.length} metric samples`} icon={KeyRound} />
            <StatCard label="Integrations" value={overview?.active_integrations ?? integrations.length} icon={ArrowLeftRight} />
            <StatCard label="Open security events" value={overview?.open_security_events ?? events.filter((e) => e.status === "open").length} hint={`${overview?.enabled_feature_flags ?? flags.filter((f) => f.enabled).length} flags enabled`} icon={ShieldAlert} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card
              title="License"
              subtitle={license ? `Plan ${license.plan} · ${license.seats} seats · ${license.features.length} features` : "No license yet"}
              actions={
                canLicenses ? (
                  <Select value={license?.plan ?? "starter"} onChange={(e) => onChangePlan(e.target.value)} options={PLANS} className="w-40" />
                ) : undefined
              }
            >
              <div className="flex flex-wrap gap-1.5">
                {(license?.features ?? []).map((feature) => (
                  <Badge key={feature} tone="brand">{feature}</Badge>
                ))}
                {(license?.features ?? []).length === 0 && <p className="text-sm text-faint">Starter plan includes core features.</p>}
              </div>
            </Card>

            <Card title="Security posture" subtitle={rules ? `Brute force at ${rules.brute_force_threshold} failed logins per ${rules.brute_force_window_minutes} min` : "Security rules unavailable"}>
              <div className="flex flex-wrap gap-1.5">
                {(rules?.event_types ?? []).slice(0, 12).map((eventType) => (
                  <Badge key={eventType} tone="warning">{eventType}</Badge>
                ))}
                {(rules?.event_types ?? []).length === 0 && <p className="text-sm text-faint">No event types configured.</p>}
              </div>
            </Card>
          </div>

          <Card title="Open security events" subtitle={`${events.filter((e) => e.status === "open").length} open`} bodyClassName="p-0">
            <Table head={<><Th>Event</Th><Th>Type</Th><Th>Severity</Th><Th>Source</Th><Th>Status</Th></>}>
              {events.filter((e) => e.status === "open").slice(0, 6).map((event) => (
                <Tr key={event.id}>
                  <Td className="font-medium">{event.title}</Td>
                  <Td><Badge tone="brand">{event.event_type}</Badge></Td>
                  <Td><Badge tone={severityTone(event.severity)}>{event.severity}</Badge></Td>
                  <Td className="text-muted">{event.source_ip ?? "—"}</Td>
                  <Td><Badge tone={checkTone(event.status)}>{event.status}</Badge></Td>
                </Tr>
              ))}
            </Table>
            {events.filter((e) => e.status === "open").length === 0 && (
              <EmptyState title="All clear" description="No open security events." />
            )}
          </Card>
        </div>
      )}

      {tab === "identity" && (
        <div className="space-y-5">
          <Card
            title="SSO providers"
            subtitle={`${providers.length} providers · ${providers.filter((p) => p.enabled).length} enabled`}
            actions={
              canIdentity ? (
                <Button size="sm" variant="secondary" onClick={() => { setShowProvider(true); setForm({}); }}>
                  <Plus className="h-3.5 w-3.5" /> New provider
                </Button>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Name</Th><Th>Type</Th><Th>Status</Th><Th>Config</Th><Th /></>}>
              {providers.map((provider) => (
                <Tr key={provider.id}>
                  <Td className="font-medium">{provider.name}</Td>
                  <Td><Badge tone="brand">{provider.provider_type}</Badge></Td>
                  <Td><Badge tone={checkTone(provider.enabled ? "enabled" : "disabled")}>{provider.enabled ? "enabled" : "disabled"}</Badge></Td>
                  <Td className="text-xs text-muted">{Object.keys(provider.config ?? {}).slice(0, 3).join(", ") || "—"}</Td>
                  <Td className="text-right">
                    {canIdentity && (
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="secondary" loading={busy} onClick={() => onSsoInitiate(provider.id)}>Test SSO</Button>
                        <Button size="sm" variant="ghost" loading={busy} onClick={() => onToggleProvider(provider)}>{provider.enabled ? "Disable" : "Enable"}</Button>
                        <Button size="sm" variant="ghost" loading={busy} onClick={() => onDeleteProvider(provider)}>Delete</Button>
                      </div>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {providers.length === 0 && <EmptyState title="No SSO providers" description="Add a SAML, OIDC, OAuth2 or LDAP provider." />}
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Authentication policy" subtitle="Org-wide MFA, session and IP restrictions" bodyClassName="p-0">
              {policy ? (
                <div className="space-y-3 p-4">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge tone={policy.mfa_required ? "success" : "neutral"}>{policy.mfa_required ? "MFA required" : "MFA optional"}</Badge>
                    <Badge tone={policy.passkey_required ? "success" : "neutral"}>{policy.passkey_required ? "Passkeys required" : "Passkeys optional"}</Badge>
                    <Badge tone="brand">{policy.session_timeout_minutes} min sessions</Badge>
                    <Badge tone={policy.enabled ? "success" : "warning"}>{policy.enabled ? "enabled" : "disabled"}</Badge>
                  </div>
                  {(policy.ip_restrictions ?? []).length > 0 && (
                    <p className="text-xs text-muted">Allowed IPs: {policy.ip_restrictions.join(", ")}</p>
                  )}
                </div>
              ) : (
                <EmptyState title="No policy yet" description="Create an authentication policy for this organization." />
              )}
            </Card>

            <Card title="Trusted devices" subtitle={`${devices.length} devices`} bodyClassName="p-0">
              <Table head={<><Th>Name</Th><Th>Type</Th><Th>Trusted</Th><Th>Last seen</Th></>}>
                {devices.slice(0, 6).map((device) => (
                  <Tr key={device.id}>
                    <Td className="font-medium">{device.name}</Td>
                    <Td><Badge tone="brand">{device.device_type}</Badge></Td>
                    <Td><Badge tone={checkTone(device.trusted ? "active" : "disabled")}>{device.trusted ? "yes" : "no"}</Badge></Td>
                    <Td className="text-muted">{device.last_seen_at ? device.last_seen_at.slice(0, 10) : "never"}</Td>
                  </Tr>
                ))}
              </Table>
              {devices.length === 0 && <EmptyState title="No devices" description="Devices you trust for passwordless flows appear here." />}
            </Card>
          </div>

          <Card title="SCIM directory" subtitle={`${scimUsers.length} users · ${scimGroups.length} groups`} bodyClassName="p-0">
            <Table head={<><Th>User</Th><Th>External ID</Th><Th>Active</Th><Th /></>}>
              {scimUsers.slice(0, 8).map((scimUser) => (
                <Tr key={scimUser.id}>
                  <Td className="font-medium">{scimUser.userName}</Td>
                  <Td className="text-muted">{scimUser.externalId ?? "—"}</Td>
                  <Td><Badge tone={checkTone(scimUser.active ? "active" : "disabled")}>{scimUser.active ? "active" : "inactive"}</Badge></Td>
                  <Td className="text-right">
                    {canIdentity && (
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="ghost" loading={busy} onClick={() => onDeactivateScimUser(scimUser)}>{scimUser.active ? "Deactivate" : "Reactivate"}</Button>
                        <Button size="sm" variant="ghost" loading={busy} onClick={() => onDeleteScimUser(scimUser)}>Deprovision</Button>
                      </div>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {scimUsers.length === 0 && <EmptyState title="No SCIM users" description="Provision users from your identity provider." />}
          </Card>

          <Card title="Identity bindings" subtitle={`${bindings.length} external subject bindings`} bodyClassName="p-0">
            <Table head={<><Th>Subject</Th><Th>Provider</Th><Th>User ID</Th><Th>MFA</Th><Th>Status</Th></>}>
              {bindings.slice(0, 8).map((binding) => (
                <Tr key={binding.id}>
                  <Td className="font-medium">{binding.external_subject}</Td>
                  <Td><Badge tone="brand">{binding.provider}</Badge></Td>
                  <Td className="text-muted">{binding.user_id.slice(0, 8)}</Td>
                  <Td><Badge tone={binding.mfa_enabled ? "success" : "neutral"}>{binding.mfa_enabled ? "on" : "off"}</Badge></Td>
                  <Td><Badge tone={checkTone(binding.status)}>{binding.status}</Badge></Td>
                </Tr>
              ))}
            </Table>
            {bindings.length === 0 && <EmptyState title="No bindings" description="SSO assertions create subject-to-user bindings." />}
          </Card>
        </div>
      )}

      {tab === "plugins" && (
        <Card
          title="Installed plugins"
          subtitle={`${plugins.length} plugins · ${plugins.filter((p) => p.status === "installed").length} active`}
          actions={
            canPlugins ? (
              <Button size="sm" variant="secondary" onClick={() => { setShowPlugin(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> Install plugin
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table head={<><Th>Plugin</Th><Th>Version</Th><Th>Category</Th><Th>Scan</Th><Th>Status</Th><Th /></>}>
            {plugins.map((plugin) => (
              <Tr key={plugin.id}>
                <Td>
                  <p className="font-medium text-ink">{plugin.name}</p>
                  <p className="text-xs text-faint">{plugin.plugin_key}</p>
                </Td>
                <Td><Badge tone="brand">v{plugin.version}</Badge></Td>
                <Td className="text-muted">{plugin.category}</Td>
                <Td><Badge tone={plugin.scan_status === "passed" ? "success" : plugin.scan_status === "blocked" ? "danger" : "warning"}>{plugin.scan_status}</Badge></Td>
                <Td><Badge tone={checkTone(plugin.status)}>{plugin.status}</Badge></Td>
                <Td className="text-right">
                  {canPlugins && (
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onTogglePlugin(plugin)}>{plugin.status === "disabled" ? "Enable" : "Disable"}</Button>
                      <Button size="sm" variant="ghost" loading={busy} onClick={() => onUpdatePlugin(plugin)}>Update</Button>
                      <Button size="sm" variant="ghost" loading={busy} onClick={() => onRemovePlugin(plugin)}>Remove</Button>
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
          {plugins.length === 0 && <EmptyState title="No plugins installed" description="Install plugins from the marketplace or add one directly." />}
        </Card>
      )}

      {tab === "marketplace" && (
        <div className="space-y-5">
          <Card
            title="Marketplace"
            subtitle={`${marketplace.length} listings · ${marketplace.filter((i) => i.verified).length} verified`}
            actions={
              canMarketplace ? (
                <Button size="sm" variant="secondary" onClick={() => { setShowMarketplaceItem(true); setForm({}); }}>
                  <Plus className="h-3.5 w-3.5" /> Publish listing
                </Button>
              ) : undefined
            }
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {marketplace.map((item) => (
                <div key={item.id} className="rounded-xl border border-line bg-surface p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink">{item.name}</p>
                      <p className="text-xs text-faint">{item.plugin_key} · v{item.version}</p>
                    </div>
                    <Badge tone={item.verified ? "success" : "neutral"}>{item.verified ? "verified" : "unverified"}</Badge>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm text-muted">{item.description ?? "No description."}</p>
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs text-muted">
                      <span className="font-semibold text-ink">{item.rating.toFixed(1)}</span>
                      <span>· {item.review_count} reviews</span>
                      <span>· {item.downloads} installs</span>
                    </div>
                    <span className="text-sm font-semibold text-ink">{item.price > 0 ? `$${item.price}` : "Free"}</span>
                  </div>
                  {canPlugins && (
                    <Button size="sm" variant="secondary" className="mt-3 w-full" loading={busy} onClick={() => onInstallMarketplaceItem(item)}>
                      <Rocket className="h-3.5 w-3.5" /> Install
                    </Button>
                  )}
                </div>
              ))}
            </div>
            {marketplace.length === 0 && <EmptyState title="Marketplace is empty" description="Publish plugin listings for the organization." />}
          </Card>
        </div>
      )}

      {tab === "gateway" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Active keys" value={apiKeys.filter((k) => k.status === "active").length} hint={`${apiKeys.length} total`} icon={KeyRound} />
            <StatCard label="Rate limit" value={gateway?.default_rate_limit_per_minute ?? 120} hint="requests / minute" icon={Activity} />
            <StatCard label="Auth header" value={gateway?.auth_header ?? "X-API-Key"} hint="gateway header" icon={Lock} />
            <StatCard label="Versions" value={(gateway?.versions ?? []).join(", ") || "—"} icon={Boxes} />
          </div>

          <Card
            title="API keys"
            subtitle="Secrets are hashed at rest; plaintext is shown once"
            actions={
              canApiKeys ? (
                <Button size="sm" variant="secondary" onClick={() => { setShowApiKey(true); setForm({}); }}>
                  <Plus className="h-3.5 w-3.5" /> New key
                </Button>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Name</Th><Th>Prefix</Th><Th>Scopes</Th><Th>Limit</Th><Th>Status</Th><Th /></>}>
              {apiKeys.map((key) => (
                <Tr key={key.id}>
                  <Td className="font-medium">{key.name}</Td>
                  <Td className="font-mono text-xs text-muted">{key.key_prefix}…</Td>
                  <Td className="text-xs text-muted">{(key.scopes ?? []).join(", ") || "all"}</Td>
                  <Td>{key.rate_limit_per_minute}/min</Td>
                  <Td><Badge tone={checkTone(key.status)}>{key.status}</Badge></Td>
                  <Td className="text-right">
                    {canApiKeys && (
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="secondary" loading={busy} onClick={() => onRotateKey(key)}>Rotate</Button>
                        <Button size="sm" variant="ghost" loading={busy} onClick={() => onRevokeKey(key)}>Revoke</Button>
                      </div>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {apiKeys.length === 0 && <EmptyState title="No API keys" description="Create a key for external systems to call the gateway." />}
          </Card>
        </div>
      )}

      {tab === "integrations" && (
        <Card
          title="Integrations"
          subtitle={`${integrations.length} connections · ${integrations.filter((i) => i.status === "active").length} active`}
          actions={
            canIntegrations ? (
              <Button size="sm" variant="secondary" onClick={() => { setShowIntegration(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> Connect
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table head={<><Th>Name</Th><Th>Provider</Th><Th>Kind</Th><Th>Auth</Th><Th>Last sync</Th><Th>Status</Th><Th /></>}>
            {integrations.map((connection) => (
              <Tr key={connection.id}>
                <Td className="font-medium">{connection.name}</Td>
                <Td className="text-muted">{connection.provider}</Td>
                <Td><Badge tone="brand">{connection.kind}</Badge></Td>
                <Td className="text-muted">{connection.auth_type}</Td>
                <Td className="text-muted">{connection.last_sync_at ? connection.last_sync_at.slice(0, 10) : "never"}</Td>
                <Td><Badge tone={checkTone(connection.status)}>{connection.status}</Badge></Td>
                <Td className="text-right">
                  {canIntegrations && (
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onTestIntegration(connection)}>Test</Button>
                      <Button size="sm" variant="ghost" loading={busy} onClick={() => onSyncIntegration(connection)}>Sync</Button>
                      <Button size="sm" variant="ghost" loading={busy} onClick={() => onRemoveIntegration(connection)}>Remove</Button>
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
          {integrations.length === 0 && <EmptyState title="No integrations" description="Connect webhooks, APIs and data sources." />}
        </Card>
      )}

      {tab === "monitoring" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Status" value={health?.status ?? "—"} hint="live health check" icon={Activity} />
            <StatCard label="HTTP error rate" value={`${(health?.checks.http_error_rate?.value ?? 0).toFixed(2)}%`} hint={`threshold ${health?.checks.http_error_rate?.threshold ?? 5}%`} icon={ShieldAlert} />
            <StatCard label="Latency" value={health?.checks.latency_ms?.value != null ? `${health.checks.latency_ms.value.toFixed(1)} ms` : "—"} icon={Activity} />
            <StatCard label="Uptime" value={health?.checks.uptime_percent?.value != null ? `${health.checks.uptime_percent.value.toFixed(1)}%` : "—"} icon={BarChart3} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Active alerts" subtitle={`${alerts.length} alerts`} bodyClassName="p-0">
              <Table head={<><Th>Severity</Th><Th>Metric</Th><Th>Message</Th></>}>
                {alerts.map((alert, index) => (
                  <Tr key={index}>
                    <Td><Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge></Td>
                    <Td className="font-medium">{alert.name}</Td>
                    <Td className="text-muted">{alert.message}</Td>
                  </Tr>
                ))}
              </Table>
              {alerts.length === 0 && <EmptyState title="No alerts" description="All systems nominal." />}
            </Card>

            <Card
              title="Recent metrics"
              subtitle={`${metrics.length} samples`}
              actions={
                canManage ? (
                  <Button size="sm" variant="ghost" onClick={() => { setShowMetric(true); setForm({}); }}>
                    <Plus className="h-3.5 w-3.5" /> Ingest
                  </Button>
                ) : undefined
              }
              bodyClassName="p-0"
            >
              <Table head={<><Th>Name</Th><Th>Value</Th><Th>Unit</Th><Th>Recorded</Th></>}>
                {metrics.slice(0, 8).map((metric) => (
                  <Tr key={metric.id}>
                    <Td className="font-medium">{metric.name}</Td>
                    <Td>{metric.value}</Td>
                    <Td className="text-muted">{metric.unit ?? "—"}</Td>
                    <Td className="text-muted">{metric.recorded_at ? metric.recorded_at.slice(0, 16).replace("T", " ") : "—"}</Td>
                  </Tr>
                ))}
              </Table>
              {metrics.length === 0 && <EmptyState title="No metrics" description="Ingest metric samples to build time series." />}
            </Card>
          </div>
        </div>
      )}

      {tab === "observability" && (
        <Card
          title="Log stream"
          subtitle={`${logs.length} recent log lines`}
          actions={
            canManage ? (
              <Button size="sm" variant="ghost" onClick={() => { setShowLog(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> Ingest
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table head={<><Th>Level</Th><Th>Source</Th><Th>Message</Th><Th>Trace</Th><Th>Recorded</Th></>}>
            {logs.map((log) => (
              <Tr key={log.id}>
                <Td><Badge tone={log.level === "error" ? "danger" : log.level === "warn" ? "warning" : "brand"}>{log.level}</Badge></Td>
                <Td className="text-muted">{log.source}</Td>
                <Td className="max-w-md truncate">{log.message}</Td>
                <Td className="font-mono text-xs text-faint">{log.trace_id ? log.trace_id.slice(0, 8) : "—"}</Td>
                <Td className="text-muted">{log.recorded_at ? log.recorded_at.slice(0, 16).replace("T", " ") : "—"}</Td>
              </Tr>
            ))}
          </Table>
          {logs.length === 0 && <EmptyState title="No logs" description="Structured logs with trace correlation appear here." />}
        </Card>
      )}

      {tab === "security" && (
        <div className="space-y-5">
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Detection rules" subtitle={rules ? `Threshold: ${rules.brute_force_threshold} failures / ${rules.brute_force_window_minutes} minutes` : "Rules unavailable"}>
              <div className="flex flex-wrap gap-1.5">
                {(rules?.event_types ?? []).map((eventType) => (
                  <Badge key={eventType} tone="warning">{eventType}</Badge>
                ))}
              </div>
            </Card>

            <Card title="Quick actions" subtitle="Simulate detections and IP enforcement">
              <div className="space-y-3">
                <div className="flex gap-2">
                  <Input placeholder="email@example.com" value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                  <Input placeholder="IP" className="w-36" value={form.source_ip ?? ""} onChange={(e) => setForm({ ...form, source_ip: e.target.value })} />
                  <Button variant="secondary" loading={busy} onClick={onDetectFailedLogin}>Failed login</Button>
                </div>
                <div className="flex gap-2">
                  <Input placeholder="IP to check" value={form.ip ?? ""} onChange={(e) => setForm({ ...form, ip: e.target.value })} />
                  <Button variant="secondary" loading={busy} onClick={onCheckIp}>Check IP</Button>
                </div>
              </div>
            </Card>
          </div>

          <Card
            title="Security events"
            subtitle={`${events.length} events · ${events.filter((e) => e.status === "open").length} open`}
            actions={
              canSecurity ? (
                <Button size="sm" variant="secondary" onClick={() => { setShowSecurityEvent(true); setForm({}); }}>
                  <Plus className="h-3.5 w-3.5" /> Record event
                </Button>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Title</Th><Th>Type</Th><Th>Severity</Th><Th>Source</Th><Th>Status</Th><Th /></>}>
              {events.slice(0, 12).map((event) => (
                <Tr key={event.id}>
                  <Td className="font-medium">{event.title}</Td>
                  <Td><Badge tone="brand">{event.event_type}</Badge></Td>
                  <Td><Badge tone={severityTone(event.severity)}>{event.severity}</Badge></Td>
                  <Td className="text-muted">{event.source_ip ?? "—"}</Td>
                  <Td><Badge tone={checkTone(event.status)}>{event.status}</Badge></Td>
                  <Td className="text-right">
                    {canSecurity && event.status === "open" && (
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onResolveEvent(event)}>Resolve</Button>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {events.length === 0 && <EmptyState title="No security events" description="Detections and manual records appear here." />}
          </Card>
        </div>
      )}

      {tab === "compliance" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {report && typeof report === "object" && "frameworks" in report && report.frameworks && typeof report.frameworks === "object"
              ? Object.entries(report.frameworks as Record<string, Record<string, number>>).map(([framework, counts]) => (
                  <StatCard key={framework} label={framework.toUpperCase()} value={counts.pass ?? 0} hint={`${counts.fail ?? 0} failing · ${counts.pending ?? 0} pending`} icon={ShieldCheck} />
                ))
              : Object.keys(frameworks).map((framework) => (
                  <StatCard key={framework} label={framework.toUpperCase()} value={(frameworks[framework] ?? []).length} hint="controls defined" icon={ShieldCheck} />
                ))}
          </div>

          <Card
            title="Controls"
            subtitle={`${records.length} records · ${records.filter((r) => r.status === "pass").length} passing`}
            actions={
              canCompliance ? (
                <Button size="sm" variant="secondary" onClick={() => { setShowComplianceRecord(true); setForm({}); }}>
                  <Plus className="h-3.5 w-3.5" /> Upsert control
                </Button>
              ) : undefined
            }
            bodyClassName="p-0"
          >
            <Table head={<><Th>Control</Th><Th>Framework</Th><Th>Title</Th><Th>Due</Th><Th>Status</Th><Th /></>}>
              {records.slice(0, 12).map((record) => (
                <Tr key={record.id}>
                  <Td className="font-mono text-xs font-medium text-ink">{record.control}</Td>
                  <Td><Badge tone="brand">{record.framework}</Badge></Td>
                  <Td className="max-w-sm truncate text-muted">{record.title}</Td>
                  <Td className="text-muted">{record.due_at ? record.due_at.slice(0, 10) : "—"}</Td>
                  <Td><Badge tone={checkTone(record.status)}>{record.status}</Badge></Td>
                  <Td className="text-right">
                    {canCompliance && (
                      <div className="flex justify-end gap-1.5">
                        {(["pass", "fail", "pending"] as const).map((status) => (
                          <Button key={status} size="sm" variant="ghost" loading={busy} onClick={() => onUpdateRecordStatus(record, status)}>
                            {status}
                          </Button>
                        ))}
                      </div>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
            {records.length === 0 && <EmptyState title="No compliance records" description="Track controls across ISO 27001, SOC 2, GDPR, HIPAA, PCI and FedRAMP." />}
          </Card>
        </div>
      )}

      {tab === "licensing" && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card
            title="Current license"
            subtitle={`Status ${license?.status ?? "—"}`}
            actions={
              canLicenses ? (
                <Button size="sm" variant="ghost" loading={busy} onClick={onRefreshLicense}>
                  <RefreshCw className="h-3.5 w-3.5" /> Refresh
                </Button>
              ) : undefined
            }
          >
            <div className="space-y-4">
              <div>
                <p className="label">Plan</p>
                {canLicenses ? (
                  <Select value={license?.plan ?? "starter"} onChange={(e) => onChangePlan(e.target.value)} options={PLANS} className="mt-1.5 max-w-xs" />
                ) : (
                  <p className="text-lg font-semibold capitalize text-ink">{license?.plan ?? "starter"}</p>
                )}
              </div>
              <div>
                <p className="label">Seats</p>
                <p className="text-lg font-semibold text-ink">{license?.seats ?? 10}</p>
              </div>
              <div>
                <p className="label">Entitled features</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {(license?.features ?? []).map((feature) => (
                    <Badge key={feature} tone="success">{feature}</Badge>
                  ))}
                </div>
              </div>
              {license?.expires_at && <p className="text-xs text-faint">Expires {license.expires_at.slice(0, 10)}</p>}
            </div>
          </Card>

          <Card title="Plans" subtitle="Available enterprise plans">
            <div className="grid gap-3 sm:grid-cols-2">
              {Object.entries(planCatalog).map(([name, plan]) => {
                const details = plan as { seats?: number; price_per_seat?: number; features?: string[] };
                return (
                  <div key={name} className="rounded-xl border border-line bg-surface p-4">
                    <p className="font-semibold capitalize text-ink">{name}</p>
                    <p className="text-xs text-faint">{details.seats ?? 0} seats · ${details.price_per_seat ?? 0}/seat</p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(details.features ?? []).slice(0, 6).map((feature) => (
                        <Badge key={feature} tone="brand">{feature}</Badge>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      {tab === "flags" && (
        <Card
          title="Feature flags"
          subtitle={`${flags.length} flags · ${flags.filter((f) => f.enabled).length} enabled`}
          actions={
            canFlags ? (
              <Button size="sm" variant="secondary" onClick={() => { setShowFlag(true); setForm({}); }}>
                <Plus className="h-3.5 w-3.5" /> New flag
              </Button>
            ) : undefined
          }
          bodyClassName="p-0"
        >
          <Table head={<><Th>Key</Th><Th>Name</Th><Th>Rules</Th><Th>Status</Th><Th /></>}>
            {flags.map((flag) => (
              <Tr key={flag.id}>
                <Td className="font-mono text-xs font-medium text-ink">{flag.key}</Td>
                <Td>
                  <p className="font-medium text-ink">{flag.name}</p>
                  {flag.description && <p className="text-xs text-faint">{flag.description}</p>}
                </Td>
                <Td className="text-xs text-muted">
                  {flag.rules?.percentage != null ? `${flag.rules.percentage}% rollout` : "—"}
                  {Array.isArray(flag.rules?.roles) && (flag.rules.roles as string[]).length > 0 ? ` · roles: ${(flag.rules.roles as string[]).join(",")}` : ""}
                </Td>
                <Td>
                  <button onClick={() => canFlags && onToggleFlag(flag)} disabled={!canFlags} className="disabled:cursor-not-allowed">
                    <Badge tone={checkTone(flag.enabled ? "enabled" : "disabled")}>{flag.enabled ? "enabled" : "disabled"}</Badge>
                  </button>
                </Td>
                <Td className="text-right">
                  {canFlags && (
                    <div className="flex justify-end gap-1.5">
                      <Button size="sm" variant="secondary" loading={busy} onClick={() => onEvaluateFlag(flag)}>
                        <ToggleLeft className="h-3.5 w-3.5" /> Evaluate
                      </Button>
                      <Button size="sm" variant="ghost" loading={busy} onClick={() => onDeleteFlag(flag)}>Delete</Button>
                    </div>
                  )}
                </Td>
              </Tr>
            ))}
          </Table>
          {flags.length === 0 && <EmptyState title="No feature flags" description="Create flags to roll features out gradually." />}
        </Card>
      )}

      {tab === "ai" && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Models available" value={aiModelsList.length} hint="governed model catalog" icon={Bot} />
            <StatCard label="Usage records" value={typeof aiUsageData?.count === "number" ? aiUsageData.count : "—"} icon={BarChart3} />
            <StatCard label="Total tokens" value={typeof aiUsageData?.total_tokens === "number" ? Number(aiUsageData.total_tokens).toLocaleString() : "—"} icon={Activity} />
            <StatCard label="Consent scopes" value={typeof aiMemory?.consent === "object" ? Object.keys((aiMemory.consent as Record<string, unknown>) ?? {}).length : "—"} icon={ShieldCheck} />
          </div>

          <Card title="Model catalog" subtitle="Models available to your plan tier" bodyClassName="p-0">
            <Table head={<><Th>Model</Th><Th>Tier</Th></>}>
              {aiModelsList.map((model, index) => (
                <Tr key={index}>
                  <Td className="font-medium">{String(model.model ?? model.name ?? model.id ?? index)}</Td>
                  <Td><Badge tone="brand">{String(model.tier ?? "standard")}</Badge></Td>
                </Tr>
              ))}
            </Table>
            {aiModelsList.length === 0 && <EmptyState title="No models" description="Model catalog depends on your license tier." />}
          </Card>

          <Card title="AI governance" subtitle="Data consent and memory retention">
            <div className="space-y-3">
              {aiMemory && typeof aiMemory.consent === "object" && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(aiMemory.consent as Record<string, unknown>).map(([scope, granted]) => (
                    <Badge key={scope} tone={granted ? "success" : "warning"}>{scope}: {granted ? "granted" : "denied"}</Badge>
                  ))}
                </div>
              )}
              {canManage && (
                <Button variant="secondary" loading={busy} onClick={() => { setShowAiConsent(true); setForm({ granted: "true" }); }}>
                  <Send className="h-3.5 w-3.5" /> Update consent
                </Button>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Create modals */}
      <Modal open={showProvider} onClose={() => setShowProvider(false)} title="New identity provider" description="Connect SAML, OIDC, OAuth2 or LDAP">
        <div className="grid grid-cols-2 gap-3">
          <Select label="Type" value={form.provider_type ?? "saml"} onChange={(e) => setForm({ ...form, provider_type: e.target.value })} options={PROVIDER_TYPES} />
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Entity ID" value={form.entity_id ?? ""} onChange={(e) => setForm({ ...form, entity_id: e.target.value })} />
          <Input label="SSO URL" value={form.sso_url ?? ""} onChange={(e) => setForm({ ...form, sso_url: e.target.value })} />
          <Input label="Client ID" value={form.client_id ?? ""} onChange={(e) => setForm({ ...form, client_id: e.target.value })} />
          <Input label="LDAP server URL" value={form.server_url ?? ""} onChange={(e) => setForm({ ...form, server_url: e.target.value })} />
          <Select label="Enabled" value={form.enabled ?? "false"} onChange={(e) => setForm({ ...form, enabled: e.target.value })} options={[{ value: "true", label: "yes" }, { value: "false", label: "no" }]} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowProvider(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateProvider}>Create provider</Button>
        </div>
      </Modal>

      <Modal open={showPolicy} onClose={() => setShowPolicy(false)} title="New authentication policy" description="MFA, sessions and IP restrictions">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name *" className="col-span-2" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label="MFA required" value={form.mfa_required ?? "false"} onChange={(e) => setForm({ ...form, mfa_required: e.target.value })} options={[{ value: "true", label: "yes" }, { value: "false", label: "no" }]} />
          <Select label="Passkeys required" value={form.passkey_required ?? "false"} onChange={(e) => setForm({ ...form, passkey_required: e.target.value })} options={[{ value: "true", label: "yes" }, { value: "false", label: "no" }]} />
          <Input label="Session timeout (min)" type="number" value={form.session_timeout_minutes ?? "480"} onChange={(e) => setForm({ ...form, session_timeout_minutes: e.target.value })} />
          <Input label="Min password length" type="number" value={form.min_length ?? "8"} onChange={(e) => setForm({ ...form, min_length: e.target.value })} />
          <Input label="Allowed IPs (comma separated)" className="col-span-2" placeholder="203.0.113.0/24, 198.51.100.1" value={form.ip_restrictions ?? ""} onChange={(e) => setForm({ ...form, ip_restrictions: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowPolicy(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreatePolicy}>Create policy</Button>
        </div>
      </Modal>

      <Modal open={showScimUser} onClose={() => setShowScimUser(false)} title="Provision SCIM user" description="Create a directory user for the identity provider">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Username *" value={form.userName ?? ""} onChange={(e) => setForm({ ...form, userName: e.target.value })} />
          <Input label="Email" value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <Input label="External ID" className="col-span-2" value={form.externalId ?? ""} onChange={(e) => setForm({ ...form, externalId: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowScimUser(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateScimUser}>Provision</Button>
        </div>
      </Modal>

      <Modal open={showScimGroup} onClose={() => setShowScimGroup(false)} title="Create SCIM group" description="Mirror an identity provider group">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Display name *" value={form.displayName ?? ""} onChange={(e) => setForm({ ...form, displayName: e.target.value })} />
          <Input label="External ID" value={form.externalId ?? ""} onChange={(e) => setForm({ ...form, externalId: e.target.value })} />
          <Input label="Member IDs (comma separated)" className="col-span-2" value={form.members ?? ""} onChange={(e) => setForm({ ...form, members: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowScimGroup(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateScimGroup}>Create group</Button>
        </div>
      </Modal>

      <Modal open={showPlugin} onClose={() => setShowPlugin(false)} title="Install plugin" description="Installs into a sandbox with static code scanning">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Plugin key *" value={form.plugin_key ?? ""} onChange={(e) => setForm({ ...form, plugin_key: e.target.value })} />
          <Input label="Display name" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowPlugin(false)}>Cancel</Button>
          <Button loading={busy} onClick={onInstallPlugin}>Install</Button>
        </div>
      </Modal>

      <Modal open={showMarketplaceItem} onClose={() => setShowMarketplaceItem(false)} title="Publish marketplace listing" description="List a plugin for the organization">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Plugin key *" value={form.plugin_key ?? ""} onChange={(e) => setForm({ ...form, plugin_key: e.target.value })} />
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Category" value={form.category ?? "general"} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          <Input label="Price" type="number" value={form.price ?? "0"} onChange={(e) => setForm({ ...form, price: e.target.value })} />
          <Input label="Version" value={form.version ?? "1.0.0"} onChange={(e) => setForm({ ...form, version: e.target.value })} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowMarketplaceItem(false)}>Cancel</Button>
          <Button loading={busy} onClick={onPublishMarketplaceItem}>Publish</Button>
        </div>
      </Modal>

      <Modal open={showApiKey} onClose={() => setShowApiKey(false)} title="New API key" description="The secret is displayed once after creation">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Rate limit (per minute)" type="number" value={form.rate_limit_per_minute ?? "120"} onChange={(e) => setForm({ ...form, rate_limit_per_minute: e.target.value })} />
          <Input label="Scopes (comma separated)" className="col-span-2" placeholder="read, write" value={form.scopes ?? ""} onChange={(e) => setForm({ ...form, scopes: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowApiKey(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateApiKey}>Create key</Button>
        </div>
      </Modal>

      <Modal open={showIntegration} onClose={() => setShowIntegration(false)} title="Connect integration" description="Webhook, API or data source">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Provider" value={form.provider ?? ""} onChange={(e) => setForm({ ...form, provider: e.target.value })} />
          <Select label="Kind" value={form.kind ?? "webhook"} onChange={(e) => setForm({ ...form, kind: e.target.value })} options={INTEGRATION_KINDS} />
          <Select label="Auth type" value={form.auth_type ?? "oauth2"} onChange={(e) => setForm({ ...form, auth_type: e.target.value })} options={[{ value: "oauth2", label: "oauth2" }, { value: "bearer", label: "bearer" }, { value: "basic", label: "basic" }]} />
          <Input label="Endpoint URL" className="col-span-2" value={form.url ?? ""} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowIntegration(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateIntegration}>Connect</Button>
        </div>
      </Modal>

      <Modal open={showMetric} onClose={() => setShowMetric(false)} title="Ingest metric" description="Record a system metric sample">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input label="Value *" type="number" value={form.value ?? "0"} onChange={(e) => setForm({ ...form, value: e.target.value })} />
          <Input label="Unit" value={form.unit ?? ""} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
          <Input label="Tags (JSON)" value={form.tags ?? ""} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowMetric(false)}>Cancel</Button>
          <Button loading={busy} onClick={onIngestMetric}>Record</Button>
        </div>
      </Modal>

      <Modal open={showLog} onClose={() => setShowLog(false)} title="Ingest log" description="Structured log line with trace correlation">
        <div className="grid grid-cols-2 gap-3">
          <Select label="Level" value={form.level ?? "info"} onChange={(e) => setForm({ ...form, level: e.target.value })} options={[{ value: "info", label: "info" }, { value: "warn", label: "warn" }, { value: "error", label: "error" }, { value: "debug", label: "debug" }]} />
          <Input label="Source" value={form.source ?? "app"} onChange={(e) => setForm({ ...form, source: e.target.value })} />
          <Textarea label="Message *" className="col-span-2" value={form.message ?? ""} onChange={(e) => setForm({ ...form, message: e.target.value })} />
          <Input label="Trace ID" className="col-span-2" value={form.trace_id ?? ""} onChange={(e) => setForm({ ...form, trace_id: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowLog(false)}>Cancel</Button>
          <Button loading={busy} onClick={onIngestLog}>Ingest</Button>
        </div>
      </Modal>

      <Modal open={showSecurityEvent} onClose={() => setShowSecurityEvent(false)} title="Record security event" description="Log a detection manually">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Title *" value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <Input label="Event type" value={form.event_type ?? "policy.violation"} onChange={(e) => setForm({ ...form, event_type: e.target.value })} />
          <Select label="Severity" value={form.severity ?? "medium"} onChange={(e) => setForm({ ...form, severity: e.target.value })} options={SEVERITIES} />
          <Input label="Source IP" value={form.source_ip ?? ""} onChange={(e) => setForm({ ...form, source_ip: e.target.value })} />
          <Textarea label="Details" className="col-span-2" value={form.details ?? ""} onChange={(e) => setForm({ ...form, details: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowSecurityEvent(false)}>Cancel</Button>
          <Button loading={busy} onClick={onRecordSecurityEvent}>Record</Button>
        </div>
      </Modal>

      <Modal open={showComplianceRecord} onClose={() => setShowComplianceRecord(false)} title="Upsert compliance control" description="Track a framework control">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Framework *" value={form.framework ?? "iso27001"} onChange={(e) => setForm({ ...form, framework: e.target.value })} />
          <Input label="Control *" value={form.control ?? ""} onChange={(e) => setForm({ ...form, control: e.target.value })} />
          <Input label="Title" value={form.title ?? ""} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <Select label="Status" value={form.status ?? "pending"} onChange={(e) => setForm({ ...form, status: e.target.value })} options={CONTROL_STATUSES} />
          <Input label="Evidence reference" value={form.evidence ?? ""} onChange={(e) => setForm({ ...form, evidence: e.target.value })} />
          <Input label="Due date" type="date" value={form.due_at ?? ""} onChange={(e) => setForm({ ...form, due_at: e.target.value })} />
          <Textarea label="Notes" className="col-span-2" value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowComplianceRecord(false)}>Cancel</Button>
          <Button loading={busy} onClick={onUpsertComplianceRecord}>Save</Button>
        </div>
      </Modal>

      <Modal open={showFlag} onClose={() => setShowFlag(false)} title="New feature flag" description="Target users, roles or a rollout percentage">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Key *" value={form.key ?? ""} onChange={(e) => setForm({ ...form, key: e.target.value })} />
          <Input label="Name *" value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select label="Enabled" value={form.enabled ?? "true"} onChange={(e) => setForm({ ...form, enabled: e.target.value })} options={[{ value: "true", label: "yes" }, { value: "false", label: "no" }]} />
          <Input label="Rollout %" type="number" value={form.percentage ?? "100"} onChange={(e) => setForm({ ...form, percentage: e.target.value })} />
          <Input label="User IDs (comma separated)" className="col-span-2" value={form.users ?? ""} onChange={(e) => setForm({ ...form, users: e.target.value })} />
          <Input label="Roles (comma separated)" className="col-span-2" value={form.roles ?? ""} onChange={(e) => setForm({ ...form, roles: e.target.value })} />
          <Textarea label="Description" className="col-span-2" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowFlag(false)}>Cancel</Button>
          <Button loading={busy} onClick={onCreateFlag}>Create flag</Button>
        </div>
      </Modal>

      <Modal open={showAiConsent} onClose={() => setShowAiConsent(false)} title="Update AI consent" description="Govern data usage scopes">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Scope" value={form.scope ?? "model_training"} onChange={(e) => setForm({ ...form, scope: e.target.value })} />
          <Select label="Granted" value={form.granted ?? "true"} onChange={(e) => setForm({ ...form, granted: e.target.value })} options={[{ value: "true", label: "grant" }, { value: "false", label: "deny" }]} />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowAiConsent(false)}>Cancel</Button>
          <Button loading={busy} onClick={onSetConsent}>Save</Button>
        </div>
      </Modal>
    </div>
  );
}
