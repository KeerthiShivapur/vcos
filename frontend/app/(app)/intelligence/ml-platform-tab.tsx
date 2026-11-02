"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  Search,
  Filter,
  Download,
  Upload,
  RefreshCw,
  Loader2,
  BarChart2,
  TrendingUp,
  TrendingDown,
  Target,
  Settings,
  Play,
  Pause,
  Square,
  RotateCcw,
  LineChart,
  X,
  AlertTriangle,
  Trash2,
  Database,
  Eye,
  Zap,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  Filter as FilterIcon,
  GitBranch,
  Network,
  Link2,
  FlaskConical,
  Microscope,
  Brain,
  ArrowRight,
  ArrowLeft,
  Target as TargetIcon,
  Calendar,
  Clock,
  DollarSign,
  Percent,
  Activity,
  Thermometer,
  Gauge,
  CheckCircle,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import {
  Table,
  TableHeader,
  TableRow,
  TableCell,
} from "@/components/ui/Table";
import { Modal } from "@/components/ui/Modal";
import { Textarea } from "@/components/ui/Textarea";
import { classNames } from "@/lib/utils";

interface ForecastingTabProps {
  organizationId: string;
  className?: string;
}

export function ForecastingTab({
  organizationId,
  className,
}: ForecastingTabProps) {
  const [activeTab, setActiveTab] = useState<
    "models" | "forecast" | "anomaly" | "models-list"
  >("models");
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<
    Array<{
      id: string;
      name: string;
      model_type: string;
      algorithm: string;
      version: string;
      status: string;
      metrics: any;
      created_at: string;
      trained_at: string | null;
    }>
  >([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newModel, setNewModel] = useState({
    name: "",
    algorithm: "prophet",
    model_type: "forecaster",
    config: {},
  });
  const [forecastParams, setForecastParams] = useState({
    periods: 30,
    freq: "D",
  });
  const [forecastResult, setForecastResult] = useState<any>(null);
  const [anomalyParams, setAnomalyParams] = useState({
    contamination: 0.1,
    data: "",
  });
  const [anomalyResult, setAnomalyResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchModels = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const response = await fetch(`/api/v1/ml/models`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setModels(data);
      } else {
        setError("Failed to load models");
      }
    } catch (error) {
      console.error("Failed to load models:", error);
      setError("Failed to load models");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const handleCreateModel = async () => {
    if (!newModel.name.trim()) return;
    setError(null);
    try {
      const response = await fetch(`/api/v1/ml/models/${newModel.model_type}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          name: newModel.name,
          algorithm: newModel.algorithm,
          config: newModel.config,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to create model");
      }
      const model = await response.json();
      setModels((prev) => [model, ...prev]);
      setShowCreateModal(false);
      setNewModel({
        name: "",
        algorithm: "prophet",
        model_type: "forecaster",
        config: {},
      });
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Failed to create model",
      );
    }
  };

  const handleForecast = async () => {
    if (!selectedModel) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/v1/ml/models/${selectedModel}/forecast`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({
            periods: forecastParams.periods,
            freq: forecastParams.freq,
          }),
        },
      );
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Forecast failed");
      }
      const result = await response.json();
      setForecastResult(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Forecast failed");
    } finally {
      setLoading(false);
    }
  };

  const handleAnomalyDetection = async () => {
    if (!selectedModel) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/v1/ml/models/${selectedModel}/anomaly`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ contamination: anomalyParams.contamination }),
        },
      );
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Anomaly detection failed");
      }
      const result = await response.json();
      setAnomalyResult(result);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Anomaly detection failed",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    if (!confirm("Are you sure you want to delete this model?")) return;
    try {
      const response = await fetch(`/api/v1/ml/models/${modelId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (!response.ok) throw new Error("Failed to delete model");
      setModels((prev) => prev.filter((m) => m.id !== modelId));
      if (selectedModel === modelId) setSelectedModel(null);
    } catch (error) {
      console.error("Failed to delete model:", error);
      alert("Failed to delete model");
    }
  };

  return (
    <div className={classNames("space-y-6", className)}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink">ML Platform</h2>
          <p className="text-muted text-sm mt-1">
            Forecasting, anomaly detection & model management
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchModels}
            disabled={isRefreshing}
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Model
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="models" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="models" className="py-2 flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Train Models
          </TabsTrigger>
          <TabsTrigger
            value="forecast"
            className="py-2 flex items-center gap-2"
          >
            <TrendingUp className="h-4 w-4" />
            Forecast
          </TabsTrigger>
          <TabsTrigger value="anomaly" className="py-2 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Anomaly Detection
          </TabsTrigger>
          <TabsTrigger
            value="models-list"
            className="py-2 flex items-center gap-2"
          >
            <Database className="h-4 w-4" />
            Model Registry
          </TabsTrigger>
        </TabsList>

        {/* Train Models Tab */}
        <TabsContent value="models" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Train New Model</h3>
              <p className="text-sm text-muted">
                Train a new ML model with your data
              </p>
            </div>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Train New Model
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Forecast Model Card */}
            <Card
              className="p-4 border-2 border-line hover:border-brand/50 transition-colors cursor-pointer"
              onClick={() =>
                setNewModel({
                  ...newModel,
                  model_type: "forecaster",
                  algorithm: "prophet",
                })
              }
            >
              <div className="flex items-center justify-between mb-3">
                <div className="p-2 bg-brand/10 rounded-lg">
                  <TrendingUp className="h-5 w-5 text-brand" />
                </div>
                <Badge tone="neutral" className="text-xs">
                  Prophet
                </Badge>
              </div>
              <h3 className="font-medium text-ink mb-1">
                Time Series Forecasting
              </h3>
              <p className="text-sm text-muted mb-3">
                Facebook Prophet forecasting with seasonality, trends, and
                holidays
              </p>
              <div className="flex items-center gap-2 text-xs text-muted">
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    Time Series
                  </Badge>
                </span>
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    Multivariate
                  </Badge>
                </span>
              </div>
            </Card>

            {/* Anomaly Detection Card */}
            <Card
              className="p-4 border-2 border-line hover:border-brand/50 transition-colors cursor-pointer"
              onClick={() =>
                setNewModel({
                  ...newModel,
                  model_type: "anomaly_detector",
                  algorithm: "isolation_forest",
                })
              }
            >
              <div className="flex items-center justify-between mb-3">
                <div className="p-2 bg-red-100 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-red-600" />
                </div>
                <Badge tone="neutral" className="text-xs">
                  Isolation Forest
                </Badge>
              </div>
              <h3 className="font-medium text-ink mb-1">Anomaly Detection</h3>
              <p className="text-sm text-muted mb-3">
                Isolation Forest for multivariate anomaly detection
              </p>
              <div className="flex items-center gap-2 text-xs text-muted">
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    Unsupervised
                  </Badge>
                </span>
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    Real-time
                  </Badge>
                </span>
              </div>
            </Card>

            {/* Custom Model Card */}
            <Card
              className="p-4 border-2 border-line hover:border-brand/50 transition-colors cursor-pointer"
              onClick={() =>
                setNewModel({
                  ...newModel,
                  model_type: "custom",
                  algorithm: "custom",
                })
              }
            >
              <div className="flex items-center justify-between mb-3">
                <div className="p-2 bg-muted rounded-lg">
                  <Zap className="h-5 w-5 text-muted" />
                </div>
                <Badge tone="neutral" className="text-xs">
                  Custom
                </Badge>
              </div>
              <h3 className="font-medium text-ink mb-1">Custom Model</h3>
              <p className="text-sm text-muted mb-3">
                Bring your own model (ONNX, PyTorch, TensorFlow)
              </p>
              <div className="flex items-center gap-2 text-xs text-muted">
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    ONNX
                  </Badge>
                </span>
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    PyTorch
                  </Badge>
                </span>
                <span className="flex items-center gap-1">
                  <Badge tone="neutral" className="text-xs">
                    TensorFlow
                  </Badge>
                </span>
              </div>
            </Card>
          </div>

          {/* Create Model Modal */}
          {showCreateModal && (
            <Modal
              open={showCreateModal}
              onClose={() => setShowCreateModal(false)}
              title="Train New Model"
              size="lg"
            >
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Model Name *
                    </label>
                    <Input
                      value={newModel.name}
                      onChange={(e) =>
                        setNewModel({ ...newModel, name: e.target.value })
                      }
                      placeholder="e.g., monthly_revenue_forecast"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Model Type *
                    </label>
                    <select
                      value={newModel.model_type}
                      onChange={(e) =>
                        setNewModel({ ...newModel, model_type: e.target.value })
                      }
                      className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
                    >
                      <option value="forecaster">Forecaster</option>
                      <option value="anomaly_detector">Anomaly Detector</option>
                      <option value="custom">Custom</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Algorithm
                    </label>
                    <select
                      value={newModel.algorithm}
                      onChange={(e) =>
                        setNewModel({ ...newModel, algorithm: e.target.value })
                      }
                      className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
                    >
                      {newModel.model_type === "forecaster" && (
                        <>
                          <option value="prophet">Prophet (Recommended)</option>
                          <option value="neuralprophet">NeuralProphet</option>
                          <option value="arima">ARIMA</option>
                        </>
                      )}
                      {newModel.model_type === "anomaly_detector" && (
                        <>
                          <option value="isolation_forest">
                            Isolation Forest
                          </option>
                          <option value="lof">Local Outlier Factor</option>
                        </>
                      )}
                      {newModel.model_type === "custom" && (
                        <>
                          <option value="onnx">ONNX</option>
                          <option value="pytorch">PyTorch</option>
                          <option value="tensorflow">TensorFlow</option>
                        </>
                      )}
                    </select>
                  </div>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium text-ink mb-1">
                    Configuration (JSON)
                  </label>
                  <Textarea
                    value={JSON.stringify(newModel.config, null, 2)}
                    onChange={(e) => {
                      try {
                        setNewModel({
                          ...newModel,
                          config: JSON.parse(e.target.value),
                        });
                      } catch {
                        // Ignore invalid JSON while typing
                      }
                    }}
                    rows={6}
                    className="font-mono text-sm"
                    placeholder='{"seasonality_mode": "multiplicative", "yearly_seasonality": true}'
                  />
                </div>

                <div className="flex justify-end gap-2 pt-4 border-t border-line">
                  <Button
                    variant="secondary"
                    onClick={() => setShowCreateModal(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleCreateModel}
                    disabled={!newModel.name.trim() || loading}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Train Model
                  </Button>
                </div>
              </div>
            </Modal>
          )}
        </TabsContent>

        {/* Forecast Tab */}
        <TabsContent value="forecast" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Generate Forecast</h3>
              <p className="text-sm text-muted">
                Generate forecasts using trained models
              </p>
            </div>
            <Button
              onClick={handleForecast}
              disabled={!selectedModel || loading}
              className="ml-auto"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Generating...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <TrendingUp className="h-4 w-4" /> Generate Forecast
                </span>
              )}
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Select Model
              </label>
              <select
                value={selectedModel || ""}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="">Select a forecasting model...</option>
                {models
                  .filter((m) => m.model_type === "forecaster")
                  .map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.algorithm})
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Periods
              </label>
              <input
                type="number"
                value={forecastParams.periods}
                onChange={(e) =>
                  setForecastParams({
                    ...forecastParams,
                    periods: parseInt(e.target.value) || 30,
                  })
                }
                min={1}
                max={365}
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Frequency
              </label>
              <select
                value={forecastParams.freq}
                onChange={(e) =>
                  setForecastParams({ ...forecastParams, freq: e.target.value })
                }
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="D">Daily (D)</option>
                <option value="W">Weekly (W)</option>
                <option value="M">Monthly (M)</option>
                <option value="H">Hourly (H)</option>
              </select>
            </div>
          </div>

          {forecastResult && (
            <Card className="p-4">
              <h3 className="font-medium mb-4">Forecast Results</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Model</p>
                  <p className="font-medium">{forecastResult.model_name}</p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Periods</p>
                  <p className="font-medium">{forecastResult.periods}</p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Frequency</p>
                  <p className="font-medium">{forecastResult.freq}</p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Metrics</p>
                  <p className="font-medium text-xs">
                    {JSON.stringify(forecastResult.metrics || {}, null, 2)}
                  </p>
                </div>
              </div>

              <div className="space-y-2 max-h-96 overflow-y-auto">
                <h4 className="font-medium mb-2">Forecast Values</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted border-b border-line">
                        <th className="pb-2 pr-4">Timestamp</th>
                        <th className="pb-2 pr-4">Value</th>
                        <th className="pb-2 pr-4">Lower Bound</th>
                        <th className="pb-2 pr-4">Upper Bound</th>
                      </tr>
                    </thead>
                    <tbody>
                      {forecastResult.timestamps?.map(
                        (ts: string, i: number) => (
                          <tr key={i} className="border-b border-line/50">
                            <td className="py-2 pr-4 font-mono text-sm">
                              {new Date(ts).toLocaleString()}
                            </td>
                            <td className="py-2 pr-4 font-mono text-sm">
                              {forecastResult.values?.[i]?.toFixed(4)}
                            </td>
                            <td className="py-2 pr-4 font-mono text-sm text-muted">
                              {forecastResult.lower_bound?.[i]?.toFixed(4)}
                            </td>
                            <td className="py-2 pr-4 font-mono text-sm text-muted">
                              {forecastResult.upper_bound?.[i]?.toFixed(4)}
                            </td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </Card>
          )}
        </TabsContent>

        {/* Anomaly Detection Tab */}
        <TabsContent value="anomaly" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Anomaly Detection</h3>
              <p className="text-sm text-muted">
                Detect anomalies in your time series data
              </p>
            </div>
            <Button
              onClick={handleAnomalyDetection}
              disabled={!selectedModel || loading}
              className="ml-auto"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Detecting...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" /> Detect Anomalies
                </span>
              )}
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Select Model
              </label>
              <select
                value={selectedModel || ""}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="">Select an anomaly detection model...</option>
                {models
                  .filter((m) => m.model_type === "anomaly_detector")
                  .map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.algorithm})
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Contamination
              </label>
              <input
                type="number"
                value={anomalyParams.contamination}
                onChange={(e) =>
                  setAnomalyParams({
                    ...anomalyParams,
                    contamination: parseFloat(e.target.value) || 0.1,
                  })
                }
                min={0.01}
                max={0.5}
                step={0.01}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-ink mb-1">
              Time Series Data (comma-separated values)
            </label>
            <textarea
              value={anomalyParams.data || ""}
              onChange={(e) =>
                setAnomalyParams({ ...anomalyParams, data: e.target.value })
              }
              rows={6}
              placeholder="1.2, 1.3, 1.1, 1.4, 1.2, 5.0, 1.1, 1.3, 1.2, 1.4..."
              className="w-full px-4 py-2 border border-line rounded-lg bg-canvas font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand"
            />
            <p className="text-xs text-muted mt-1">
              Enter comma-separated numeric values for anomaly detection
            </p>
          </div>

          <Button
            onClick={handleAnomalyDetection}
            disabled={!selectedModel || loading || !anomalyParams.data?.trim()}
            className="w-full"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Detecting...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> Detect Anomalies
              </span>
            )}
          </Button>

          {anomalyResult && (
            <Card className="p-4 mt-4">
              <h3 className="font-medium mb-4">Anomaly Detection Results</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Total Points</p>
                  <p className="font-medium">{anomalyResult.data_points}</p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Anomalies Found</p>
                  <p className="font-medium text-red-600">
                    {anomalyResult.anomaly_count}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Threshold</p>
                  <p className="font-medium">
                    {anomalyResult.threshold?.toFixed(4)}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Anomaly Rate</p>
                  <p className="font-medium text-red-600">
                    {(
                      (anomalyResult.anomaly_count /
                        anomalyResult.data_points) *
                      100
                    ).toFixed(2)}
                    %
                  </p>
                </div>
              </div>

              {anomalyResult.is_anomaly &&
              anomalyResult.is_anomaly.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  <h4 className="font-medium mb-2">Detected Anomalies</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-muted border-b border-line">
                          <th className="pb-2 pr-4">Index</th>
                          <th className="pb-2 pr-4">Value</th>
                          <th className="pb-2 pr-4">Anomaly</th>
                          <th className="pb-2 pr-4">Score</th>
                        </tr>
                      </thead>
                      <tbody>
                        {anomalyResult.is_anomaly.map(
                          (anomaly: boolean, i: number) =>
                            anomaly ? (
                              <tr key={i} className="border-b border-line/50">
                                <td className="py-2 pr-4 font-mono text-sm">
                                  {i}
                                </td>
                                <td className="py-2 pr-4 font-mono text-sm">
                                  {anomalyResult.values?.[i]?.toFixed(4)}
                                </td>
                                <td className="py-2 pr-4">
                                  <Badge tone="danger">Anomaly</Badge>
                                </td>
                                <td className="py-2 pr-4 font-mono text-sm">
                                  {anomalyResult.scores?.[i]?.toFixed(4)}
                                </td>
                              </tr>
                            ) : null,
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </Card>
          )}
        </TabsContent>

        {/* Model Registry Tab */}
        <TabsContent value="models-list" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Model Registry</h3>
              <p className="text-sm text-muted">
                Manage and track all trained models
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchModels}
              disabled={isRefreshing}
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
              />
              Refresh
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand border-t-transparent" />
            </div>
          ) : models.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <Database className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">No models yet</h3>
              <p className="text-muted text-sm mb-4">
                Train your first model to get started
              </p>
              <Button
                onClick={() => {
                  setActiveTab("models");
                  setShowCreateModal(true);
                }}
              >
                <Plus className="h-4 w-4 mr-1" />
                Train First Model
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-line">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Type</th>
                    <th className="pb-2 pr-4">Algorithm</th>
                    <th className="pb-2 pr-4">Version</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Created</th>
                    <th className="pb-2 pr-4">Trained</th>
                    <th className="pb-2 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((model) => (
                    <tr
                      key={model.id}
                      className="border-b border-line/50 hover:bg-muted/50"
                    >
                      <td className="py-3 pr-4 font-medium text-sm">
                        {model.name}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge tone="neutral" className="text-xs">
                          {model.model_type}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm">{model.algorithm}</td>
                      <td className="py-3 pr-4 text-sm">{model.version}</td>
                      <td className="py-3 pr-4">
                        <Badge
                          tone={
                            model.status === "active"
                              ? "success"
                              : model.status === "training"
                                ? "warning"
                                : "neutral"
                          }
                        >
                          {model.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm text-muted">
                        {new Date(model.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 pr-4 text-sm text-muted">
                        {model.trained_at
                          ? new Date(model.trained_at).toLocaleDateString()
                          : "Never"}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedModel(model.id);
                              setActiveTab("forecast");
                            }}
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Forecast
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedModel(model.id);
                              setActiveTab("anomaly");
                            }}
                          >
                            <AlertTriangle className="h-3.5 w-3.5" />
                            Anomaly
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-700"
                            onClick={() => handleDeleteModel(model.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
