"use client";

import { Palette, Zap } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

export function CustomizationContent() {
  return (
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
}