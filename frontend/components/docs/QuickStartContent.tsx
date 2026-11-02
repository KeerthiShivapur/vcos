"use client";

import { Zap, Palette, Code, Monitor, Globe, CheckCircle2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

export function QuickStartContent() {
  return (
    <>
      <header>
        <h1 className="text-4xl font-bold text-slate-900 dark:text-white mb-4">Quick Start</h1>
        <p className="text-lg text-slate-600 dark:text-slate-300 mb-8 max-w-3xl">
          Embed VCOS analytics dashboards in your application in minutes. 
          This guide walks you through creating a dashboard, generating a token, and embedding it in your app.
        </p>

        <Card className="bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-800">
          <div className="flex items-start gap-4 p-6">
            <Zap className="w-6 h-6 text-indigo-600 dark:text-indigo-400 mt-0.5" />
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white mb-2">Prerequisites</h3>
              <ul className="space-y-1 text-sm text-slate-600 dark:text-slate-300">
                <li>• VCOS account with admin permissions</li>
                <li>• Access to the target dashboard</li>
                <li>• Ability to add iframe/script tags to your app</li>
              </ul>
            </div>
          </div>
        </Card>

        <section className="space-y-4">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">1</span>
            Create an Embedded Dashboard
          </h2>
          <p className="text-slate-600 dark:text-slate-300">
            First, create an embedded dashboard configuration in VCOS. This defines which dashboard to embed, 
            the embedding mode, allowed origins, and security settings.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`POST /api/v1/embedded-analytics/dashboards
{
  "name": "Customer Dashboard",
  "description": "Customer health metrics for external partners",
  "dashboard_id": "customer-health",
  "embedding_mode": "iframe",
  "allowed_origins": ["https://app.example.com"],
  "theme": "light",
  "refresh_interval": 300
}`}</code></pre>
        </section>

        <section className="space-y-4 mt-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">2</span>
            Generate an Embed Token
          </h2>
          <p className="text-slate-600 dark:text-slate-300">
            Generate a secure, short-lived token for the embed. Tokens can be scoped to specific users, 
            organizations, and dashboards with configurable expiration.
          </p>
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

        <section className="space-y-4 mt-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">3</span>
            Embed in Your Application
          </h2>
          <p className="text-slate-600 dark:text-slate-300">
            Choose your embedding method based on your application framework.
          </p>

          <Tabs defaultValue="iframe" className="space-y-4">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="iframe">Iframe</TabsTrigger>
              <TabsTrigger value="web-component">
                <Palette className="w-4 h-4 mr-2" />
                Web Component
              </TabsTrigger>
              <TabsTrigger value="javascript-sdk">
                <Code className="w-4 h-4 mr-2" />
                JavaScript SDK
              </TabsTrigger>
              <TabsTrigger value="vanilla">
                <Monitor className="w-4 h-4 mr-2" />
                Vanilla JS
              </TabsTrigger>
            </TabsList>

            <TabsContent value="iframe">
              <p className="text-slate-600 dark:text-slate-300 mb-4">
                The simplest embedding method. Just add an iframe with the embed URL and token.
              </p>
              <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`<iframe 
  src="https://vcos.io/embed/CUSTOMER_HEALTH_DASHBOARD?token=EMBED_TOKEN"
  width="100%"
  height="600px"
  frameborder="0"
  allowfullscreen>
</iframe>`}</code></pre>
            </TabsContent>

            <TabsContent value="web-component">
              <p className="text-slate-600 dark:text-slate-300 mb-4">
                Use the native web component for seamless integration with any framework.
              </p>
              <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`<!-- Include SDK -->
<script src="https://cdn.jsdelivr.net/npm/@vcos/embedded-analytics@latest/dist/vcos-embedded-analytics.umd.min.js"></script>

<vcos-embedded-dashboard
  dashboard-id="customer-health"
  token="EMBED_TOKEN"
  width="100%"
  height="600px">
</vcos-embedded-dashboard>`}</code></pre>
            </TabsContent>

            <TabsContent value="javascript-sdk">
              <p className="text-slate-600 dark:text-slate-300 mb-4">
                Use the JavaScript SDK for full control over the embed lifecycle.
              </p>
              <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`import { VCOSAnalyticsSDK } from '@vcos/embedded-analytics';

const sdk = new VCOSAnalyticsSDK('https://vcos.io');

async function loadDashboard() {
  const { token } = await sdk.generateToken({
    userId: 'user_123',
    email: 'user@example.com',
    name: 'John Doe',
    orgId: 'org_456',
    dashboardId: 'customer-health'
  });
  
  const cleanup = sdk.createIframeEmbed('customer-health', token, {
    containerId: 'dashboard-container',
    onLoad: () => console.log('Dashboard loaded!'),
    onError: (err) => console.error(err)
  });
}

loadDashboard();`}</code></pre>
            </TabsContent>

            <TabsContent value="vanilla">
              <p className="text-slate-600 dark:text-slate-300 mb-4">
                Plain JavaScript without any framework dependencies.
              </p>
              <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`<!-- Include SDK -->
<script src="https://cdn.jsdelivr.net/npm/@vcos/embedded-analytics@latest/dist/vcos-embedded-analytics.umd.min.js"></script>

<div id="dashboard-container"></div>

<script>
  const sdk = new VCOSAnalyticsSDK('https://vcos.io');

  async function loadDashboard() {
    const { token } = await sdk.generateToken({
      userId: 'user_123',
      email: 'user@example.com',
      name: 'John Doe',
      orgId: 'org_456',
      dashboardId: 'embed-abc123'
    });
    
    const cleanup = sdk.createIframeEmbed('embed-abc123', token, {
      containerId: 'dashboard-container',
      onLoad: () => console.log('Dashboard loaded!'),
      onError: (err) => console.error(err)
    });
  }

  loadDashboard();
</script>`}</code></pre>
            </TabsContent>
          </Tabs>
        </section>

        <section className="space-y-4 mt-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <span className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold">4</span>
            Complete HTML Example
          </h2>
          <p className="text-slate-600 dark:text-slate-300">
            A complete, self-contained HTML file you can save and open in a browser.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Embedded VCOS Dashboard</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; }
    .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
    header { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .embed-container { border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    iframe { width: 100%; height: 700px; border: none; border-radius: 8px; }
    @media (max-width: 768px) { .container { padding: 10px; } iframe { height: 500px; } }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Customer Analytics Dashboard</h1>
      <p>Embedded VCOS Analytics for Partner Portal</p>
    </header>
    <div class="embed-container">
      <iframe id="vcos-embed" src="https://vcos.io/embed/EMBED_ID?token=YOUR_TOKEN" allowfullscreen></iframe>
    </div>
    <script>
      window.addEventListener('message', function(event) {
        if (event.data.type === 'vcos:resize') {
          document.getElementById('vcos-embed').style.height = event.data.height + 'px';
        }
      });
    </script>
  </body>
</html>`}</code></pre>
        </section>
      </header>
    </>
  );
}