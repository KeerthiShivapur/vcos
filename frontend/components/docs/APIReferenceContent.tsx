"use client";

import { Globe, Code } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

export function APIReferenceContent() {
  return (
    <>
      <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">API Reference</h2>
      <Tabs defaultValue="rest" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="rest">REST API</TabsTrigger>
          <TabsTrigger value="webhooks">
            <Globe className="w-4 h-4 mr-2" />
            Webhooks
          </TabsTrigger>
          <TabsTrigger value="sdk">
            <Code className="w-4 h-4 mr-2" />
            SDK
          </TabsTrigger>
        </TabsList>

        <TabsContent value="rest">
          <h3 className="font-semibold text-slate-900 dark:text-white mb-4">Dashboard Endpoints</h3>
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
              <p className="text-sm text-slate-600 dark:text-slate-400">Delete dashboard configuration</p>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="webhooks">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            Receive real-time notifications for dashboard events.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// Webhook events
POST /api/v1/embedded-analytics/webhooks
{
  "url": "https://your-app.com/webhooks/vcos",
  "events": [
    "dashboard.loaded",
    "dashboard.filter_changed",
    "dashboard.exported",
    "dashboard.error"
  ]
}`}</code></pre>
        </TabsContent>

        <TabsContent value="sdk">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            JavaScript SDK for programmatic control.
          </p>
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
        </TabsContent>
      </Tabs>
    </>
  );
}