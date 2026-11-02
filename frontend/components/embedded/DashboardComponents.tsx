"use client";

import { useState } from "react";
import { Plus, Edit, Trash2, Eye, Copy, ExternalLink, Box, Monitor, Smartphone, Tablet, Palette, Shield, Key, Copy as CopyIcon, Globe, Code, Zap, Layers, Settings, HelpCircle } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/DropdownMenu";
import { Modal } from "@/components/ui/Modal";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { Label } from "@/components/ui/Label";

interface EmbeddedDashboard {
  id: string;
  name: string;
  description?: string;
  dashboard_id?: string;
  embedding_mode: "iframe" | "web_component" | "javascript_sdk";
  allowed_origins: string[];
  theme: string;
  branding?: {
    primary_color?: string;
    logo_url?: string;
    company_name?: string;
  };
  features: {
    fullscreen: boolean;
    export: boolean;
    share: boolean;
    drill_down: boolean;
    filtering: boolean;
  };
  dimensions: {
    width: string;
    height: string;
    min_height: string;
    responsive: boolean;
  };
  allowed_referrers: string[];
  csp_policy?: string;
  created_at: string;
  updated_at: string;
}

interface CreateDashboardModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: Partial<EmbeddedDashboard>) => Promise<void>;
  loading?: boolean;
  initialData?: Partial<EmbeddedDashboard>;
}

export function CreateDashboardModal({ isOpen, onClose, onSubmit, loading, initialData }: CreateDashboardModalProps) {
  const [formData, setFormData] = useState<Partial<EmbeddedDashboard>>({
    name: "",
    description: "",
    dashboard_id: "",
    embedding_mode: "iframe",
    allowed_origins: [],
    theme: "light",
    branding: {},
    features: {
      fullscreen: true,
      export: true,
      share: true,
      drill_down: true,
      filtering: true,
    },
    dimensions: {
      width: "100%",
      height: "600px",
      min_height: "400px",
      responsive: true,
    },
    allowed_referrers: [],
    csp_policy: "",
  });

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={initialData ? "Edit Dashboard" : "Create Dashboard"}>
      <form onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit(formData);
      }} className="space-y-4">
        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" value={formData.name || ""} onChange={e => setFormData({...formData, name: e.target.value})} required />
        </div>
        <div>
          <Label htmlFor="description">Description</Label>
          <Textarea id="description" value={formData.description || ""} onChange={e => setFormData({...formData, description: e.target.value})} />
        </div>
        <div>
          <Label htmlFor="dashboard_id">Dashboard ID</Label>
          <Input id="dashboard_id" value={formData.dashboard_id || ""} onChange={e => setFormData({...formData, dashboard_id: e.target.value})} />
        </div>
        <div className="flex gap-4">
          <div className="flex-1">
            <Label htmlFor="embedding_mode">Embedding Mode</Label>
            <Select value={formData.embedding_mode || "iframe"} onValueChange={v => setFormData({...formData, embedding_mode: v as any})}>
              <option value="iframe">Iframe</option>
              <option value="web_component">Web Component</option>
              <option value="javascript_sdk">JavaScript SDK</option>
            </Select>
          </div>
          <div className="flex-1">
            <Label htmlFor="theme">Theme</Label>
            <Select value={formData.theme || "light"} onValueChange={v => setFormData({...formData, theme: v})}>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-4">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={loading}>{loading ? "Saving..." : initialData ? "Update" : "Create"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function AccessDenied() {
  return <ErrorState
    title="Access Denied"
    message="You don't have permission to view embedded analytics dashboards."
    action={{ label: "Go Home", onClick: () => window.location.href = "/app" }}
  />;
}

export function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

export function ErrorStateComponent({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <ErrorState
      title="Failed to load dashboards"
      message={error}
      action={{ label: "Retry", onClick: onRetry }}
    />
  );
}

export function EmptyStateComponent({ onCreate, disabled }: { onCreate: () => void; disabled: boolean }) {
  return (
    <EmptyState
      icon={<Box className="h-12 w-12 text-muted" />}
      title="No dashboards yet"
      description="Create your first embedded dashboard to get started"
      action={{
        label: "Create Dashboard",
        onClick: onCreate,
        disabled,
      }}
    />
  );
}

interface DashboardCardProps {
  dashboard: EmbeddedDashboard;
  onEdit: () => void;
  onViewEmbedCode: () => void;
  onPreview: () => void;
  onCopyId: () => void;
  onDelete: () => void;
}

export function DashboardCard({ dashboard, onEdit, onViewEmbedCode, onPreview, onCopyId, onDelete }: DashboardCardProps) {
  return (
    <Card key={dashboard.id} className="relative">
      <div className="flex items-start justify-between p-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
              <Box className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white truncate">{dashboard.name}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 truncate max-w-md">
                {dashboard.description || "No description"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {dashboard.embedding_mode === "iframe" ? "Iframe" : 
               dashboard.embedding_mode === "web_component" ? "Web Component" : "JS SDK"}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {dashboard.dimensions.width} × {dashboard.dimensions.height}
            </Badge>
          </div>
        </div>
        <div className="border-t border-slate-200 dark:border-slate-700 px-4 py-3">
          <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
            <span>Updated {new Date(dashboard.updated_at).toLocaleDateString()}</span>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={onViewEmbedCode}>
                <ExternalLink className="w-4 h-4 mr-1" />
                Embed Code
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                    <Settings className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem onClick={onEdit}>
                    <Edit className="w-4 h-4 mr-2" />
                    Edit
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onViewEmbedCode}>
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Embed Code
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onPreview} className="text-slate-600 dark:text-slate-400">
                    <Eye className="w-4 h-4 mr-2" />
                    Preview
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onCopyId} className="text-slate-600 dark:text-slate-400">
                    <CopyIcon className="w-4 h-4 mr-2" />
                    Copy ID
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onDelete} className="text-red-600 dark:text-red-400">
                    <Trash2 className="w-4 h-4 mr-2" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
    </Card>
  );
}

interface DashboardsContentProps {
  filteredDashboards: EmbeddedDashboard[];
  loading: boolean;
  error: string | null;
  canManage: boolean;
  onRefresh: () => void;
  onCreate: () => void;
  onEdit: (dashboard: EmbeddedDashboard) => void;
  onViewEmbedCode: (dashboard: EmbeddedDashboard) => void;
  onPreview: (dashboard: EmbeddedDashboard) => void;
  onCopyId: (id: string) => void;
  onDelete: (dashboard: EmbeddedDashboard) => void;
}

export function DashboardsContent({ 
  filteredDashboards, 
  loading, 
  error, 
  canManage,
  onRefresh,
  onCreate,
  onEdit,
  onViewEmbedCode,
  onPreview,
  onCopyId,
  onDelete
}: DashboardsContentProps) {
  if (loading) return <LoadingState />;
  if (error) return <ErrorStateComponent error={error} onRetry={onRefresh} />;
  if (filteredDashboards.length === 0) return <EmptyStateComponent onCreate={onCreate} disabled={!canManage} />;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {filteredDashboards.map(dashboard => (
        <DashboardCard
          key={dashboard.id}
          dashboard={dashboard}
          onEdit={() => onEdit(dashboard)}
          onViewEmbedCode={() => onViewEmbedCode(dashboard)}
          onPreview={() => onPreview(dashboard)}
          onCopyId={() => onCopyId(dashboard.id)}
          onDelete={() => onDelete(dashboard)}
        />
      ))}
    </div>
  );
}

export function BrandingContent() {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <div className="p-6">
            <h3 className="font-semibold text-lg mb-4">Primary Color</h3>
            <div className="flex items-center gap-4">
              <input
                type="color"
                defaultValue="#3b82f6"
                className="w-12 h-12 rounded-lg border border-slate-200 dark:border-slate-600 cursor-pointer"
              />
              <div>
                <p className="font-medium">#3b82f6</p>
                <p className="text-sm text-muted">Primary brand color</p>
              </div>
            </div>
          </div>
        </Card>
        <Card>
          <div className="p-6">
            <h3 className="font-semibold text-lg mb-4">Logo</h3>
            <div className="aspect-square bg-slate-100 dark:bg-slate-800 rounded-lg flex items-center justify-center mb-4">
              <Monitor className="h-12 w-12 text-muted" />
            </div>
            <Button variant="outline" className="w-full">Upload Logo</Button>
          </div>
        </Card>
        <Card>
          <div className="p-6">
            <h3 className="font-semibold text-lg mb-4">Company Name</h3>
            <Input placeholder="Your Company Name" defaultValue="VCOS Analytics" />
          </div>
        </Card>
      </div>
    </div>
  );
}

export function SSOContent() {
  return (
    <Card className="max-w-2xl">
      <div className="p-6 space-y-6">
        <div>
          <h3 className="font-semibold text-lg mb-2">SAML 2.0 Configuration</h3>
          <p className="text-sm text-muted">Configure SAML 2.0 for single sign-on</p>
        </div>
        <div className="space-y-4">
          <div>
            <Label htmlFor="sso_entity_id">Entity ID</Label>
            <Input id="sso_entity_id" placeholder="https://your-app.com/saml/metadata" />
          </div>
          <div>
            <Label htmlFor="sso_acs_url">Assertion Consumer Service URL</Label>
            <Input id="sso_acs_url" placeholder="https://your-app.com/saml/acs" />
          </div>
          <div>
            <Label htmlFor="sso_certificate">X.509 Certificate</Label>
            <Textarea placeholder="Paste your X.509 certificate here..." rows={4} />
          </div>
        </div>
        <Button>Save SAML Configuration</Button>
      </div>
    </Card>
  );
}

export function APIContent() {
  return (
    <div className="prose prose-slate dark:prose-invert max-w-none">
      <h2 className="text-2xl font-bold mb-6">Embedded Analytics API Reference</h2>
      
      <section className="mb-8">
        <h3 className="text-xl font-semibold mb-4">Authentication</h3>
        <p className="mb-4">All API requests require authentication via Bearer token in the Authorization header.</p>
        <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`Authorization: Bearer YOUR_API_KEY`}</code></pre>
      </section>

      <section className="mb-8">
        <h3 className="text-xl font-semibold mb-4">Dashboard Endpoints</h3>
        <div className="space-y-4">
          <div className="bg-slate-50 dark:bg-slate-800 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Code className="w-4 h-4 text-indigo-600" />
              <span className="font-medium text-indigo-600">POST</span>
              <span className="font-mono text-sm text-slate-600">/api/v1/embedded-analytics/dashboards</span>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Create a new embedded dashboard configuration</p>
          </div>
          <div className="bg-slate-50 dark:bg-slate-800 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Code className="w-4 h-4 text-indigo-600" />
              <span className="font-medium text-indigo-600">GET</span>
              <span className="font-mono text-sm text-slate-600">/api/v1/embedded-analytics/dashboards/:id</span>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Get dashboard configuration</p>
          </div>
          <div className="bg-slate-50 dark:bg-slate-800 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Code className="w-4 h-4 text-indigo-600" />
              <span className="font-medium text-indigo-600">PUT</span>
              <span className="font-mono text-sm text-slate-600">/api/v1/embedded-analytics/dashboards/:id</span>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Update dashboard configuration</p>
          </div>
          <div className="bg-slate-50 dark:bg-slate-800 p-4 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Code className="w-4 h-4 text-indigo-600" />
              <span className="font-medium text-indigo-600">DELETE</span>
              <span className="font-mono text-sm text-slate-600">/api/v1/embedded-analytics/dashboards/:id</span>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">Delete a dashboard</p>
          </div>
        </div>
      </section>

      <section className="mb-8">
        <h3 className="text-xl font-semibold mb-4">Token Generation</h3>
        <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`POST /api/v1/embedded-analytics/tokens
{
  "user_id": "user_123",
  "email": "user@example.com",
  "name": "John Doe",
  "org_id": "org_456",
  "dashboard_id": "customer-health",
  "expires_in": 3600
}`}</code></pre>
      </section>

      <section className="mb-8">
        <h3 className="text-xl font-semibold mb-4">Embed Code Generation</h3>
        <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`POST /api/v1/embedded-analytics/dashboards/:id/embed-code
{
  "mode": "iframe",
  "width": "100%",
  "height": "600px"
}`}</code></pre>
      </section>

      <section className="mb-8">
        <h3 className="text-xl font-semibold mb-4">Webhooks</h3>
        <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`POST /api/v1/embedded-analytics/webhooks
{
  "url": "https://your-app.com/webhooks/vcos",
  "events": [
    "dashboard.loaded",
    "dashboard.filter_changed",
    "dashboard.exported",
    "dashboard.error"
  ]
}`}</code></pre>
      </section>

      <section className="mb-8">
        <h3 className="text-xl font-semibold mb-4">JavaScript SDK</h3>
        <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// Initialize SDK
const sdk = new VCOSAnalyticsSDK('https://vcos.io', {
  apiKey: 'your-api-key'
});

// Generate embed token
const { token } = await sdk.generateToken({
  userId: 'user_123',
  dashboardId: 'customer-health',
  expiresIn: 3600
});

// Create iframe embed
const cleanup = sdk.createIframeEmbed('customer-health', token, {
  containerId: 'dashboard-container',
  onLoad: () => console.log('Loaded!'),
  onError: (err) => console.error(err)
});

// Listen to events
sdk.on('dashboard:load', (data) => { /* ... */ });`}</code></pre>
      </section>
    </div>
  );
}