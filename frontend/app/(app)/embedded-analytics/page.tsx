"use client";

import { useState } from "react";
import { Plus, Code, Zap, Palette, Shield, HelpCircle, ExternalLink, Eye } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";

import { useAuth } from "@/hooks/useAuth";
import { useEmbeddedAnalytics } from "@/hooks/useEmbeddedAnalytics";
import { roleCan, PERMISSIONS } from "@/lib/permissions";
import { useWhiteLabelTheme } from "@/hooks/useEmbeddedAnalytics";

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

export default function EmbeddedAnalyticsPage() {
  const { user } = useAuth();
  const canManage = roleCan(user?.role || "", "analytics:read");
  const canView = roleCan(user?.role || "", "analytics:read");
  const theme = useWhiteLabelTheme();
  
  const { isLoading: loading, error, fetchDashboard, dashboard } = useEmbeddedAnalytics();
  
  const [searchQuery, setSearchQuery] = useState("");

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-ink">Embedded Analytics</h1>
            <p className="text-sm text-muted mt-1">Create and manage embedded dashboards for white-label analytics</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => {}} disabled>
              <Code className="w-4 h-4 mr-2" />
              Documentation
            </Button>
            <Button onClick={() => alert("Create dashboard")} disabled={!canManage}>
              <Plus className="w-4 h-4 mr-2" />
              New Embedded Dashboard
            </Button>
          </div>
        </div>

        <Tabs defaultValue="dashboards" className="space-y-6">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="dashboards">Dashboards</TabsTrigger>
            <TabsTrigger value="branding">
              <Palette className="w-4 h-4 mr-2" />
              Branding
            </TabsTrigger>
            <TabsTrigger value="sso">
              <Shield className="w-4 h-4 mr-2" />
              SSO Config
            </TabsTrigger>
            <TabsTrigger value="docs">
              <Code className="w-4 h-4 mr-2" />
              API Docs
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dashboards">
            <Card>
              {dashboard ? (
                <div className="p-6">
                  <h3 className="text-xl font-bold text-ink mb-2">{dashboard.name}</h3>
                  <p className="text-slate-500 dark:text-slate-400">{dashboard.description || "No description"}</p>
                  <div className="mt-4 flex gap-2">
                    <Button variant="secondary" onClick={() => alert("View embed code")}>
                      <ExternalLink className="w-4 h-4 mr-2" />
                      Embed Code
                    </Button>
                    <Button onClick={() => alert("Preview")}>
                      <Eye className="w-4 h-4 mr-2" />
                      Preview
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="p-6 text-center">
                  <p className="text-muted">No dashboard selected. Create or select a dashboard to view details.</p>
                  <Button className="mt-4" onClick={() => alert("Create dashboard")}>
                    <Plus className="w-4 h-4 mr-2" />
                    Create Dashboard
                  </Button>
                </div>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="branding">
            <div className="p-4">Branding configuration coming soon...</div>
          </TabsContent>

          <TabsContent value="sso">
            <div className="p-4">SSO configuration coming soon...</div>
          </TabsContent>

          <TabsContent value="docs">
            <div className="p-4">API Documentation coming soon...</div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}