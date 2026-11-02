"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

export function ExamplesContent() {
  return (
    <>
      <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">Examples</h2>
      <Tabs defaultValue="react" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="react">React</TabsTrigger>
          <TabsTrigger value="vue">Vue</TabsTrigger>
          <TabsTrigger value="vanilla">Vanilla JS</TabsTrigger>
          <TabsTrigger value="nextjs">Next.js</TabsTrigger>
          <TabsTrigger value="wordpress">WordPress</TabsTrigger>
          <TabsTrigger value="shopify">Shopify</TabsTrigger>
        </TabsList>

        <TabsContent value="react">
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`import { VCOSAnalyticsSDK } from '@vcos/embedded-analytics';

function EmbeddedDashboard({ token, dashboardId }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const sdk = new VCOSAnalyticsSDK('https://vcos.io');
    
    const cleanup = sdk.createIframeEmbed(dashboardId, token, {
      containerId: containerRef.current.id,
      onLoad: () => console.log('Dashboard loaded!'),
      onError: (err) => console.error(err)
    );

    return () => cleanup?.();
  }, [token, dashboardId]);

  return <div ref={containerRef} id="dashboard-container" className="w-full h-96" />;
}

// Usage
<EmbeddedDashboard 
  token="EMBED_TOKEN" 
  dashboardId="customer-health" 
/>`}</code></pre>
        </TabsContent>

        <TabsContent value="vue">
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`<template>
  <div ref="container" class="w-full h-96" id="dashboard-container"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { VCOSAnalyticsSDK } from '@vcos/embedded-analytics';

const props = defineProps(['token', 'dashboardId']);
const container = ref<HTMLElement>();
let cleanup: Function | null = null;

onMounted(async () => {
  const sdk = new VCOSAnalyticsSDK('https://vcos.io');
  cleanup = await sdk.createIframeEmbed(props.dashboardId, props.token, {
    containerId: container.value!.id,
    onLoad: () => console.log('Dashboard loaded!'),
    onError: (err) => console.error(err)
  });
});

onUnmounted(() => {
  cleanup?.();
});
</script>`}</code></pre>
        </TabsContent>

        <TabsContent value="vanilla">
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

        <TabsContent value="nextjs">
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`import { VCOSAnalyticsSDK } from '@vcos/embedded-analytics';

export default function DashboardPage({ params }) {
  const [token, setToken] = useState('');

  useEffect(() => {
    async function fetchToken() {
      const res = await fetch('/api/embed-token', {
        method: 'POST',
        body: JSON.stringify({ dashboardId: params.id })
      });
      const data = await res.json();
      setToken(data.token);
    }
    fetchToken();
  }, [params.id]);

  return (
    <div id="dashboard-container" className="w-full h-96">
      {token && (
        <script
          dangerouslySetInnerHTML={{
            __html: \`
              const sdk = new VCOSAnalyticsSDK('https://vcos.io');
              sdk.createIframeEmbed('\${params.id}', '\${token}', {
                containerId: 'dashboard-container',
                onLoad: () => console.log('Loaded!')
              });
            \`
          }} />
      )}
    </div>
  );
}`}</code></pre>
        </TabsContent>

        <TabsContent value="wordpress">
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// WordPress shortcode
function vcos_embed_shortcode($atts) {
  $atts = shortcode_atts([
    'dashboard_id' => '',
    'token' => '',
    'width' => '100%',
    'height' => '600px'
  ], $atts);

  return '<div id="vcos-dashboard-' . esc_attr($atts['dashboard_id']) . '" 
    style="width:' . esc_attr($atts['width']) . ';height:' . esc_attr($atts['height']) . '"></div>
    <script>
      var sdk = new VCOSAnalyticsSDK("https://vcos.io");
      sdk.createIframeEmbed("' . esc_attr($atts['dashboard_id']) . '", "' . esc_attr($atts['token']) . '", {
        containerId: "vcos-dashboard-' . esc_attr($atts['dashboard_id']) . '",
        onLoad: () => console.log("Loaded!")
      });
    </script>';

add_shortcode('vcos_embed', 'vcos_embed_shortcode');

// Usage: [vcos_embed dashboard_id="customer-health" token="EMBED_TOKEN"]`}</code></pre>
        </TabsContent>

        <TabsContent value="shopify">
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`<!-- Shopify theme.liquid -->
<script src="https://cdn.jsdelivr.net/npm/@vcos/embedded-analytics@latest/dist/vcos-embedded-analytics.umd.min.js"></script>

<div id="dashboard-container" style="width: 100%; height: 600px;"></div>

<script>
  window.addEventListener('load', function() {
    const sdk = new VCOSAnalyticsSDK('https://vcos.io');
    sdk.createIframeEmbed('{{ section.settings.dashboard_id }}', '{{ section.settings.embed_token }}', {
      containerId: 'dashboard-container',
      onLoad: () => console.log('Dashboard loaded!')
    });
  });
</script>`}</code></pre>
        </TabsContent>
      </Tabs>
    </>
  );
}