"use client";

import { useEffect, useState } from "react";
import {
  KeyRound,
  MessageSquare,
  GitBranch,
  Mail,
  Monitor,
  Ticket,
  Zap,
  Plus,
  Loader2,
  Key,
  RefreshCw,
  Trash2,
  X,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Globe,
} from "lucide-react";

import { api } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";
import type { IntegrationConnection } from "@/types";
import { EntitlementGate } from "@/hooks/useEntitlements";

const OAUTH_PROVIDERS = [
  {
    id: "microsoft",
    name: "Microsoft 365 / Entra ID",
    description: "Sync users, groups, mail, calendar, Teams, and SharePoint",
    iconName: "Monitor",
    color: "text-blue-600",
    bgColor: "bg-blue-600/10",
    scopes: [
      "openid",
      "email",
      "profile",
      "User.Read",
      "User.Read.All",
      "Group.Read.All",
      "Directory.Read.All",
      "Mail.Read",
      "Calendars.Read",
      "Team.ReadBasic.All",
      "Channel.ReadBasic.All",
      "Files.Read.All",
    ],
  },
  {
    id: "google",
    name: "Google Workspace",
    description: "Sync users, groups, Drive, Calendar, and Gmail",
    iconName: "Mail",
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
    scopes: [
      "openid",
      "email",
      "profile",
      "https://www.googleapis.com/auth/drive.readonly",
      "https://www.googleapis.com/auth/calendar.readonly",
      "https://www.googleapis.com/auth/admin.directory.user.readonly",
      "https://www.googleapis.com/auth/admin.directory.group.readonly",
    ],
  },
  {
    id: "slack",
    name: "Slack",
    description: "Sync channels, messages, users, and files",
    iconName: "MessageSquare",
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
    scopes: [
      "channels:read",
      "channels:history",
      "groups:read",
      "groups:history",
      "users:read",
      "users:read.email",
      "team:read",
      "files:read",
    ],
  },
  {
    id: "github",
    name: "GitHub",
    description: "Sync repositories, issues, PRs, commits, and members",
    iconName: "GitBranch",
    color: "text-gray-500",
    bgColor: "bg-gray-500/10",
    scopes: ["repo", "read:org", "read:user", "user:email", "admin:repo_hook"],
  },
  {
    id: "jira",
    name: "Jira",
    description: "Sync projects, issues, sprints, and users",
    iconName: "Ticket",
    color: "text-blue-600",
    bgColor: "bg-blue-600/10",
    scopes: [],
  },
] as const;

const ICON_MAP: Record<string, typeof Zap> = {
  Mail,
  MessageSquare,
  GitBranch,
  Ticket,
  Zap,
  Monitor,
  Globe,
  CheckCircle2,
  AlertCircle,
  Key,
  RefreshCw,
  Trash2,
  X,
  ExternalLink,
  Loader2,
  Plus,
};

function getIcon(iconName: string) {
  return ICON_MAP[iconName] || Zap;
}

export function IntegrationsTab() {
  const { organization } = useAuth();
  const {
    data: connections,
    loading,
    error,
    refetch: refreshConnections,
  } = useFetch<IntegrationConnection[]>("/enterprise/integrations");
  const [showCreate, setShowCreate] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [formData, setFormData] = useState<{
    name: string;
    provider: string;
    kind: string;
    config: Record<string, unknown>;
    auth_type: string;
  }>({
    name: "",
    provider: "",
    kind: "webhook",
    config: {},
    auth_type: "oauth2",
  });
  const [oauthState, setOauthState] = useState<{
    provider: string | null;
    authUrl: string | null;
    state: string | null;
    connectionId: string | null;
  }>({ provider: null, authUrl: null, state: null, connectionId: null });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthProvider = params.get("oauth_provider");
    const oauthCode = params.get("code");
    const oauthState = params.get("state");
    const oauthError = params.get("error");

    if (oauthProvider && oauthCode && oauthState) {
      handleOAuthCallback(oauthProvider, oauthCode, oauthState);
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (oauthError) {
      setLocalError(`OAuth error: ${oauthError}`);
    }
  }, []);

  async function handleCreate(payload: {
    name: string;
    provider: string;
    kind: string;
    config: Record<string, unknown>;
    auth_type: string;
  }) {
    setLocalError(null);
    try {
      const result = await api<IntegrationConnection>(
        "/enterprise/integrations",
        {
          method: "POST",
          body: payload,
        },
      );
      toastSuccess("Integration created", result.name);
      setShowCreate(false);
      await refreshConnections();
    } catch (err) {
      setLocalError(
        err instanceof Error ? err.message : "Failed to create integration",
      );
    }
  }

  async function handleOAuthConnect(providerId: string) {
    const provider = OAUTH_PROVIDERS.find((p) => p.id === providerId);
    if (!provider) return;

    setLocalError(null);
    try {
      const redirectUri = `${window.location.origin}/settings?tab=integrations`;
      const response = await api<{ authorization_url: string; state: string }>(
        "/enterprise/integrations/oauth/authorize",
        {
          method: "POST",
          body: {
            provider: providerId,
            redirect_uri: redirectUri,
            scopes: provider.scopes,
          },
        },
      );

      setOauthState({
        provider: providerId,
        authUrl: response.authorization_url,
        state: response.state,
        connectionId: null,
      });

      window.location.href = response.authorization_url;
    } catch (err) {
      setLocalError(
        err instanceof Error ? err.message : "Failed to start OAuth flow",
      );
    }
  }

  async function handleOAuthCallback(
    providerId: string,
    code: string,
    state: string,
  ) {
    setLocalError(null);
    try {
      const redirectUri = `${window.location.origin}/settings?tab=integrations`;
      const response = await api<{
        success: boolean;
        connection_id: string;
        detail: string;
        provider: string;
      }>("/enterprise/integrations/oauth/callback", {
        method: "POST",
        body: {
          provider: providerId,
          code,
          state,
          redirect_uri: redirectUri,
        },
      });

      if (response.success) {
        toastSuccess(`Connected to ${response.provider}`, response.detail);
        await refreshConnections();
      } else {
        setLocalError(response.detail || "OAuth callback failed");
      }
    } catch (err) {
      setLocalError(
        err instanceof Error ? err.message : "OAuth callback failed",
      );
    }
  }

  async function handleRefreshToken(connectionId: string) {
    setRefreshingId(connectionId);
    try {
      const response = await api<{ success: boolean; detail: string }>(
        `/enterprise/integrations/${connectionId}/refresh-token`,
        { method: "POST" },
      );
      toastSuccess("Token refreshed", response.detail);
    } catch (err) {
      toastError(
        "Token refresh failed",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setRefreshingId(null);
    }
  }

  async function handleDisconnect(connectionId: string) {
    if (
      !confirm(
        "Are you sure you want to disconnect this integration? This will revoke tokens and remove the connection.",
      )
    )
      return;
    try {
      await api<{ success: boolean; detail: string }>(
        `/enterprise/integrations/${connectionId}/disconnect`,
        { method: "POST" },
      );
      toastSuccess("Integration disconnected");
      await refreshConnections();
    } catch (err) {
      toastError(
        "Failed to disconnect",
        err instanceof Error ? err.message : undefined,
      );
    }
  }

  async function handleTest(connectionId: string) {
    setTestingId(connectionId);
    try {
      const result = await api<{ success: boolean; detail: string }>(
        `/enterprise/integrations/${connectionId}/test`,
        { method: "POST" },
      );
      toastSuccess(
        result.success ? "Connection successful" : "Connection failed",
        result.detail,
      );
    } catch (err) {
      toastError("Test failed", err instanceof Error ? err.message : undefined);
    } finally {
      setTestingId(null);
    }
  }

  async function handleSync(connectionId: string) {
    setSyncingId(connectionId);
    try {
      const result = await api<{
        entities_synced: number;
        sync_results: Record<string, any>;
      }>(`/enterprise/integrations/${connectionId}/sync`, { method: "POST" });
      toastSuccess(
        "Sync completed",
        `${result.entities_synced} entities synced`,
      );
    } catch (err) {
      toastError("Sync failed", err instanceof Error ? err.message : undefined);
    } finally {
      setSyncingId(null);
    }
  }

  async function handleDelete(connectionId: string) {
    if (!confirm("Are you sure you want to delete this integration?")) return;
    try {
      await api(`/enterprise/integrations/${connectionId}`, {
        method: "DELETE",
      });
      toastSuccess("Integration deleted");
      await refreshConnections();
    } catch (err) {
      toastError(
        "Failed to delete",
        err instanceof Error ? err.message : undefined,
      );
    }
  }

  const columns = [
    { key: "name", header: "Name", width: "200px" },
    { key: "provider", header: "Provider", width: "120px" },
    { key: "kind", header: "Type", width: "100px" },
    { key: "status", header: "Status", width: "100px" },
    { key: "last_sync", header: "Last Sync", width: "180px" },
    { key: "actions", header: "Actions", width: "280px" },
  ];

  if (!organization) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-ink">
            Integrations
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            Connect external services and sync data.
          </p>
        </div>
        <div className="flex gap-2">
          <EntitlementGate
            entitlementKey="integrations.max"
            required={1}
            fallback={
              <Button variant="secondary" disabled>
                <Plus className="h-4 w-4 mr-2" /> Upgrade to add integrations
              </Button>
            }
          >
            <Button
              onClick={() => setShowCreate(true)}
              disabled={!organization}
              variant="secondary"
            >
              <Plus className="h-4 w-4 mr-2" /> Add custom integration
            </Button>
          </EntitlementGate>
          <div className="flex gap-2">
            {OAUTH_PROVIDERS.map((provider) => {
              const Icon = getIcon(provider.iconName);
              return (
                <EntitlementGate
                  key={provider.id}
                  entitlementKey="integrations.max"
                  required={1}
                  fallback={
                    <Button variant="secondary" disabled>
                      <Icon className={`h-4 w-4 ${provider.color}`} />{" "}
                      {provider.name}
                    </Button>
                  }
                >
                  <Button
                    key={provider.id}
                    variant="secondary"
                    onClick={() => handleOAuthConnect(provider.id)}
                    className="flex items-center gap-2"
                    disabled={!organization}
                  >
                    <Icon className={`h-4 w-4 ${provider.color}`} />
                    {provider.name}
                  </Button>
                </EntitlementGate>
              );
            })}
          </div>
        </div>
      </div>

      {localError && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-[13px] text-danger flex items-center justify-between">
          <AlertCircle className="h-4 w-4 mr-2" />
          {localError}
          <button
            onClick={() => setLocalError(null)}
            className="ml-2 text-faint hover:text-ink"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">
          Available Providers
        </h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {OAUTH_PROVIDERS.map((provider) => {
            const existingConnection = connections?.find(
              (c: IntegrationConnection) => c.provider === provider.id,
            );
            const isConnected =
              existingConnection && existingConnection.status === "active";
            const isError =
              existingConnection && existingConnection.status === "error";
            const ProviderIcon = getIcon(provider.iconName);

            return (
              <Card
                key={provider.id}
                className={`relative ${isConnected ? "border-brand/30 bg-brand/5" : isError ? "border-danger/30 bg-danger/5" : ""}`}
              >
                <div className="p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-lg ${provider.bgColor}`}
                    >
                      <ProviderIcon className={`h-5 w-5 ${provider.color}`} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-ink">{provider.name}</p>
                      <p className="text-[12px] text-muted truncate">
                        {provider.description}
                      </p>
                    </div>
                  </div>

                  {isConnected ? (
                    <div className="space-y-2 pt-2 border-t border-line">
                      <div className="flex items-center justify-between">
                        <span className="text-[12px] text-success flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5" /> Connected
                        </span>
                        <Badge tone="success" className="text-[10px]">
                          Active
                        </Badge>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleTest(existingConnection!.id)}
                          disabled={testingId === existingConnection!.id}
                          className="flex-1"
                        >
                          {testingId === existingConnection!.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin mx-auto" />
                          ) : (
                            <Key className="h-3.5 w-3.5 mr-1 mx-auto" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            handleDisconnect(existingConnection!.id)
                          }
                          className="flex-1"
                        >
                          {syncingId === existingConnection!.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin mx-auto" />
                          ) : (
                            <RefreshCw className="h-3.5 w-3.5 mr-1 mx-auto" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            handleDisconnect(existingConnection!.id)
                          }
                          className="flex-1"
                        >
                          {refreshingId === existingConnection!.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin mx-auto" />
                          ) : (
                            <Key className="h-3.5 w-3.5 mr-1 mx-auto" />
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            handleDisconnect(existingConnection!.id)
                          }
                          className="flex-1"
                        >
                          <ExternalLink className="h-3.5 w-3.5 mx-auto" />
                        </Button>
                      </div>
                      {existingConnection!.last_sync_at && (
                        <p className="text-[11px] text-muted">
                          Last sync:{" "}
                          {formatDate(existingConnection!.last_sync_at)}
                        </p>
                      )}
                    </div>
                  ) : isError ? (
                    <div className="space-y-2 pt-2 border-t border-line">
                      <div className="flex items-center justify-between">
                        <span className="text-[12px] text-danger flex items-center gap-1">
                          <AlertCircle className="h-3.5 w-3.5" /> Connection
                          error
                        </span>
                        <Badge tone="danger" className="text-[10px]">
                          Error
                        </Badge>
                      </div>
                      {existingConnection!.error && (
                        <p className="text-[11px] text-danger">
                          {existingConnection!.error}
                        </p>
                      )}
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleTest(existingConnection!.id)}
                          disabled={testingId === existingConnection!.id}
                          className="flex-1"
                        >
                          Retry connection
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            handleDisconnect(existingConnection!.id)
                          }
                          className="flex-1"
                        >
                          Disconnect
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <EntitlementGate
                      entitlementKey="integrations.max"
                      required={1}
                      fallback={
                        <Button className="w-full" disabled>
                          <Globe className="h-4 w-4 mr-2" /> Upgrade to connect
                        </Button>
                      }
                    >
                      <Button
                        className="w-full"
                        onClick={() => handleOAuthConnect(provider.id)}
                        disabled={!organization}
                      >
                        <Globe className="h-4 w-4 mr-2" /> Connect{" "}
                        {provider.name}
                      </Button>
                    </EntitlementGate>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">
          Custom Integrations
        </h3>
        {localError && (
          <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-[13px] text-danger flex items-center justify-between">
            {localError}
            <button
              onClick={() => setLocalError(null)}
              className="ml-2 text-faint hover:text-ink"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        <Card className="overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-line">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className="px-5 py-3 text-left text-[12px] font-semibold text-muted uppercase tracking-wider"
                    style={{ width: col.width }}
                  >
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-5 py-8 text-center"
                  >
                    <Spinner />
                  </td>
                </tr>
              ) : connections?.filter(
                  (c: IntegrationConnection) => !OAUTH_PROVIDERS.some((p) => p.id === c.provider),
                ).length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-5 py-10 text-center"
                  >
                    <EmptyState
                      icon={Zap}
                      title="No custom integrations yet"
                      description="Add a webhook, API, or custom integration."
                    />
                  </td>
                </tr>
              ) : (
                connections
                  ?.filter(
                    (c: IntegrationConnection) => !OAUTH_PROVIDERS.some((p) => p.id === c.provider),
                  )
                  .map((conn: IntegrationConnection) => {
                    return (
                      <tr
                        key={conn.id}
                        className="border-b border-line hover:bg-brand/5"
                      >
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
                              {conn.provider === "slack" ? (
                                <MessageSquare className="h-5 w-5" />
                              ) : conn.provider === "github" ? (
                                <GitBranch className="h-5 w-5" />
                              ) : conn.provider === "google" ? (
                                <Mail className="h-5 w-5" />
                              ) : conn.provider === "microsoft" ? (
                                <Monitor className="h-5 w-5" />
                              ) : conn.provider === "jira" ? (
                                <Ticket className="h-5 w-5" />
                              ) : (
                                <Zap className="h-5 w-5" />
                              )}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="font-medium text-ink truncate">
                                {conn.name}
                              </p>
                              <p className="text-[12px] text-muted truncate">
                                {conn.provider} · {conn.kind}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <Badge
                            tone={
                              conn.status === "active"
                                ? "success"
                                : conn.status === "error"
                                  ? "danger"
                                  : "warning"
                            }
                          >
                            {conn.status}
                          </Badge>
                        </td>
                        <td className="px-5 py-4 text-[13px] text-muted">
                          {conn.last_sync_at
                            ? formatDate(conn.last_sync_at)
                            : "Never"}
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleTest(conn.id)}
                              disabled={testingId === conn.id}
                            >
                              {testingId === conn.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <>
                                  <Key className="h-3.5 w-3.5 mr-1" /> Test
                                </>
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleSync(conn.id)}
                              disabled={syncingId === conn.id}
                            >
                              {syncingId === conn.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                              ) : (
                                <>
                                  <RefreshCw className="h-3.5 w-3.5 mr-1" />{" "}
                                  Sync
                                </>
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              onClick={() => handleDelete(conn.id)}
                              disabled={
                                syncingId === conn.id || testingId === conn.id
                              }
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
              )}
            </tbody>
          </table>
        </Card>

        {showCreate && (
          <Modal
            open={showCreate}
            onClose={() => setShowCreate(false)}
            title="Add Custom Integration"
            footer={
              <div className="flex justify-end gap-2">
                <Button
                  variant="secondary"
                  onClick={() => setShowCreate(false)}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => handleCreate(formData)}
                  loading={loading}
                >
                  Create
                </Button>
              </div>
            }
          >
            <div className="space-y-4">
              <Input
                label="Name"
                value={formData?.name || ""}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="My Webhook"
                required
              />
              <Input
                label="Provider"
                value={formData?.provider || ""}
                onChange={(e) =>
                  setFormData({ ...formData, provider: e.target.value })
                }
                placeholder="custom, zapier, make, etc."
                required
              />
              <Input
                label="Type"
                value={formData?.kind || "webhook"}
                onChange={(e) =>
                  setFormData({ ...formData, kind: e.target.value })
                }
                placeholder="webhook, api, app, datasource"
              />
              <Textarea
                label="Configuration (JSON)"
                value={JSON.stringify(formData?.config || {}, null, 2)}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: JSON.parse(e.target.value || "{}"),
                  })
                }
                placeholder='{"url": "https://...", "events": ["message", "reaction"]}'
                rows={4}
              />
              <Input
                label="Auth Type"
                value={formData?.auth_type || "oauth2"}
                onChange={(e) =>
                  setFormData({ ...formData, auth_type: e.target.value })
                }
                placeholder="oauth2, api_key, basic, saml, oidc"
              />
            </div>
          </Modal>
        )}
      </div>
    </div>
  );
}
