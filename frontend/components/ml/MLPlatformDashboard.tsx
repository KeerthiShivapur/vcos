"use client";

/**
 * ML Platform Dashboard
 * Main dashboard combining all ML Platform sub-dashboards
 */

import { useState, useMemo } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Card } from "@/components/ui/Card";
// import { MLInsightsDashboard } from "@/components/collaboration/MLInsightsDashboard";
import { ModelRegistryDashboard } from "./ModelRegistryDashboard";
import { FeatureStoreExplorer } from "./FeatureStoreExplorer";
import { ForecastingWorkbench } from "./ForecastingWorkbench";
import { CausalAnalysisPanel } from "./CausalAnalysisPanel";
import { TextToSQLPlayground } from "./TextToSQLPlayground";
import { ProactiveAlertsCenter } from "./ProactiveAlertsCenter";
import {
  Brain,
  Database,
  LineChart,
  GitBranch,
  Terminal,
  AlertTriangle,
  Zap,
} from "lucide-react";
import { classNames } from "@/lib/utils";

interface MLPlatformDashboardProps {
  organizationId: string;
  className?: string;
}

export function MLPlatformDashboard({
  organizationId,
  className,
}: MLPlatformDashboardProps) {
  const [activeTab, setActiveTab] = useState<
    | "insights"
    | "models"
    | "features"
    | "forecasting"
    | "causal"
    | "sql"
    | "alerts"
  >("insights");

  const tabs = useMemo(
    () => [
      {
        id: "insights",
        label: "ML Insights",
        icon: Brain,
        description: "AI-powered predictions, anomalies & recommendations",
      },
      {
        id: "models",
        label: "Model Registry",
        icon: GitBranch,
        description: "Browse, register & deploy ML models",
      },
      {
        id: "features",
        label: "Feature Store",
        icon: Database,
        description: "Manage entities, feature views & online serving",
      },
      {
        id: "forecasting",
        label: "Forecasting",
        icon: LineChart,
        description: "Time series forecasting & evaluation",
      },
      {
        id: "causal",
        label: "Causal Analysis",
        icon: Zap,
        description: "Causal inference, counterfactuals & mediation",
      },
      {
        id: "sql",
        label: "Text-to-SQL",
        icon: Terminal,
        description: "Natural language to SQL with semantic layer",
      },
      {
        id: "alerts",
        label: "Proactive Alerts",
        icon: AlertTriangle,
        description: "Automated anomaly detection & alerting",
      },
    ],
    [],
  );

  return (
    <div className={classNames("flex flex-col h-full", className)}>
      {/* Header */}
      <div className="p-4 border-b border-line bg-canvas/50">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-ink">ML Platform</h1>
              <p className="text-sm text-muted">
                Unified ML Platform: Models, Features, Forecasting, Causal
                Inference & Proactive Insights
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-7 p-1 bg-canvas/50 border-b border-line">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className="flex flex-col items-center gap-1 py-3 px-2 text-sm"
            >
              <tab.icon className="h-5 w-5 text-muted" />
              <span className="font-medium">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="insights" className="flex-1 p-4">
          <div className="p-8 text-center text-muted">
            <p>Insights dashboard coming soon</p>
          </div>
        </TabsContent>

        <TabsContent value="models" className="flex-1 p-4">
          <ModelRegistryDashboard organizationId={organizationId} />
        </TabsContent>

        <TabsContent value="features" className="flex-1 p-4">
          <FeatureStoreExplorer organizationId={organizationId} />
        </TabsContent>

        <TabsContent value="forecasting" className="flex-1 p-4">
          <ForecastingWorkbench organizationId={organizationId} />
        </TabsContent>

        <TabsContent value="causal" className="flex-1 p-4">
          <CausalAnalysisPanel organizationId={organizationId} />
        </TabsContent>

        <TabsContent value="sql" className="flex-1 p-4">
          <TextToSQLPlayground organizationId={organizationId} />
        </TabsContent>

        <TabsContent value="alerts" className="flex-1 p-4">
          <ProactiveAlertsCenter organizationId={organizationId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default MLPlatformDashboard;
