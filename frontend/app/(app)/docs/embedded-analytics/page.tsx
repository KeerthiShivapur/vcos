"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Menu, X, Search, Sun, Moon, Github, Zap, Code, ArrowUpRight, Layers, Shield, Palette, Terminal, Monitor, Globe, CheckCircle2, Palette as PaletteIcon, ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { ScrollArea } from "@/components/ui/ScrollArea";
import { Separator } from "@/components/ui/Separator";

const navItems = [
  { id: "quick-start", label: "Quick Start", iconName: "Zap", children: [] },
  { id: "embedding", label: "Embedding Methods", iconName: "Layers", children: [
    { id: "iframe", label: "Iframe Embedding" },
    { id: "web-component", label: "Web Component" },
    { id: "javascript-sdk", label: "JavaScript SDK" },
  ]},
  { id: "authentication", label: "Authentication", iconName: "Shield", children: [
    { id: "token-auth", label: "Token Authentication" },
    { id: "jwt", label: "JWT Tokens" },
    { id: "api-keys", label: "API Keys" },
  ]},
  { id: "customization", label: "Customization", iconName: "Palette", children: [
    { id: "theming", label: "Theming" },
    { id: "white-labeling", label: "White Labeling" },
    { id: "custom-events", label: "Custom Events" },
  ]},
  { id: "api-reference", label: "API Reference", iconName: "Code", children: [
    { id: "rest-api", label: "REST API" },
    { id: "webhooks", label: "Webhooks" },
    { id: "sdk", label: "SDK Reference" },
  ]},
  { id: "examples", label: "Examples", iconName: "Terminal", children: [
    { id: "react", label: "React Integration" },
    { id: "vue", label: "Vue Integration" },
    { id: "vanilla", label: "Vanilla JS" },
    { id: "nextjs", label: "Next.js" },
    { id: "wordpress", label: "WordPress" },
    { id: "shopify", label: "Shopify" },
  ]},
];

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  Zap, Layers, Shield, Palette, Code, Terminal
};

function EmbeddedAnalyticsDocsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState("quick-start");

  useEffect(() => {
    const savedTheme = (localStorage.getItem("docs-theme") as "light" | "dark") || "light";
    setTheme(savedTheme);
    document.documentElement.classList.toggle("dark", savedTheme === "dark");
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === "light" ? "dark" : "light";
    setTheme(newTheme);
    localStorage.setItem("docs-theme", newTheme);
    document.documentElement.classList.toggle("dark", newTheme === "dark");
  };

  const filteredNav = navItems.map(group => ({
    ...group,
    children: group.children.filter(child => 
      child.label.toLowerCase().includes(searchQuery.toLowerCase())
    )
  })).filter(group => group.children.length > 0);

  const navigate = (id: string) => {
    setActiveSection(id);
    if (window.innerWidth < 1024) setSidebarOpen(false);
  };

  // Mobile Menu Button
  const MobileMenuButton = () => (
    <button
      className="fixed top-4 left-4 z-50 lg:hidden p-2 rounded-lg bg-white dark:bg-slate-800 shadow-lg border border-slate-200 dark:border-slate-700"
      onClick={() => setSidebarOpen(!sidebarOpen)}
      aria-label="Toggle menu"
    >
      {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
    </button>
  );

  // Sidebar
  const Sidebar = () => (
    <aside className={`${sidebarOpen ? "translate-x-0" : "-translate-x-full"} fixed inset-y-0 left-0 z-40 w-72 lg:translate-x-0 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-transform duration-300 ease-in-out`}>
      <div className="flex flex-col h-full">
        <div className="p-6 border-b border-slate-200 dark:border-slate-800">
          <Link href="/docs/embedded-analytics" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-xl text-slate-900 dark:text-white">VCOS Analytics</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">Embedded Analytics Docs</p>
            </div>
          </Link>
          <div className="mt-4 flex items-center gap-2">
            <button
              onClick={toggleTheme}
              className="flex-1 px-3 py-2 text-sm font-medium rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              {theme === "light" ? (
                <> <Moon className="w-4 h-4 mr-1" /> Dark </>
              ) : (
                <> <Sun className="w-4 h-4 mr-1" /> Light </>
              )}
            </button>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="p-4 border-b border-slate-200 dark:border-slate-800">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search docs..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
            />
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-6">
          {filteredNav.map(group => {
            const IconComponent = iconMap[group.iconName];
            return (
              <div key={group.id}>
                <div className="flex items-center gap-2 px-2 py-1 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  <IconComponent className="w-4 h-4" />
                  {group.label}
                </div>
                <ul className="space-y-1 mt-1">
                  {group.children.map(item => (
                    <li key={item.id}>
                      <button
                        onClick={() => navigate(item.id)}
                        className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                          activeSection === item.id
                            ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-medium"
                            : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                        }`}
                      >
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800">
          <div className="flex flex-col gap-2">
            <Link href="https://github.com/vcos" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 px-3 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">
              <Github className="w-4 h-4" />
              <span>GitHub</span>
            </Link>
            <Link href="/app/embedded-analytics" className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
              <Zap className="w-4 h-4 mr-1" />
              Try Live Demo
            </Link>
          </div>
        </div>
      </div>
    </aside>
  );

  // Header
  const Header = () => (
    <header className="sticky top-0 z-30 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border-b border-slate-200 dark:border-slate-800">
      <div className="max-w-5xl mx-auto px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Embedded Analytics</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Embed VCOS analytics dashboards in your application</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => setActiveSection("quick-start")}>
              <Code className="w-4 h-4 mr-2" />
              Documentation
            </Button>
            <Link href="/app/embedded-analytics" className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
              <Zap className="w-4 h-4 mr-1" />
              Try Live Demo
            </Link>
          </div>
        </div>
      </div>
    </header>
  );

  // QuickStartContent
  const QuickStartContent = () => (
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

  // EmbeddingContent
  const EmbeddingContent = () => (
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

  // AuthenticationContent
  const AuthenticationContent = () => (
    <>
      <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">Authentication</h2>
      <Tabs defaultValue="token" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="token">Token Auth</TabsTrigger>
          <TabsTrigger value="jwt">JWT</TabsTrigger>
          <TabsTrigger value="api-key">API Keys</TabsTrigger>
        </TabsList>

        <TabsContent value="token">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            Short-lived tokens for secure embedding. Tokens expire automatically and can be refreshed.
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
        </TabsContent>

        <TabsContent value="jwt">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            JWT tokens for stateless authentication with custom claims.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// Generate JWT
const jwt = require('jsonwebtoken');

const token = jwt.sign(
  {
    sub: 'user_123',
    email: 'user@example.com',
    dashboard: 'customer-health',
    permissions: ['read', 'export']
  },
  process.env.JWT_SECRET,
  { expiresIn: '1h' }
);

// Use in embed URL
const embedUrl = \`https://vcos.io/embed/customer-health?token=\${token}\`;`}</code></pre>
        </TabsContent>

        <TabsContent value="api-key">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            Long-lived API keys for server-to-server communication.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// Create API key
POST /api/v1/embedded-analytics/api-keys
{
  "name": "Production Embed",
  "permissions": ["embed", "read"],
  "rate_limit": 1000
}

// Use API key
Authorization: Bearer ak_live_abc123`}</code></pre>
        </TabsContent>
      </Tabs>
    </>
  );

  // CustomizationContent
  const CustomizationContent = () => (
    <>
      <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">Customization</h2>
      <Tabs defaultValue="theming" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="theming">Theming</TabsTrigger>
          <TabsTrigger value="white-labeling">
            <Palette className="w-4 h-4 mr-2" />
            White Labeling
          </TabsTrigger>
          <TabsTrigger value="events">
            <Zap className="w-4 h-4 mr-2" />
            Custom Events
          </TabsTrigger>
        </TabsList>

        <TabsContent value="theming">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            Customize colors, fonts, and spacing to match your brand.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// Theme configuration
const theme = {
  colors: {
    primary: '#3b82f6',
    background: '#ffffff',
    surface: '#f8fafc',
    text: '#1e293b',
    border: '#e2e8f0'
  },
  fonts: {
    heading: 'Inter, sans-serif',
    body: 'Inter, sans-serif'
  },
  borderRadius: '8px',
  spacing: 4
};

// Apply theme
sdk.setTheme(theme);`}</code></pre>
        </TabsContent>

        <TabsContent value="white-labeling">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            Remove VCOS branding and customize the UI completely.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// White label configuration
const config = {
  branding: {
    logo: 'https://your-domain.com/logo.png',
    companyName: 'Your Company',
    favicon: 'https://your-domain.com/favicon.ico'
  },
  hideVCOSBranding: true,
  customCSS: \`
    .vcos-header { display: none; }
    .vcos-footer { display: none; }
  \`
};

sdk.setWhiteLabel(config);`}</code></pre>
        </TabsContent>

        <TabsContent value="events">
          <p className="text-slate-600 dark:text-slate-300 mb-4">
            Listen to dashboard events and trigger custom actions.
          </p>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg overflow-x-auto text-sm"><code>{`// Listen to dashboard events
sdk.on('dashboard:load', (data) => {
  console.log('Dashboard loaded:', data);
});

sdk.on('dashboard:filter:change', (filters) => {
  console.log('Filters changed:', filters);
});

sdk.on('dashboard:export', (data) => {
  downloadExport(data);
});

// Send custom events
sdk.emit('custom:action', { action: 'export_pdf', params: {} });`}</code></pre>
        </TabsContent>
      </Tabs>
    </>
  );

  // APIReferenceContent
  const APIReferenceContent = () => (
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

  // ExamplesContent
  const ExamplesContent = () => (
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

  const contentMap: Record<string, React.ReactNode> = {
    "quick-start": <QuickStartContent />,
    "embedding": <EmbeddingContent />,
    "authentication": <AuthenticationContent />,
    "customization": <CustomizationContent />,
    "api-reference": <APIReferenceContent />,
    "examples": <ExamplesContent />,
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <MobileMenuButton />
      <Sidebar />
      <main className="lg:ml-72 flex-1">
        <Header />
        <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">
          {contentMap[activeSection]}
        </div>
      </main>
    </div>
  );
}

export default EmbeddedAnalyticsDocsPage;