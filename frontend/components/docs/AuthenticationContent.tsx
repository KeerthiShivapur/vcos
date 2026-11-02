"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

export function AuthenticationContent() {
  return (
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
}