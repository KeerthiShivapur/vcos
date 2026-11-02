"use client";

/**
 * Proactive Alerts Center
 * View insights, anomalies, trend changes & manage alert rules
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useProactiveInsights } from "@/hooks/useMLPlatform";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import {
  Table,
  TableHeader,
  TableRow,
  TableCell,
  TableHeaderCell,
} from "@/components/ui/Table";
import { Modal } from "@/components/ui/Modal";
import { InputTextarea } from "@/components/ui/Input";
import {
  Plus,
  Search,
  Filter,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Bell,
  BellOff,
  Check,
  X,
  RefreshCw,
  Loader2,
  Settings,
  Eye,
  Clock,
  Zap,
  Lightbulb,
  Link,
  BarChart2,
  LineChart,
  PieChart,
  AlertCircle,
  CheckCircle,
  XCircle,
  MoreHorizontal,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  Filter as FilterIcon,
  Target,
} from "lucide-react";
import { classNames } from "@/lib/utils";
import {
  Insight,
  Anomaly,
  TrendChange,
  Alert,
  AlertRule,
  AlertChannel,
  InsightType,
  InsightSeverity,
  AnomalyMethod,
  DataPoint,
  TimeSeriesMetric,
  AlertRuleRequest,
} from "@/hooks/useMLPlatform";

interface ProactiveAlertsCenterProps {
  organizationId: string;
  className?: string;
}

export function ProactiveAlertsCenter({
  organizationId,
  className,
}: ProactiveAlertsCenterProps) {
  const {
    insights,
    anomalies,
    trends,
    alerts,
    status,
    registerMetric,
    updateMetric,
    addAlertRule,
    listAlertRules,
    startMonitoring,
    stopMonitoring,
    getStatus,
    getInsights,
    getAnomalies,
    getTrends,
    getAlerts,
    acknowledgeInsight,
    acknowledgeAnomaly,
  } = useProactiveInsights();

  const [activeTab, setActiveTab] = useState<
    "insights" | "anomalies" | "trends" | "alerts" | "rules" | "status"
  >("insights");
  const [searchQuery, setSearchQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState<
    "all" | "critical" | "warning" | "info"
  >("all");
  const [typeFilter, setTypeFilter] = useState<
    | "all"
    | "anomaly"
    | "trend_change"
    | "seasonality_shift"
    | "correlation_break"
    | "threshold_breach"
    | "forecast_deviation"
    | "pattern_discovery"
    | "causal_hypothesis"
  >("all");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isMonitoring, setIsMonitoring] = useState(false);

  // Alert rule form state
  const [showCreateRule, setShowCreateRule] = useState(false);
  const [newRule, setNewRule] = useState({
    id: "",
    name: "",
    metric_patterns: [] as string[],
    severity_threshold: "warning" as "info" | "warning" | "critical",
    channels: [] as AlertChannel[],
    recipients: {} as Record<AlertChannel, string[]>,
    cooldown_minutes: 60,
    enabled: true,
  });

  // Metric registration state
  const [showRegisterMetric, setShowRegisterMetric] = useState(false);
  const [registerMetricRequest, setRegisterMetricRequest] = useState({
    name: "",
    data: [] as DataPoint[],
    frequency: "1h",
    thresholds: {} as Record<string, number>,
  });

  const fetchData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([
        getInsights(),
        getAnomalies(),
        getTrends(),
        getAlerts(),
        listAlertRules(),
        getStatus(),
      ]);
    } finally {
      setIsRefreshing(false);
    }
  }, [
    getInsights,
    getAnomalies,
    getTrends,
    getAlerts,
    listAlertRules,
    getStatus,
  ]);

  useEffect(() => {
    fetchData();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    await addAlertRule(newRule);
    setShowCreateRule(false);
    setNewRule({
      id: "",
      name: "",
      metric_patterns: [],
      severity_threshold: "warning",
      channels: [],
      recipients: {},
      cooldown_minutes: 60,
      enabled: true,
    });
    fetchData();
  };

  const handleStartMonitoring = async () => {
    await startMonitoring();
    setIsMonitoring(true);
  };

  const handleStopMonitoring = async () => {
    await stopMonitoring();
    setIsMonitoring(false);
  };

  const handleAcknowledgeInsight = async (insightId: string) => {
    await acknowledgeInsight(insightId);
    fetchData();
  };

  const handleAcknowledgeAnomaly = async (anomalyId: string) => {
    await acknowledgeAnomaly(anomalyId);
    fetchData();
  };

  return (
    <div
      className={classNames(
        "flex flex-col h-full bg-canvas rounded-xl border border-line overflow-hidden",
        className,
      )}
    >
      {/* Header */}
      <div className="p-4 border-b border-line bg-canvas/50">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Bell className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">
                Proactive Alerts Center
              </h2>
              <p className="text-sm text-muted">
                Automated anomaly detection, trend analysis & alert management
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-2 bg-canvas border border-line rounded-lg px-3 py-1">
              <FilterIcon className="h-4 w-4 text-muted" />
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="all">All Severities</option>
                <option value="critical">Critical</option>
                <option value="warning">Warning</option>
                <option value="info">Info</option>
              </select>
            </div>

            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <FilterIcon className="h-4 w-4 text-muted" />
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="all">All Types</option>
                <option value="anomaly">Anomaly</option>
                <option value="trend_change">Trend Change</option>
                <option value="seasonality_shift">Seasonality Shift</option>
                <option value="correlation_break">Correlation Break</option>
                <option value="threshold_breach">Threshold Breach</option>
                <option value="forecast_deviation">Forecast Deviation</option>
                <option value="pattern_discovery">Pattern Discovery</option>
                <option value="causal_hypothesis">Causal Hypothesis</option>
              </select>
            </div>

            <button
              onClick={fetchData}
              disabled={isRefreshing}
              className="p-2 rounded-lg bg-canvas border border-line text-ink hover:bg-muted transition-colors"
              title="Refresh"
            >
              <RefreshCw
                className={classNames(
                  "h-4 w-4",
                  isRefreshing && "animate-spin",
                )}
              />
            </button>

            {!isMonitoring ? (
              <button
                onClick={handleStartMonitoring}
                className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors flex items-center gap-1"
              >
                <Zap className="h-4 w-4" />
                <span className="hidden sm:inline">Start Monitoring</span>
              </button>
            ) : (
              <button
                onClick={handleStopMonitoring}
                className="px-3 py-1.5 rounded-lg text-sm font-medium bg-amber-600 text-white hover:bg-amber-700 transition-colors flex items-center gap-1"
              >
                <BellOff className="h-4 w-4" />
                <span className="hidden sm:inline">Stop Monitoring</span>
              </button>
            )}

            <button
              onClick={() => setShowCreateRule(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Alert Rule</span>
            </button>
          </div>
        </div>
      </div>

      {/* Status Bar */}
      {status && (
        <div className="px-4 py-2 border-b border-line bg-canvas/30">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4 text-sm">
              <span
                className={classNames(
                  "px-2 py-1 rounded-full font-medium",
                  isMonitoring
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-amber-100 text-amber-700",
                )}
              >
                {isMonitoring ? "● Monitoring Active" : "○ Monitoring Stopped"}
              </span>
              <span className="px-2 py-1 rounded-full bg-canvas border border-line">
                Metrics: {status.metrics_monitored || 0}
              </span>
              <span className="px-2 py-1 rounded-full bg-canvas border border-line">
                Insights: {status.total_insights || 0}
              </span>
              <span className="px-2 py-1 rounded-full bg-canvas border border-line">
                Anomalies: {status.total_anomalies || 0}
              </span>
              <span className="px-2 py-1 rounded-full bg-canvas border border-line">
                Trends: {status.total_trend_changes || 0}
              </span>
              <span className="px-2 py-1 rounded-full bg-canvas border border-line">
                Alerts: {status.total_alerts || 0}
              </span>
              <span className="px-2 py-1 rounded-full bg-canvas border border-line">
                Unacked: {status.unacknowledged_insights || 0} /{" "}
                {status.unacknowledged_anomalies || 0}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted">
                Last check: {new Date().toLocaleTimeString()}
              </span>
              <button
                onClick={fetchData}
                disabled={isRefreshing}
                className="p-1.5 rounded hover:bg-muted text-muted hover:text-ink transition-colors"
                title="Refresh"
              >
                <RefreshCw
                  className={classNames(
                    "h-4 w-4",
                    isRefreshing && "animate-spin",
                  )}
                />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-6 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger
            value="insights"
            className="py-2 flex items-center gap-2"
          >
            <Lightbulb className="h-4 w-4" />
            Insights
          </TabsTrigger>
          <TabsTrigger
            value="anomalies"
            className="py-2 flex items-center gap-2"
          >
            <AlertTriangle className="h-4 w-4" />
            Anomalies
          </TabsTrigger>
          <TabsTrigger value="trends" className="py-2 flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Trends
          </TabsTrigger>
          <TabsTrigger value="alerts" className="py-2 flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Alerts
          </TabsTrigger>
          <TabsTrigger value="rules" className="py-2 flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Rules
          </TabsTrigger>
          <TabsTrigger value="status" className="py-2 flex items-center gap-2">
            <BarChart2 className="h-4 w-4" />
            Status
          </TabsTrigger>
        </TabsList>

        {/* Insights Tab */}
        <TabsContent value="insights" className="flex-1 p-4 overflow-auto">
          <InsightsPanel
            insights={insights}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            severityFilter={severityFilter}
            setSeverityFilter={setSeverityFilter}
            typeFilter={typeFilter}
            setTypeFilter={setTypeFilter}
            onAcknowledge={handleAcknowledgeInsight}
          />
        </TabsContent>

        {/* Anomalies Tab */}
        <TabsContent value="anomalies" className="flex-1 p-4 overflow-auto">
          <AnomaliesPanel
            anomalies={anomalies}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            severityFilter={severityFilter}
            setSeverityFilter={setSeverityFilter}
            onAcknowledge={handleAcknowledgeAnomaly}
          />
        </TabsContent>

        {/* Trends Tab */}
        <TabsContent value="trends" className="flex-1 p-4 overflow-auto">
          <TrendsPanel
            trends={trends}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
          />
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="flex-1 p-4 overflow-auto">
          <AlertsPanel
            alerts={alerts}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
          />
        </TabsContent>

        {/* Rules Tab */}
        <TabsContent value="rules" className="flex-1 p-4 overflow-auto">
          <RulesPanel
            rules={listAlertRules()}
            onCreate={setShowCreateRule}
            onRefresh={fetchData}
          />
        </TabsContent>

        {/* Status Tab */}
        <TabsContent value="status" className="flex-1 p-4 overflow-auto">
          <StatusPanel
            status={status}
            isMonitoring={isMonitoring}
            onStart={handleStartMonitoring}
            onStop={handleStopMonitoring}
          />
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {createRuleModal()}
    </div>
  );

  function createRuleModal() {
    return (
      <Modal
        open={showCreateRule}
        onClose={() => setShowCreateRule(false)}
        title="Create Alert Rule"
        size="lg"
      >
        <form onSubmit={handleCreateRule} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Rule ID *
            </label>
            <Input
              value={newRule.id}
              onChange={(e) => setNewRule({ ...newRule, id: e.target.value })}
              placeholder="e.g., high_churn_alert"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Rule Name *
            </label>
            <Input
              value={newRule.name}
              onChange={(e) => setNewRule({ ...newRule, name: e.target.value })}
              placeholder="e.g., High Churn Rate Alert"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Metric Patterns (comma-separated regex)
            </label>
            <Input
              value={newRule.metric_patterns.join(", ")}
              onChange={(e) =>
                setNewRule({
                  ...newRule,
                  metric_patterns: e.target.value
                    .split(",")
                    .map((p) => p.trim())
                    .filter(Boolean),
                })
              }
              placeholder="e.g., churn_rate_*, revenue_*, latency_p99"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Severity Threshold
              </label>
              <Select
                value={newRule.severity_threshold}
                onValueChange={(v) =>
                  setNewRule({ ...newRule, severity_threshold: v as any })
                }
                options={[
                  { value: "info", label: "Info" },
                  { value: "warning", label: "Warning" },
                  { value: "critical", label: "Critical" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Cooldown (minutes)
              </label>
              <Input
                type="number"
                value={newRule.cooldown_minutes}
                onChange={(e) =>
                  setNewRule({
                    ...newRule,
                    cooldown_minutes: parseInt(e.target.value),
                  })
                }
                min={1}
                max={10080}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Channels
            </label>
            <div className="flex items-center gap-2 flex-wrap">
              {["email", "slack", "webhook", "push", "in_app"].map(
                (channel) => (
                  <label
                    key={channel}
                    className="flex items-center gap-1 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={newRule.channels.includes(
                        channel as AlertChannel,
                      )}
                      onChange={(e) =>
                        setNewRule({
                          ...newRule,
                          channels: e.target.checked
                            ? [...newRule.channels, channel as AlertChannel]
                            : newRule.channels.filter((c) => c !== channel),
                        })
                      }
                      className="rounded border-line"
                    />
                    <span className="text-sm text-ink capitalize">
                      {channel}
                    </span>
                  </label>
                ),
              )}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Recipients (JSON per channel)
            </label>
            <InputTextarea
              value={JSON.stringify(newRule.recipients, null, 2)}
              onChange={(e) => {
                try {
                  setNewRule({
                    ...newRule,
                    recipients: JSON.parse(e.target.value),
                  });
                } catch {}
              }}
              placeholder='{"email": ["user@example.com"], "slack": ["#alerts"]}'
              rows={3}
              fontMonospace
            />
          </div>
          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={newRule.enabled}
                onChange={(e) =>
                  setNewRule({ ...newRule, enabled: e.target.checked })
                }
                className="rounded border-line"
              />
              <span className="text-sm text-ink">Enabled</span>
            </label>
          </div>
          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setShowCreateRule(false);
                setNewRule({
                  id: "",
                  name: "",
                  metric_patterns: [],
                  severity_threshold: "warning",
                  channels: [],
                  recipients: {},
                  cooldown_minutes: 60,
                  enabled: true,
                });
              }}
            >
              Cancel
            </Button>
            <Button type="submit">Create Rule</Button>
          </div>
        </form>
      </Modal>
    );
  }
}

function InsightsPanel({
  insights,
  searchQuery,
  setSearchQuery,
  severityFilter,
  setSeverityFilter,
  typeFilter,
  setTypeFilter,
  onAcknowledge,
}: {
  insights: Insight[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  severityFilter: "all" | "critical" | "warning" | "info";
  setSeverityFilter: (s: "all" | "critical" | "warning" | "info") => void;
  typeFilter:
    | "all"
    | "anomaly"
    | "trend_change"
    | "seasonality_shift"
    | "correlation_break"
    | "threshold_breach"
    | "forecast_deviation"
    | "pattern_discovery"
    | "causal_hypothesis";
  setTypeFilter: (
    t:
      | "all"
      | "anomaly"
      | "trend_change"
      | "seasonality_shift"
      | "correlation_break"
      | "threshold_breach"
      | "forecast_deviation"
      | "pattern_discovery"
      | "causal_hypothesis",
  ) => void;
  onAcknowledge: (id: string) => void;
}) {
  const filtered = useMemo(
    () =>
      insights.filter((i) => {
        const matchesSearch =
          i.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          i.description.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesSeverity =
          severityFilter === "all" || i.severity === severityFilter;
        const matchesType = typeFilter === "all" || i.type === typeFilter;
        return matchesSearch && matchesSeverity && matchesType;
      }),
    [insights, searchQuery, severityFilter, typeFilter],
  );

  const getTypeIcon = (type: InsightType) => {
    switch (type) {
      case "anomaly":
        return AlertTriangle;
      case "trend_change":
        return TrendingUp;
      case "seasonality_shift":
        return LineChart;
      case "correlation_break":
        return Link;
      case "threshold_breach":
        return AlertCircle;
      case "forecast_deviation":
        return TrendingDown;
      case "pattern_discovery":
        return Lightbulb;
      case "causal_hypothesis":
        return Zap;
      default:
        return Lightbulb;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search insights..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-64"
          />
          <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
            <Filter className="h-4 w-4 text-muted" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as any)}
              className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </div>
          <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as any)}
              className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
            >
              <option value="all">All Types</option>
              <option value="anomaly">Anomaly</option>
              <option value="trend_change">Trend Change</option>
              <option value="seasonality_shift">Seasonality Shift</option>
              <option value="correlation_break">Correlation Break</option>
              <option value="threshold_breach">Threshold Breach</option>
              <option value="forecast_deviation">Forecast Deviation</option>
              <option value="pattern_discovery">Pattern Discovery</option>
              <option value="causal_hypothesis">Causal Hypothesis</option>
            </select>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Lightbulb className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No insights match your filters
            </h3>
            <p className="text-faint max-w-md mx-auto">
              Try adjusting your filters or search query
            </p>
            <Button
              onClick={() => {
                setSeverityFilter("all");
                setTypeFilter("all");
                setSearchQuery("");
              }}
              className="mt-4"
            >
              Clear All Filters
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((insight) => (
              <InsightCard
                key={insight.id}
                insight={insight}
                onAcknowledge={onAcknowledge}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function InsightCard({
  insight,
  onAcknowledge,
}: {
  insight: Insight;
  onAcknowledge: (id: string) => void;
}) {
  const severityConfig = {
    critical: {
      color: "bg-red-100 text-red-700 border-red-200",
      icon: AlertCircle,
      label: "Critical",
    },
    warning: {
      color: "bg-amber-100 text-amber-700 border-amber-200",
      icon: AlertTriangle,
      label: "Warning",
    },
    info: {
      color: "bg-blue-100 text-blue-700 border-blue-200",
      icon: Lightbulb,
      label: "Info",
    },
  }[insight.severity];

  const typeConfig = {
    anomaly: {
      icon: AlertTriangle,
      label: "Anomaly",
      color: "text-red-600 bg-red-100",
    },
    trend_change: {
      icon: TrendingUp,
      label: "Trend Change",
      color: "text-blue-600 bg-blue-100",
    },
    seasonality_shift: {
      icon: LineChart,
      label: "Seasonality Shift",
      color: "text-purple-600 bg-purple-100",
    },
    correlation_break: {
      icon: Link,
      label: "Correlation Break",
      color: "text-purple-600 bg-purple-100",
    },
    threshold_breach: {
      icon: AlertCircle,
      label: "Threshold Breach",
      color: "text-red-600 bg-red-100",
    },
    forecast_deviation: {
      icon: TrendingDown,
      label: "Forecast Deviation",
      color: "text-orange-600 bg-orange-100",
    },
    pattern_discovery: {
      icon: Lightbulb,
      label: "Pattern Discovery",
      color: "text-emerald-600 bg-emerald-100",
    },
    causal_hypothesis: {
      icon: Zap,
      label: "Causal Hypothesis",
      color: "text-amber-600 bg-amber-100",
    },
  }[insight.type];

  const TypeIcon = typeConfig.icon;
  const SeverityIcon = severityConfig.icon;

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden transition-all hover:border-brand/30">
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div
              className={classNames(
                "p-2 rounded-lg",
                typeConfig.color.replace("text-", "bg-").replace("600", "100"),
              )}
            >
              <TypeIcon className={classNames("h-5 w-5", typeConfig.color)} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">
                  {insight.title}
                </h4>
                <span
                  className={classNames(
                    "px-2 py-0.5 rounded text-xs font-medium border",
                    severityConfig.color,
                  )}
                >
                  <SeverityIcon className="h-3 w-3 inline mr-1" />
                  {severityConfig.label}
                </span>
                <span
                  className={classNames(
                    "px-2 py-0.5 rounded text-xs font-medium",
                    typeConfig.color
                      .replace("text-", "bg-")
                      .replace("600", "100"),
                  )}
                >
                  {typeConfig.label}
                </span>
              </div>
              <p className="text-sm text-muted mt-1 line-clamp-2">
                {insight.description}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <Target className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-ink">
                {Math.round(insight.confidence * 100)}%
              </span>
              <span className="text-xs text-muted">confidence</span>
            </div>

            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <Zap className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-ink capitalize">
                {insight.impact}
              </span>
              <span className="text-xs text-muted">impact</span>
            </div>

            <div className="flex items-center gap-2 ml-auto">
              {insight.suggested_actions.map((action, i) => (
                <button
                  key={i}
                  className="px-2 py-1 text-xs font-medium text-brand hover:bg-brand/10 rounded transition-colors"
                >
                  {action}
                </button>
              ))}

              {!insight.acknowledged && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onAcknowledge(insight.id);
                  }}
                  className="px-2 py-1 text-xs font-medium text-emerald-600 hover:bg-emerald-100 rounded transition-colors"
                >
                  <Check className="h-3 w-3 inline mr-1" />
                  Acknowledge
                </button>
              )}

              {insight.acknowledged && (
                <span className="px-2 py-1 text-xs font-medium text-emerald-600 bg-emerald-100 rounded">
                  <CheckCircle className="h-3 w-3 inline mr-1" />
                  Acknowledged
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-line flex items-center justify-between text-sm text-muted">
          <span>Metrics: {insight.metrics_affected.join(", ")}</span>
          <span>{new Date(insight.detected_at).toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}

function AnomaliesPanel({
  anomalies,
  searchQuery,
  setSearchQuery,
  severityFilter,
  setSeverityFilter,
  onAcknowledge,
}: {
  anomalies: Anomaly[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  severityFilter: "all" | "critical" | "warning" | "info";
  setSeverityFilter: (s: "all" | "critical" | "warning" | "info") => void;
  onAcknowledge: (id: string) => void;
}) {
  const filtered = useMemo(
    () =>
      anomalies.filter((a) => {
        const matchesSearch = a.metric_name
          .toLowerCase()
          .includes(searchQuery.toLowerCase());
        const matchesSeverity =
          severityFilter === "all" || a.severity === severityFilter;
        return matchesSearch && matchesSeverity;
      }),
    [anomalies, searchQuery, severityFilter],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <Input
          placeholder="Search anomalies..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-64"
        />
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as any)}
          className="bg-canvas border border-line rounded-lg px-3 py-1 text-sm"
        >
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <AlertTriangle className="h-12 w-12 text-muted/30 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-muted mb-2">
            No anomalies found
          </h3>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((anomaly) => (
            <AnomalyCard
              key={anomaly.id}
              anomaly={anomaly}
              onAcknowledge={onAcknowledge}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AnomalyCard({
  anomaly,
  onAcknowledge,
}: {
  anomaly: Anomaly;
  onAcknowledge: (id: string) => void;
}) {
  const severityConfig = {
    critical: {
      color: "bg-red-100 text-red-700 border-red-200",
      icon: AlertCircle,
      label: "Critical",
    },
    warning: {
      color: "bg-amber-100 text-amber-700 border-amber-200",
      icon: AlertTriangle,
      label: "Warning",
    },
    info: {
      color: "bg-blue-100 text-blue-700 border-blue-200",
      icon: Lightbulb,
      label: "Info",
    },
  }[anomaly.severity];

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden transition-all hover:border-brand/30">
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-red-100 text-red-600">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">
                  {anomaly.metric_name}
                </h4>
                <span
                  className={classNames(
                    "px-2 py-0.5 rounded text-xs font-medium border",
                    severityConfig.color,
                  )}
                >
                  <AlertTriangle className="h-3 w-3 inline mr-1" />
                  {severityConfig.label}
                </span>
              </div>
              <p className="text-sm text-muted mt-1">{anomaly.explanation}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <Target className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-ink">
                {Math.round(anomaly.score * 100)}%
              </span>
            </div>

            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <Zap className="h-3 w-3 text-muted" />
              <span className="text-xs font-medium text-ink">
                {anomaly.value.toFixed(4)}
              </span>
              <span className="text-xs text-muted">value</span>
            </div>

            <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-canvas border border-line">
              <span className="text-xs font-medium text-muted">Range:</span>
              <span className="text-xs font-medium text-ink">
                [{anomaly.expected_range[0].toFixed(2)},{" "}
                {anomaly.expected_range[1].toFixed(2)}]
              </span>
            </div>

            <div className="flex items-center gap-2 ml-auto">
              {!anomaly.acknowledged && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onAcknowledge(anomaly.id);
                  }}
                  className="px-2 py-1 text-xs font-medium text-emerald-600 hover:bg-emerald-100 rounded transition-colors"
                >
                  <Check className="h-3 w-3 inline mr-1" />
                  Acknowledge
                </button>
              )}

              {anomaly.acknowledged && (
                <span className="px-2 py-1 text-xs font-medium text-emerald-600 bg-emerald-100 rounded">
                  <CheckCircle className="h-3 w-3 inline mr-1" />
                  Acknowledged
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-line flex items-center justify-between text-sm text-muted">
          <span>{new Date(anomaly.timestamp).toLocaleString()}</span>
          <span>Method: {anomaly.method}</span>
        </div>
      </div>
    </div>
  );
}

function TrendsPanel({
  trends,
  searchQuery,
  setSearchQuery,
}: {
  trends: TrendChange[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}) {
  const filtered = useMemo(
    () =>
      trends.filter((t) =>
        t.metric_name.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [trends, searchQuery],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Input
          placeholder="Search trends..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-64"
        />
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <TrendingUp className="h-12 w-12 text-muted/30 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-muted mb-2">
            No trend changes detected
          </h3>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((trend) => (
            <TrendCard key={trend.id} trend={trend} />
          ))}
        </div>
      )}
    </div>
  );
}

function TrendCard({ trend }: { trend: TrendChange }) {
  const isIncreasing = trend.direction === "increasing";

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden hover:border-brand/30 transition-colors">
      <div className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div
              className={classNames(
                "p-2 rounded-lg",
                isIncreasing
                  ? "bg-emerald-100 text-emerald-600"
                  : "bg-red-100 text-red-600",
              )}
            >
              {isIncreasing ? (
                <TrendingUp className="h-5 w-5" />
              ) : (
                <TrendingDown className="h-5 w-5" />
              )}
            </div>
            <div className="min-w-0">
              <h4 className="font-semibold text-ink truncate">
                {trend.metric_name}
              </h4>
              <p className="text-sm text-muted">
                Trend changed from {trend.before_trend.toFixed(4)} to{" "}
                {trend.after_trend.toFixed(4)} ({trend.direction})
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge tone={isIncreasing ? "success" : "warning"}>
              {trend.direction}
            </Badge>
            <Badge tone="neutral">
              Magnitude: {trend.magnitude.toFixed(4)}
            </Badge>
            <Badge tone="neutral">
              Confidence: {Math.round(trend.confidence * 100)}%
            </Badge>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-4 text-sm text-muted">
            <span>
              Change point: {new Date(trend.change_point).toLocaleString()}
            </span>
            <span>Method: {trend.method}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function AlertsPanel({
  alerts,
  searchQuery,
  setSearchQuery,
}: {
  alerts: Alert[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
}) {
  const filtered = useMemo(
    () =>
      alerts.filter(
        (a) =>
          a.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
          a.message.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [alerts, searchQuery],
  );

  return (
    <div className="space-y-4">
      <Input
        placeholder="Search alerts..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="w-64"
      />

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <Bell className="h-12 w-12 text-muted/30 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-muted mb-2">No alerts</h3>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((alert) => (
            <AlertCard key={alert.id} alert={alert} />
          ))}
        </div>
      )}
    </div>
  );
}

function AlertCard({ alert }: { alert: Alert }) {
  const severityColors = {
    critical: "bg-red-100 text-red-700 border-red-200",
    warning: "bg-amber-100 text-amber-700 border-amber-200",
    info: "bg-blue-100 text-blue-700 border-blue-200",
  }[alert.severity];

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden">
      <div className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div
              className={classNames(
                "px-2 py-1 rounded text-xs font-medium",
                severityColors,
              )}
            >
              {alert.severity.toUpperCase()}
            </div>
            <div className="min-w-0">
              <h4 className="font-semibold text-ink truncate">
                {alert.subject}
              </h4>
              <p className="text-sm text-muted truncate">{alert.message}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="px-2 py-1 rounded text-xs font-medium bg-canvas border border-line">
              {alert.channel.toUpperCase()}
            </span>
            <span className="px-2 py-1 rounded text-xs font-medium bg-canvas border border-line">
              {alert.sent ? "Sent" : "Pending"}
            </span>
            {alert.sent_at && (
              <span className="text-xs text-muted">
                {new Date(alert.sent_at).toLocaleString()}
              </span>
            )}
          </div>
        </div>

        {alert.error && (
          <div className="mt-3 p-3 rounded-lg bg-red-50 border border-red-200">
            <p className="text-sm text-red-800">Error: {alert.error}</p>
            <p className="text-xs text-red-600 mt-1">
              Retries: {alert.retry_count}
            </p>
          </div>
        )}

        <div className="mt-3 pt-3 border-t border-line text-sm text-muted">
          <span>Insight: {alert.insight_id}</span>
        </div>
      </div>
    </div>
  );
}

function RulesPanel({
  rules,
  onCreate,
  onRefresh,
}: {
  rules: AlertRule[];
  onCreate: () => void;
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-ink">Alert Rules</h3>
          <p className="text-sm text-muted">
            {rules.length} rule{rules.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4 mr-1" /> New Rule
        </Button>
      </div>

      {rules.length === 0 ? (
        <Card className="p-8 text-center">
          <Settings className="h-12 w-12 text-muted/30 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-muted mb-2">
            No alert rules yet
          </h3>
          <p className="text-faint max-w-md mx-auto mb-4">
            Create your first alert rule to get notified about anomalies and
            trends
          </p>
          <Button onClick={onCreate}>
            <Plus className="h-4 w-4 mr-1" /> Create Rule
          </Button>
        </Card>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => (
            <RuleCard key={rule.id} rule={rule} />
          ))}
        </div>
      )}
    </div>
  );
}

function RuleCard({ rule }: { rule: AlertRule }) {
  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden hover:border-brand/30 transition-colors">
      <div className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Settings className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h4 className="font-semibold text-ink truncate">{rule.name}</h4>
              <p className="text-sm text-muted">
                {rule.metric_patterns.join(", ") || "All metrics"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge tone="neutral">{rule.severity_threshold}</Badge>
            <Badge tone="neutral">{rule.channels.join(", ")}</Badge>
            <Badge tone={rule.enabled ? "success" : "neutral"}>
              {rule.enabled ? "Enabled" : "Disabled"}
            </Badge>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between text-sm text-muted">
          <span>Cooldown: {rule.cooldown_minutes} min</span>
          <span>
            Recipients: {Object.values(rule.recipients).flat().length}
          </span>
        </div>
      </div>
    </div>
  );
}

function StatusPanel({
  status,
  isMonitoring,
  onStart,
  onStop,
}: {
  status: any;
  isMonitoring: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  return (
    <div className="space-y-6">
      <Card
        title="Monitoring Status"
        subtitle={
          isMonitoring ? "Active monitoring in progress" : "Monitoring stopped"
        }
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div
              className={classNames(
                "p-3 rounded-full",
                isMonitoring
                  ? "bg-emerald-100 text-emerald-600"
                  : "bg-amber-100 text-amber-600",
              )}
            >
              {isMonitoring ? (
                <Zap className="h-6 w-6" />
              ) : (
                <BellOff className="h-6 w-6" />
              )}
            </div>
            <div>
              <h3 className="font-semibold text-ink">
                {isMonitoring ? "Monitoring Active" : "Monitoring Stopped"}
              </h3>
              <p className="text-sm text-muted">
                Auto-refresh every 30 seconds
              </p>
            </div>
          </div>
          <Button
            onClick={isMonitoring ? onStop : onStart}
            variant={isMonitoring ? "destructive" : "default"}
            className="px-4 py-2"
          >
            {isMonitoring ? (
              <>
                {" "}
                <BellOff className="h-4 w-4 mr-1" /> Stop Monitoring{" "}
              </>
            ) : (
              <>
                {" "}
                <Zap className="h-4 w-4 mr-1" /> Start Monitoring{" "}
              </>
            )}
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            label="Metrics Monitored"
            value={status.metrics_monitored || 0}
            icon={Database}
            color="bg-brand/10 text-brand"
          />
          <StatCard
            label="Total Insights"
            value={status.total_insights || 0}
            icon={Lightbulb}
            color="bg-blue-100 text-blue-600"
          />
          <StatCard
            label="Total Anomalies"
            value={status.total_anomalies || 0}
            icon={AlertTriangle}
            color="bg-red-100 text-red-600"
          />
          <StatCard
            label="Total Trends"
            value={status.total_trend_changes || 0}
            icon={TrendingUp}
            color="bg-emerald-100 text-emerald-600"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            label="Unacked Insights"
            value={status.unacknowledged_insights || 0}
            icon={Lightbulb}
            color="bg-amber-100 text-amber-600"
          />
          <StatCard
            label="Unacked Anomalies"
            value={status.unacknowledged_anomalies || 0}
            icon={AlertTriangle}
            color="bg-red-100 text-red-600"
          />
          <StatCard
            label="Total Alerts"
            value={status.total_alerts || 0}
            icon={Bell}
            color="bg-purple-100 text-purple-600"
          />
          <StatCard
            label="Rules Active"
            value={status.active_rules || 0}
            icon={Settings}
            color="bg-brand/10 text-brand"
          />
        </div>
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) {
  return (
    <div className="p-4 rounded-xl bg-canvas border border-line">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={classNames("p-2 rounded-lg", color)}>
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-muted">{label}</p>
            <p className="text-lg font-bold text-ink">{value}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
