"use client";

import { Palette, Code, Monitor } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

export function EmbeddingContent() {
  return (
    <>
      <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">Embedding Methods</h2>
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
    </>
  );
}