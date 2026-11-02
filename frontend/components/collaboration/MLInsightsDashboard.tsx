"use client";

import { useState, useEffect, useMemo } from "react";
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Activity,
  Brain,
  Zap,
  Target,
  DollarSign,
  Users,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  Download,
  Filter,
  Calendar,
  BarChart2,
  LineChart,
  PieChart,
  AlertCircle,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { classNames } from "@/lib/utils";

interface MLInsight {
  id: string;
  type: "forecast" | "anomaly" | "recommendation" | "risk";
  title: string;
  description: string;
  severity: "high" | "medium" | "low";
  confidence: number;
  impact: "high" | "medium" | "low";
  metric?: string;
  currentValue?: number;
  predictedValue?: number;
  timeframe?: string;
  actionable: boolean;
  actions?: Array<{ label: string; type: "view" | "configure" | "dismiss" }>;
  createdAt: string;
  modelName: string;
}

interface MLInsightsDashboardProps {
  organizationId: string;
  className?: string;
}

const MOCK_INSIGHTS: MLInsight[] = [
  {
    id: "1",
    type: "forecast",
    title: "Revenue Forecast - Q2 Exceeding Targets",
    description: "Current trajectory indicates 15% above Q2 revenue target. Strong performance in APAC region driving growth.",
    severity: "low",
    confidence: 0.92,
    impact: "high",
    metric: "quarterly_revenue",
    currentValue: 2.45,
    predictedValue: 2.82,
    timeframe: "Q2 2024",
    actionable: true,
    actions: [{ label: "View Forecast Details", type: "view" }, { label: "Adjust Budget", type: "configure" }],
    createdAt: "2024-03-15T10:30:00Z",
    modelName: "Prophet Forecaster v3.2",
  },
  {
    id: "2",
    type: "anomaly",
    title: "Unusual Spike in Customer Churn",
    description: "Detected 40% increase in churn rate for Enterprise segment over past 2 weeks. Correlated with new competitor pricing.",
    severity: "high",
    confidence: 0.87,
    impact: "high",
    metric: "churn_rate_enterprise",
    currentValue: 0.08,
    predictedValue: 0.12,
    timeframe: "Last 14 days",
    actionable: true,
    actions: [{ label: "Investigate Root Cause", type: "view" }, { label: "Launch Retention Campaign", type: "configure" }],
    createdAt: "2024-03-14T16:45:00Z",
    modelName: "Isolation Forest v2.1",
  },
  {
    id: "3",
    type: "recommendation",
    title: "Optimize Cloud Infrastructure Costs",
    description: "Identified 23% cost reduction opportunity by rightsizing underutilized compute instances and enabling savings plans.",
    severity: "medium",
    confidence: 0.89,
    impact: "medium",
    metric: "cloud_cost_per_user",
    currentValue: 45.2,
    predictedValue: 34.8,
    timeframe: "Next 30 days",
    actionable: true,
    actions: [{ label: "View Savings Plan", type: "view" }, { label: "Apply Recommendations", type: "configure" }],
    createdAt: "2024-03-13T09:15:00Z",
    modelName: "Cost Optimization Engine v1.5",
  },
  {
    id: "4",
    type: "risk",
    title: "Project Delivery Timeline at Risk",
    description: "Project Phoenix timeline shows 65% probability of 2-week delay based on current velocity and resource allocation.",
    severity: "medium",
    confidence: 0.78,
    impact: "high",
    metric: "project_velocity",
    currentValue: 0.72,
    predictedValue: 0.58,
    timeframe: "Next Sprint",
    actionable: true,
    actions: [{ label: "View Project Health", type: "view" }, { label: "Reallocate Resources", type: "configure" }],
    createdAt: "2024-03-12T14:20:00Z",
    modelName: "Project Risk Scorer v2.0",
  },
  {
    id: "5",
    type: "forecast",
    title: "Employee Attrition Risk - Engineering",
    description: "ML model predicts 18% attrition rate in Engineering over next quarter. Key drivers: compensation gap and workload.",
    severity: "high",
    confidence: 0.83,
    impact: "high",
    metric: "attrition_rate_engineering",
    currentValue: 0.12,
    predictedValue: 0.18,
    timeframe: "Q2 2024",
    actionable: true,
    actions: [{ label: "View Retention Plan", type: "view" }, { label: "Schedule 1:1s", type: "configure" }],
    createdAt: "2024-03-11T11:00:00Z",
    modelName: "Attrition Predictor v1.8",
  },
  {
    id: "6",
    type: "anomaly",
    title: "Unusual API Latency Pattern",
    description: "Payment API p99 latency increased 300% between 2-4 AM UTC. No deployment correlation found.",
    severity: "medium",
    confidence: 0.91,
    impact: "medium",
    metric: "api_latency_p99",
    currentValue: 145,
    predictedValue: 220,
    timeframe: "Last 6 hours",
    actionable: true,
    actions: [{ label: "View Traces", type: "view" }, { label: "Create Incident", type: "configure" }],
    createdAt: "2024-03-15T03:30:00Z",
    modelName: "Anomaly Detector v3.0",
  },
];

export function MLInsightsDashboard({ organizationId, className }: MLInsightsDashboardProps) {
  const [insights, setInsights] = useState<MLInsight[]>(MOCK_INSIGHTS);
  const [filterSeverity, setFilterSeverity] = useState<"all" | "high" | "medium" | "low">("all");
  const [filterType, setFilterType] = useState<"all" | "forecast" | "anomaly" | "recommendation" | "risk">("all");
  const [sortBy, setSortBy] = useState<"severity" | "confidence" | "impact" | "date">("severity");
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d" | "90d">("7d");
  const [expandedInsights, setExpandedInsights] = useState<Set<string>>(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showModelDetails, setShowModelDetails] = useState<string | null>(null);

  const filteredInsights = useMemo(() => {
    return insights
      .filter(i => filterSeverity === "all" || i.severity === filterSeverity)
      .filter(i => filterType === "all" || i.type === filterType)
      .sort((a, b) => {
        if (sortBy === "severity") {
          const severityOrder = { high: 3, medium: 2, low: 1 };
          return severityOrder[b.severity] - severityOrder[a.severity];
        }
        if (sortBy === "confidence") return b.confidence - a.confidence;
        if (sortBy === "impact") {
          const impactOrder = { high: 3, medium: 2, low: 1 };
          return impactOrder[b.impact] - impactOrder[a.impact];
        }
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      });
  }, [insights, filterSeverity, filterType, sortBy]);

  const stats = useMemo(() => ({
    total: insights.length,
    high: insights.filter(i => i.severity === "high").length,
    medium: insights.filter(i => i.severity === "medium").length,
    low: insights.filter(i => i.severity === "low").length,
    actionable: insights.filter(i => i.actionable).length,
    avgConfidence: insights.reduce((sum, i) => sum + i.confidence, 0) / insights.length,
  }, [insights]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await new Promise(r => setTimeout(r, 1000));
    setIsRefreshing(false);
  }, []);

  const toggleExpand = useCallback((id: string) => {
    setExpandedInsights(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleAction = useCallback((insight: MLInsight, actionType: string) => {
    console.log(`Action ${actionType} for insight ${insight.id}`);
  }, []);

  const dismissInsight = useCallback((id: string) => {
    setInsights(prev => prev.filter(i => i.id !== id));
  }, []);

  const formatTimeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const getSeverityConfig = (severity: string) => {
    switch (severity) {
      case "high": return { color: "bg-red-100 text-red-700 border-red-200", icon: AlertCircle, label: "High" };
      case "medium": return { color: "bg-amber-100 text-amber-700 border-amber-200", icon: AlertTriangle, label: "Medium" };
      case "low": return { color: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle, label: "Low" };
      default: return { color: "bg-muted text-muted", icon: Info, label: "Unknown" };
    }
  };

  const getTypeConfig = (type: string) => {
    switch (type) {
      case "forecast": return { icon: TrendingUp, label: "Forecast", color: "text-blue-600 bg-blue-100" };
      case "anomaly": return { icon: AlertTriangle, label: "Anomaly", color: "text-red-600 bg-red-100" };
      case "recommendation": return { icon: Target, label: "Recommendation", color: "text-emerald-600 bg-emerald-100" };
      case "risk": return { icon: AlertCircle, label: "Risk", color: "text-amber-600 bg-amber-100" };
      default: return { icon: Info, label: "Unknown", color: "text-muted" };
    }
  };

  return (
    <div className={classNames("flex flex-col h-full bg-canvas rounded-xl border border-line overflow-hidden", className)}>
      {/* Header */}
      <div className="p-4 border-b border-line bg-canvas/50">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">ML Insights</h2>
              <p className="text-sm text-muted">AI-powered predictions, anomalies & recommendations</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <Calendar className="h-4 w-4 text-muted" />
              <select
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="24h">24h</option>
                <option value="7d">7d</option>
                <option value="30d">30d</option>
                <option value="90d">90d</option>
              </select>
            </div>
            
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="p-2 rounded-lg bg-canvas border border-line text-ink hover:bg-muted transition-colors"
              title="Refresh insights"
            >
              <RefreshCw className={classNames("h-4 w-4", isRefreshing && "animate-spin")} />
            </button>
            
            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <Filter className="h-4 w-4 text-muted" />
              <select
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="all">All Severities</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
            
            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="all">All Types</option>
                <option value="forecast">Forecast</option>
                <option value="anomaly">Anomaly</option>
                <option value="recommendation">Recommendation</option>
                <option value="risk">Risk</option>
              </select>
            </div>
            
            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="severity">Severity</option>
                <option value="confidence">Confidence</option>
                <option value="impact">Impact</option>
                <option value="date">Date</option>
              </select>
            </div>
            
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="p-2 rounded-lg bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
              disabled={isRefreshing}
            >
              <RefreshCw className={classNames("h-4 w-4", isRefreshing && "animate-spin")} />
              <span className="hidden sm:inline">Refresh</span>
            </button>
          </div>
        </div>

      {/* Stats Row */}
      <div className="px-4 py-3 border-b border-line bg-canvas/30">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <StatCard 
            label="Total Insights" 
            value={stats.total} 
            icon={Brain} 
            color="bg-brand/10 text-brand" 
            trend={"+12% vs last week"}
            trendUp={true}
          />
          <StatCard 
            label="High Severity" 
            value={stats.high} 
            icon={AlertCircle} 
            color="bg-red-100 text-red-600" 
            trend={stats.high > 2 ? "Attention needed" : "Under control"}
            trendUp={false}
          />
          <StatCard 
            label="Medium Severity" 
            value={stats.medium} 
            icon={AlertTriangle} 
            color="bg-amber-100 text-amber-600" 
            trend={stats.medium > 3 ? "Monitor" : "Normal"}
            trendUp={false}
          />
          <StatCard 
            label="Low Severity" 
            value={stats.low} 
            icon={CheckCircle} 
            color="bg-emerald-100 text-emerald-600" 
            trend="Within range"
            trendUp={true}
          />
          <StatCard 
            label="Actionable" 
            value={stats.actionable} 
            icon={Target} 
            color="bg-emerald-100 text-emerald-600" 
            trend={`${Math.round(stats.actionable / stats.total * 100)}% of total`}
            trendUp={true}
          />
          <StatCard 
            label="Avg Confidence" 
            value={`${Math.round(stats.avgConfidence * 100)}%`} 
            icon={Target} 
            color="bg-blue-100 text-blue-600" 
            trend={stats.avgConfidence > 0.85 ? "Excellent" : "Good"}
            trendUp={stats.avgConfidence > 0.85}
          />
        </div>
      </div>

      {/* Insights List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {filteredInsights.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Filter className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">No insights match your filters</h3>
            <p className="text-faint max-w-md mx-auto">
              Try adjusting your filters or time range to see more insights.
            </p>
            <button
              onClick={() => { setFilterSeverity("all"); setFilterType("all"); }}
              className="mt-4 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-strong transition-colors"
            >
              Clear All Filters
            </button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-medium text-ink">
                {filteredInsights.length} insight{filteredInsights.length !== 1 ? "s" : ""} found
              </h3>
              <div className="flex items-center gap-2 text-sm text-muted">
                <span>Sorted by: {sortBy}</span>
                <ChevronDown className="h-4 w-4" />
              </div>
            </div>
            
            <div className="space-y-3">
              {filteredInsights.map((insight) => (
                <InsightCard
                  key={insight.id}
                  insight={insight}
                  isExpanded={expandedInsights.has(insight.id)}
                  onToggleExpand={() => toggleExpand(insight.id)}
                  onAction={(action) => handleAction(insight, action)}
                  onDismiss={() => dismissInsight(insight.id)}
                  onShowModelDetails={() => setShowModelDetails(insight.id === showModelDetails ? null : insight.id)}
                  showModelDetails={showModelDetails === insight.id}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ 
  label, 
  value, 
  icon: Icon, 
  color, 
  trend, 
  trendUp 
}: { 
  label: string; 
  value: string | number; 
  icon: React.ComponentType<{ className?: string }>; 
  color: string; 
  trend: string; 
  trendUp: boolean; 
}) {
  return (
    <div className="p-3 rounded-xl bg-canvas border border-line">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={classNames("p-2 rounded-lg", color)}>
            <icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted">{label}</p>
            <p className="text-lg font-bold text-ink">{value}</p>
          </div>
        </div>
        <div className={classNames(
          "text-xs font-medium px-2 py-0.5 rounded",
          trendUp ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
        )}>
          {trendUp ? <TrendingUp className="h-3 w-3 inline mr-1" /> : <TrendingDown className="h-3 w-3 inline mr-1" />}
          {trend}
        </div>
      </div>
    </div>
  );
}

function InsightCard({
  insight,
  isExpanded,
  onToggleExpand,
  onAction,
  onDismiss,
  onShowModelDetails,
  showModelDetails,
}: {
  insight: MLInsight;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onAction: (action: string) => void;
  onDismiss: () => void;
  onShowModelDetails: () => void;
  showModelDetails: boolean;
}) {
  const severityConfig = {
    high: { color: "bg-red-100 text-red-700 border-red-200", icon: AlertCircle, label: "High" },
    medium: { color: "bg-amber-100 text-amber-700 border-amber-200", icon: AlertTriangle, label: "Medium" },
    low: { color: "bg-emerald-100 text-emerald-700 border-emerald-200", icon: CheckCircle, label: "Low" },
  }[insight.severity];

  const typeConfig = {
    forecast: { icon: TrendingUp, label: "Forecast", color: "text-blue-600 bg-blue-100" },
    anomaly: { icon: AlertTriangle, label: "Anomaly", color: "text-red-600 bg-red-100" },
    recommendation: { icon: Target, label: "Recommendation", color: "text-emerald-600 bg-emerald-100" },
    risk: { icon: AlertCircle, label: "Risk", color: "text-amber-600 bg-amber-100" },
  }[insight.type];

  const TypeIcon = typeConfig.icon;
  const SeverityIcon = severityConfig.icon;

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden transition-all duration-200 hover:border-brand/30">
      {/* Main Card */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={classNames("p-2 rounded-lg", typeConfig.color.replace("text-", "bg-").replace("600", "100"))}>
              <TypeIcon className={classNames("h-5 w-5", typeConfig.color)} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">{insight.title}</h4>
                <span className={classNames(
                  "px-2 py-0.5 rounded text-xs font-medium border",
                  severityConfig.color
                )}>
                  <SeverityIcon className="h-3 w-3 inline mr-1" />
                  {severityConfig.label}
                </span>
                <span className={classNames(
                  "px-2 py-0.5 rounded text-xs font-medium",
                  typeConfig.color.replace("text-", "bg-").replace("600", "100")
                )}>
                  {typeConfig.label}
                </span>
              </div>
              <p className="text-sm text-muted mt-1 line-clamp-2">{insight.description}</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Confidence */}
            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <Target className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-ink">{Math.round(insight.confidence * 100)}%</span>
              <span className="text-xs text-muted">confidence</span>
            </div>
            
            {/* Impact */}
            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <Zap className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-ink capitalize">{insight.impact}</span>
              <span className="text-xs text-muted">impact</span>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 ml-auto">
              <button
                onClick={(e) => { e.stopPropagation(); onShowModelDetails(); }}
                className="p-1.5 rounded hover:bg-muted text-muted hover:text-brand transition-colors"
                title="Model Details"
              >
                <Brain className="h-4 w-4" />
              </button>
              
              {insight.actionable && insight.actions?.map((action, i) => (
                <button
                  key={i}
                  onClick={(e) => { e.stopPropagation(); onAction(action.type); }}
                  className="px-2 py-1 text-xs font-medium text-brand hover:bg-brand/10 rounded transition-colors"
                >
                  {action.label}
                </button>
              ))}
              
              <button
                onClick={(e) => { e.stopPropagation(); onDismiss(); }}
                className="p-1.5 rounded hover:bg-muted text-muted hover:text-red-600 transition-colors"
                title="Dismiss"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Expanded Content */}
        {isExpanded && (
          <div className="border-t border-line p-4 bg-canvas/50 animate-slide-down">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="p-3 rounded-lg bg-canvas border border-line">
                <p className="text-xs font-medium text-muted mb-1">Metric</p>
                <p className="font-medium text-ink">{insight.metric || "N/A"}</p>
              </div>
              <div className="p-3 rounded-lg bg-canvas border border-line">
                <p className="text-xs font-medium text-muted mb-1">Current Value</p>
                <p className="font-medium text-ink">{insight.currentValue !== undefined ? insight.currentValue.toLocaleString() : "N/A"}</p>
              </div>
              <div className="p-3 rounded-lg bg-canvas border border-line">
                <p className="text-xs font-medium text-muted mb-1">Predicted Value</p>
                <p className={classNames(
                  "font-medium",
                  insight.predictedValue !== undefined && insight.currentValue !== undefined && 
                  ((insight.type === "anomaly" && insight.predictedValue > insight.currentValue) ||
                   (insight.type !== "anomaly" && insight.predictedValue < insight.currentValue))
                    ? "text-red-600" : "text-emerald-600"
                )}>
                  {insight.predictedValue !== undefined ? insight.predictedValue.toLocaleString() : "N/A"}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
                {insight.modelName}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-muted text-muted">
                {formatTimeAgo(insight.createdAt)}
              </span>
              {insight.timeframe && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-muted text-muted">
                  {insight.timeframe}
                </span>
              )}
            </div>

            {showModelDetails && (
              <div className="mt-4 p-3 rounded-lg bg-brand/5 border border-brand/20 animate-slide-down">
                <div className="flex items-center justify-between mb-2">
                  <h5 className="font-medium text-ink">Model Details</h5>
                  <button
                    onClick={() => showModelDetails(false)}
                    className="p-1 rounded hover:bg-muted text-muted"
                  >
                    <ChevronUp className="h-4 w-4" />
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-muted">Model Name</p>
                    <p className="font-medium">{insight.modelName}</p>
                  </div>
                  <div>
                    <p className="text-muted">Confidence</p>
                    <p className="font-medium">{Math.round(insight.confidence * 100)}%</p>
                  </div>
                  <div>
                    <p className="text-muted">Severity</p>
                    <p className="font-medium capitalize">{insight.severity}</p>
                  </div>
                  <div>
                    <p className="text-muted">Impact</p>
                    <p className="font-medium capitalize">{insight.impact}</p>
                  </div>
                  <div>
                    <p className="text-muted">Actionable</p>
                    <p className="font-medium">{insight.actionable ? "Yes" : "No"}</p>
                  </div>
                  <div>
                    <p className="text-muted">Created</p>
                    <p className="font-medium">{formatDate(insight.createdAt)}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 pt-3 border-t border-line">
              {insight.actions?.map((action, i) => (
                <button
                  key={i}
                  onClick={() => { onAction(action.type); }}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium text-brand hover:bg-brand/10 border border-brand/20 transition-colors"
                >
                  {action.type === "view" && <Zap className="h-3 w-3" />}
                  {action.type === "configure" && <Settings className="h-3 w-3" />}
                  {action.type === "dismiss" && <XCircle className="h-3 w-3" />}
                  {action.label}
                </button>
              ))}
              <button
                onClick={() => { /* dismiss */ }}
                className="ml-auto p-2 rounded-lg text-muted hover:bg-muted hover:text-red-600 transition-colors"
                title="Dismiss"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatTimeAgo(dateString: string) {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(date.getTime() / 60000);
  const diffHours = Math.floor(date.getTime() / 3600000);
  const diffDays = Math.floor(date.getTime() / 86400000);
  
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}