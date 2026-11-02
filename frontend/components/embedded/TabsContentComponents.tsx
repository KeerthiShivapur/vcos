"use client";

import { Monitor, Palette, Shield, Key, Copy, Globe, Code, Zap, Layers, Settings, HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { Label } from "@/components/ui/Label";

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