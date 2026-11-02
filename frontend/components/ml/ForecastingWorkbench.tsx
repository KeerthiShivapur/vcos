"use client";

/**
 * Forecasting Workbench
 * Configure and run time series forecasts with multiple methods
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useForecasting } from "@/hooks/useMLPlatform";
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
  Calendar,
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
  Stop,
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
} from "lucide-react";
import { classNames } from "@/lib/utils";
import {
  ForecastMethod,
  Frequency,
  TimeSeriesDataPoint,
  RegisterForecastDataRequest,
  ForecastRequest,
  ForecastResult,
  ModelEvaluation,
} from "@/hooks/useMLPlatform";

/**
 * Evaluate Panel - Stub component for model evaluation
 */
interface EvaluatePanelProps {
  dataSources: any[];
  forecastRequest: any;
  setForecastRequest: (r: any) => void;
  evaluationResults: any;
  evaluating: boolean;
  onEvaluate: () => void;
}

function EvaluatePanel({
  dataSources,
  forecastRequest,
  setForecastRequest,
  evaluationResults,
  evaluating,
  onEvaluate,
}: EvaluatePanelProps) {
  return (
    <Card className="p-6">
      <div className="text-center text-muted py-12">
        <div className="h-12 w-12 mx-auto mb-4 rounded-full bg-muted flex items-center justify-center">
          <BarChart2 className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-medium mb-2">Model Evaluation</h3>
        <p className="mb-4">
          Configure and run model evaluations against your forecast data.
        </p>
        <Button onClick={onEvaluate} disabled={evaluating}>
          {evaluating ? "Evaluating..." : "Run Evaluation"}
        </Button>
      </div>
    </Card>
  );
}

/**
 * Anomaly Panel - Stub component for anomaly detection
 */
interface AnomalyPanelProps {
  dataSources: any[];
  anomalyResults: any;
  detecting: boolean;
  onDetect: () => void;
  forecastRequest: any;
  setForecastRequest: (r: any) => void;
}

function AnomalyPanel({
  dataSources,
  anomalyResults,
  detecting,
  onDetect,
  forecastRequest,
  setForecastRequest,
}: AnomalyPanelProps) {
  return (
    <Card className="p-6">
      <div className="text-center text-muted py-12">
        <div className="h-12 w-12 mx-auto mb-4 rounded-full bg-muted flex items-center justify-center">
          <AlertTriangle className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-medium mb-2">Anomaly Detection</h3>
        <p className="mb-4">
          Detect anomalies in your time series data using various methods.
        </p>
        <Button onClick={onDetect} disabled={detecting}>
          {detecting ? "Detecting..." : "Run Anomaly Detection"}
        </Button>
      </div>
    </Card>
  );
}

interface ForecastingWorkbenchProps {
  organizationId: string;
  className?: string;
}

export function ForecastingWorkbench({
  organizationId,
  className,
}: ForecastingWorkbenchProps) {
  const {
    dataSources,
    loading,
    error,
    registerData,
    listData,
    forecast,
    evaluate,
    detectAnomalies,
  } = useForecasting();

  const [activeTab, setActiveTab] = useState<
    "data" | "forecast" | "evaluate" | "anomaly"
  >("data");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedData, setSelectedData] = useState<any | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Forecast form state
  const [forecastRequest, setForecastRequest] = useState({
    data_name: "",
    horizon: 30,
    method: "prophet" as "prophet",
    frequency: "D" as "D",
    confidence_level: 0.95,
    params: {},
    include_history: false,
  });

  // Register data state
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [registerRequest, setRegisterRequest] = useState({
    name: "",
    data: [] as TimeSeriesDataPoint[],
    date_col: "ds",
    value_col: "y",
  });
  const [csvFile, setCsvFile] = useState<File | null>(null);

  // Evaluation state
  const [evaluationResults, setEvaluationResults] = useState<any>(null);
  const [evaluating, setEvaluating] = useState(false);

  // Anomaly detection state
  const [anomalyResults, setAnomalyResults] = useState<any>(null);
  const [detectingAnomalies, setDetectingAnomalies] = useState(false);

  // Forecast results
  const [forecastResult, setForecastResult] = useState<any | null>(null);
  const [forecasting, setForecasting] = useState(false);

  // Chart data for visualization
  const chartData = useMemo(() => {
    if (!forecastResult || !selectedData) return null;

    const historical = selectedData.data;
    const forecast = forecastResult.forecast;
    const timestamps = forecastResult.timestamps;
    const lower = forecastResult.lower_bound;
    const upper = forecastResult.upper_bound;

    return {
      historical: historical.slice(-50).map((d: any) => ({
        x: d.timestamp,
        y: d.value,
      })),
      forecast: timestamps.map((t: string, i: number) => ({
        x: t,
        y: forecast[i],
        lower: forecastResult.lower_bound?.[i],
        upper: forecastResult.upper_bound?.[i],
      })),
    };
  }, [forecastResult, selectedData]);

  const fetchData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await listData();
    } finally {
      setIsRefreshing(false);
    }
  }, [listData]);

  useEffect(() => {
    listData();
  }, [listData]);

  const handleRegisterData = async (e: React.FormEvent) => {
    e.preventDefault();
    await registerData(registerRequest);
    setShowRegisterModal(false);
    setRegisterRequest({ name: "", data: [], date_col: "ds", value_col: "y" });
    setCsvFile(null);
    listData();
  };

  const handleCsvUpload = async (file: File) => {
    setCsvFile(file);
    const text = await file.text();
    const lines = text.trim().split("\n");
    const headers = lines[0].split(",").map((h) => h.trim());
    const dateColIdx = headers.findIndex(
      (h) =>
        h.toLowerCase() === "ds" ||
        h.toLowerCase() === "date" ||
        h.toLowerCase() === "timestamp",
    );
    const valueColIdx = headers.findIndex(
      (h) =>
        h.toLowerCase() === "y" ||
        h.toLowerCase() === "value" ||
        h.toLowerCase() === "target",
    );

    if (dateColIdx === -1 || valueColIdx === -1) {
      alert(
        "CSV must contain 'ds'/'date'/'timestamp' and 'y'/'value'/'target' columns",
      );
      return;
    }

    const data = lines
      .slice(1)
      .map((line) => {
        const values = line.split(",").map((v) => v.trim());
        return {
          timestamp: values[dateColIdx],
          value: parseFloat(values[valueColIdx]),
          metadata: {},
        };
      })
      .filter((d) => !isNaN(d.value));

    setRegisterRequest((prev) => ({ ...prev, data }));
  };

  const handleForecast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!forecastRequest.data_name) return;

    setForecasting(true);
    try {
      const result = await forecast(forecastRequest);
      setForecastResult(result);
    } catch (err) {
      console.error("Forecast failed:", err);
    } finally {
      setForecasting(false);
    }
  };

  const handleEvaluate = async () => {
    if (!forecastRequest.data_name) return;
    setEvaluating(true);
    try {
      const results = await evaluate({
        data_name: forecastRequest.data_name,
        horizon: forecastRequest.horizon,
        methods: ["prophet", "arima", "random_forest", "gradient_boosting"],
        test_size: 0.2,
      });
      setEvaluationResults(results);
    } catch (err) {
      console.error("Evaluation failed:", err);
    } finally {
      setEvaluating(false);
    }
  };

  const handleDetectAnomalies = async () => {
    if (!forecastRequest.data_name) return;
    setDetectingAnomalies(true);
    try {
      const result = await detectAnomalies(
        forecastRequest.data_name,
        "ensemble",
        0.05,
      );
      setAnomalyResults(result);
    } catch (err) {
      console.error("Anomaly detection failed:", err);
    } finally {
      setDetectingAnomalies(false);
    }
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
              <LineChart className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">
                Forecasting Workbench
              </h2>
              <p className="text-sm text-muted">
                Time series forecasting with multiple methods & evaluation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => listData()}
              disabled={isRefreshing}
              className="p-2 rounded-lg bg-canvas border border-line text-ink hover:bg-muted transition-colors"
              title="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </button>

            <button
              onClick={() => setShowRegisterModal(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Register Data</span>
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-4 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="data" className="py-2 flex items-center gap-2">
            <Database className="h-4 w-4" />
            Data Sources
          </TabsTrigger>
          <TabsTrigger
            value="forecast"
            className="py-2 flex items-center gap-2"
          >
            <TrendingUp className="h-4 w-4" />
            Forecast
          </TabsTrigger>
          <TabsTrigger
            value="evaluate"
            className="py-2 flex items-center gap-2"
          >
            <Target className="h-4 w-4" />
            Evaluate
          </TabsTrigger>
          <TabsTrigger value="anomaly" className="py-2 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            Anomaly Detection
          </TabsTrigger>
        </TabsList>

        {/* Data Sources Tab */}
        <TabsContent value="data" className="flex-1 p-4 overflow-auto">
          <DataSourcesPanel
            dataSources={dataSources}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            loading={loading}
            onRefresh={listData}
            onRegister={setShowRegisterModal}
          />
        </TabsContent>

        {/* Forecast Tab */}
        <TabsContent value="forecast" className="flex-1 p-4 overflow-auto">
          <ForecastPanel
            dataSources={dataSources}
            forecastRequest={forecastRequest}
            setForecastRequest={setForecastRequest}
            forecastResult={forecastResult}
            forecasting={forecasting}
            onForecast={handleForecast}
            chartData={chartData}
            selectedData={selectedData}
          />
        </TabsContent>

        {/* Evaluate Tab */}
        <TabsContent value="evaluate" className="flex-1 p-4 overflow-auto">
          <EvaluatePanel
            dataSources={dataSources}
            forecastRequest={forecastRequest}
            setForecastRequest={setForecastRequest}
            evaluationResults={evaluationResults}
            evaluating={evaluating}
            onEvaluate={handleEvaluate}
          />
        </TabsContent>

        {/* Anomaly Detection Tab */}
        <TabsContent value="anomaly" className="flex-1 p-4 overflow-auto">
          <AnomalyPanel
            dataSources={dataSources}
            anomalyResults={anomalyResults}
            detecting={detectingAnomalies}
            onDetect={handleDetectAnomalies}
            forecastRequest={forecastRequest}
            setForecastRequest={setForecastRequest}
          />
        </TabsContent>
      </Tabs>

      {/* Register Data Modal */}
      <Modal
        open={showRegisterModal}
        onClose={() => setShowRegisterModal(false)}
        title="Register Time Series Data"
        size="lg"
      >
        <form
          onSubmit={handleRegisterData}
          className="space-y-4 max-h-[80vh] overflow-y-auto"
        >
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Data Source Name *
            </label>
            <Input
              value={registerRequest.name}
              onChange={(e) =>
                setRegisterRequest({ ...registerRequest, name: e.target.value })
              }
              placeholder="e.g., daily_revenue, weekly_active_users"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Date Column
              </label>
              <Input
                value={registerRequest.date_col}
                onChange={(e) =>
                  setRegisterRequest({
                    ...registerRequest,
                    date_col: e.target.value,
                  })
                }
                placeholder="ds"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Value Column
              </label>
              <Input
                value={registerRequest.value_col}
                onChange={(e) =>
                  setRegisterRequest({
                    ...registerRequest,
                    value_col: e.target.value,
                  })
                }
                placeholder="y"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Upload CSV
            </label>
            <div className="border-2 border-dashed border-line rounded-lg p-6 text-center">
              <input
                type="file"
                accept=".csv"
                onChange={(e) =>
                  e.target.files?.[0] && handleCsvUpload(e.target.files[0])
                }
                className="hidden"
                id="csv-upload"
                ref={(el) => {
                  if (el) el.style.display = "none";
                }}
              />
              <label
                htmlFor="csv-upload"
                className="cursor-pointer flex flex-col items-center gap-2"
              >
                <Upload className="h-8 w-8 text-muted" />
                <span className="text-sm text-muted">
                  Drag & drop CSV or click to browse
                </span>
                <span className="text-xs text-faint">
                  Columns: ds/date/timestamp, y/value/target
                </span>
              </label>
              {csvFile && (
                <div className="mt-2 p-2 bg-brand/5 border border-brand/20 rounded text-sm text-brand">
                  Selected: {csvFile.name} ({Math.round(csvFile.size / 1024)}{" "}
                  KB)
                </div>
              )}
            </div>
          </div>
          {registerRequest.data.length > 0 && (
            <div className="p-3 bg-canvas border border-line rounded">
              <p className="text-sm font-medium text-ink mb-1">
                Preview ({registerRequest.data.length} rows):
              </p>
              <div className="overflow-x-auto text-xs font-mono">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-line">
                      <th className="p-1">Timestamp</th>
                      <th className="p-1">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {registerRequest.data.slice(0, 5).map((d, i) => (
                      <tr key={i}>
                        <td className="p-1">{d.timestamp}</td>
                        <td className="p-1">{d.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {registerRequest.data.length > 5 && (
                <p className="text-xs text-muted mt-1">
                  ... and {registerRequest.data.length - 5} more rows
                </p>
              )}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setShowRegisterModal(false);
                setRegisterRequest({
                  name: "",
                  data: [],
                  date_col: "ds",
                  value_col: "y",
                });
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                !registerRequest.name || registerRequest.data.length === 0
              }
            >
              Register Data
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

function DataSourcesPanel({
  dataSources,
  searchQuery,
  setSearchQuery,
  loading,
  onRefresh,
  onRegister,
}: {
  dataSources: any[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  loading: boolean;
  onRefresh: () => void;
  onRegister: () => void;
}) {
  const filtered = useMemo(
    () =>
      dataSources.filter(
        (d) =>
          d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          JSON.stringify(d).toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [dataSources, searchQuery],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search data sources..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-64"
          />
          <Button onClick={onRefresh} variant="outline" disabled={loading}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button onClick={onRegister}>
            <Plus className="h-4 w-4 mr-1" /> Register Data
          </Button>
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Database className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No data sources registered
            </h3>
            <p className="text-faint max-w-md mx-auto">
              Register your first time series to start forecasting
            </p>
            <Button onClick={onRegister} className="mt-4">
              <Plus className="h-4 w-4 mr-1" /> Register Data
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((ds) => (
              <DataSourceCard key={ds.name} dataSource={ds} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DataSourceCard({ dataSource }: { dataSource: any }) {
  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden hover:border-brand/30 transition-colors">
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Database className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">
                  {dataSource.name}
                </h4>
                <Badge tone="neutral">{dataSource.length || 0} points</Badge>
                {dataSource.frequency && (
                  <Badge tone="neutral">{dataSource.frequency}</Badge>
                )}
              </div>
              <p className="text-sm text-muted">
                Range: {dataSource.start} to {dataSource.end}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Mean</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.mean?.toFixed(2) ?? "N/A"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Std Dev</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.std?.toFixed(2) ?? "N/A"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Range</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.min?.toFixed(2)} -{" "}
                {dataSource.stats?.max?.toFixed(2)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ForecastPanel({
  dataSources,
  forecastRequest,
  setForecastRequest,
  forecastResult,
  forecasting,
  onForecast,
  chartData,
  selectedData,
}: any) {
  return (
    <div className="space-y-6">
      {/* Forecast Configuration */}
      <Card
        title="Configure Forecast"
        subtitle="Select data source and configure forecast parameters"
      >
        <form onSubmit={handleForecast} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={forecastRequest.data_name}
                onValueChange={(v) =>
                  setForecastRequest({ ...forecastRequest, data_name: v })
                }
                options={dataSources.map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
                placeholder="Select data source"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Horizon (periods) *
              </label>
              <Input
                type="number"
                value={forecastRequest.horizon}
                onChange={(e) =>
                  setForecastRequest({
                    ...forecastRequest,
                    horizon: parseInt(e.target.value),
                  })
                }
                min={1}
                max={365}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Method *
              </label>
              <Select
                value={forecastRequest.method}
                onValueChange={(v) =>
                  setForecastRequest({ ...forecastRequest, method: v as any })
                }
                options={[
                  { value: "prophet", label: "Prophet (Facebook)" },
                  { value: "neuralprophet", label: "NeuralProphet" },
                  { value: "arima", label: "ARIMA" },
                  { value: "sarima", label: "SARIMA" },
                  {
                    value: "exponential_smoothing",
                    label: "Exponential Smoothing",
                  },
                  { value: "linear_regression", label: "Linear Regression" },
                  { value: "random_forest", label: "Random Forest" },
                  { value: "gradient_boosting", label: "Gradient Boosting" },
                  { value: "ensemble", label: "Ensemble" },
                ]}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Frequency
              </label>
              <Select
                value={forecastRequest.frequency}
                onValueChange={(v) =>
                  setForecastRequest({
                    ...forecastRequest,
                    frequency: v as any,
                  })
                }
                options={[
                  { value: "T", label: "Minutely" },
                  { value: "H", label: "Hourly" },
                  { value: "D", label: "Daily" },
                  { value: "W", label: "Weekly" },
                  { value: "M", label: "Monthly" },
                  { value: "Q", label: "Quarterly" },
                  { value: "A", label: "Yearly" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Confidence Level
              </label>
              <Select
                value={forecastRequest.confidence_level}
                onValueChange={(v) =>
                  setForecastRequest({
                    ...forecastRequest,
                    confidence_level: parseFloat(v),
                  })
                }
                options={[
                  { value: "0.8", label: "80%" },
                  { value: "0.9", label: "90%" },
                  { value: "0.95", label: "95%" },
                  { value: "0.99", label: "99%" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Include History
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={forecastRequest.include_history}
                  onChange={(e) =>
                    setForecastRequest({
                      ...forecastRequest,
                      include_history: e.target.checked,
                    })
                  }
                  className="rounded border-line"
                />
                <span className="text-sm text-ink">
                  Include historical predictions
                </span>
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Advanced Params (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(forecastRequest.params, null, 2)}
                onChange={(e) => {
                  try {
                    setForecastRequest({
                      ...forecastRequest,
                      params: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"yearly_seasonality": true, "changepoint_prior_scale": 0.05}'
                rows={3}
                fontMonospace
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="submit"
              disabled={!forecastRequest.data_name || forecasting}
            >
              {forecasting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Forecasting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-1" />
                  Generate Forecast
                </>
              )}
            </Button>
          </div>
        </form>
      </Card>

      {/* Forecast Results */}
      {forecastResult && (
        <Card
          title="Forecast Results"
          subtitle={`${forecastResult.method.toUpperCase()} • ${forecastResult.forecast.length} periods • ${Math.round(forecastResult.confidence_level * 100)}% CI`}
        >
          {/* Metrics */}
          {forecastResult.metrics &&
            Object.keys(forecastResult.metrics).length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                <MetricCard
                  label="MAE"
                  value={forecastResult.metrics.mae?.toFixed(4)}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="RMSE"
                  value={forecastResult.metrics.rmse?.toFixed(4)}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="MAPE"
                  value={`${(forecastResult.metrics.mape || 0).toFixed(2)}%`}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="sMAPE"
                  value={`${(forecastResult.metrics.smape || 0).toFixed(2)}%`}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="Method"
                  value={forecastResult.method.toUpperCase()}
                  icon={Settings}
                />
              </div>
            )}

          {/* Chart Visualization */}
          <div className="h-80 relative">
            {chartData && chartData.historical && chartData.forecast && (
              <ForecastChart
                historical={chartData.historical}
                forecast={chartData.forecast}
              />
            )}
            {!chartData && (
              <div className="flex items-center justify-center h-full text-muted">
                <p>Chart data not available</p>
              </div>
            )}
          </div>

          {/* Forecast Table */}
          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-muted">
                  <th className="pb-2">Timestamp</th>
                  <th className="pb-2">Forecast</th>
                  <th className="pb-2">Lower Bound</th>
                  <th className="pb-2">Upper Bound</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {forecastResult.timestamps
                  .slice(0, 50)
                  .map((ts: string, i: number) => (
                    <tr key={i} className="hover:bg-canvas/50">
                      <td className="py-2 font-mono">
                        {new Date(ts).toLocaleString()}
                      </td>
                      <td className="py-2 font-medium">
                        {forecastResult.forecast[i]?.toFixed(4)}
                      </td>
                      <td className="py-2 text-muted">
                        {forecastResult.lower_bound?.[i]?.toFixed(4) ?? "N/A"}
                      </td>
                      <td className="py-2 text-muted">
                        {forecastResult.upper_bound?.[i]?.toFixed(4) ?? "N/A"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function DataSourcesPanel({
  dataSources,
  searchQuery,
  setSearchQuery,
  loading,
  onRefresh,
  onRegister,
}: {
  dataSources: any[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  loading: boolean;
  onRefresh: () => void;
  onRegister: () => void;
}) {
  const filtered = useMemo(
    () =>
      dataSources.filter(
        (d) =>
          d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          JSON.stringify(d).toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [dataSources, searchQuery],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search data sources..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-64"
          />
          <Button onClick={onRefresh} variant="outline" disabled={loading}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button onClick={onRegister}>
            <Plus className="h-4 w-4 mr-1" /> Register Data
          </Button>
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Database className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No data sources registered
            </h3>
            <p className="text-faint max-w-md mx-auto">
              Register your first time series to start forecasting
            </p>
            <Button onClick={onRegister} className="mt-4">
              <Plus className="h-4 w-4 mr-1" /> Register Data
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((ds) => (
              <DataSourceCard key={ds.name} dataSource={ds} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DataSourceCard({ dataSource }: { dataSource: any }) {
  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden hover:border-brand/30 transition-colors">
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Database className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">
                  {dataSource.name}
                </h4>
                <Badge tone="neutral">{dataSource.length || 0} points</Badge>
                {dataSource.frequency && (
                  <Badge tone="neutral">{dataSource.frequency}</Badge>
                )}
              </div>
              <p className="text-sm text-muted">
                Range: {dataSource.start} to {dataSource.end}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Mean</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.mean?.toFixed(2) ?? "N/A"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Std Dev</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.std?.toFixed(2) ?? "N/A"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Range</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.min?.toFixed(2)} -{" "}
                {dataSource.stats?.max?.toFixed(2)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ForecastPanel({
  dataSources,
  forecastRequest,
  setForecastRequest,
  forecastResult,
  forecasting,
  onForecast,
  chartData,
  selectedData,
}: any) {
  return (
    <div className="space-y-6">
      {/* Forecast Configuration */}
      <Card
        title="Configure Forecast"
        subtitle="Select data source and configure forecast parameters"
      >
        <form onSubmit={handleForecast} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={forecastRequest.data_name}
                onValueChange={(v) =>
                  setForecastRequest({ ...forecastRequest, data_name: v })
                }
                options={dataSources.map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
                placeholder="Select data source"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Horizon (periods) *
              </label>
              <Input
                type="number"
                value={forecastRequest.horizon}
                onChange={(e) =>
                  setForecastRequest({
                    ...forecastRequest,
                    horizon: parseInt(e.target.value),
                  })
                }
                min={1}
                max={365}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Method *
              </label>
              <Select
                value={forecastRequest.method}
                onValueChange={(v) =>
                  setForecastRequest({ ...forecastRequest, method: v as any })
                }
                options={[
                  { value: "prophet", label: "Prophet (Facebook)" },
                  { value: "neuralprophet", label: "NeuralProphet" },
                  { value: "arima", label: "ARIMA" },
                  { value: "sarima", label: "SARIMA" },
                  {
                    value: "exponential_smoothing",
                    label: "Exponential Smoothing",
                  },
                  { value: "linear_regression", label: "Linear Regression" },
                  { value: "random_forest", label: "Random Forest" },
                  { value: "gradient_boosting", label: "Gradient Boosting" },
                  { value: "ensemble", label: "Ensemble" },
                ]}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Frequency
              </label>
              <Select
                value={forecastRequest.frequency}
                onValueChange={(v) =>
                  setForecastRequest({
                    ...forecastRequest,
                    frequency: v as any,
                  })
                }
                options={[
                  { value: "T", label: "Minutely" },
                  { value: "H", label: "Hourly" },
                  { value: "D", label: "Daily" },
                  { value: "W", label: "Weekly" },
                  { value: "M", label: "Monthly" },
                  { value: "Q", label: "Quarterly" },
                  { value: "A", label: "Yearly" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Confidence Level
              </label>
              <Select
                value={forecastRequest.confidence_level}
                onValueChange={(v) =>
                  setForecastRequest({
                    ...forecastRequest,
                    confidence_level: parseFloat(v),
                  })
                }
                options={[
                  { value: "0.8", label: "80%" },
                  { value: "0.9", label: "90%" },
                  { value: "0.95", label: "95%" },
                  { value: "0.99", label: "99%" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Include History
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={forecastRequest.include_history}
                  onChange={(e) =>
                    setForecastRequest({
                      ...forecastRequest,
                      include_history: e.target.checked,
                    })
                  }
                  className="rounded border-line"
                />
                <span className="text-sm text-ink">
                  Include historical predictions
                </span>
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Advanced Params (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(forecastRequest.params, null, 2)}
                onChange={(e) => {
                  try {
                    setForecastRequest({
                      ...forecastRequest,
                      params: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"yearly_seasonality": true, "changepoint_prior_scale": 0.05}'
                rows={3}
                fontMonospace
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="submit"
              disabled={!forecastRequest.data_name || forecasting}
            >
              {forecasting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Forecasting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-1" />
                  Generate Forecast
                </>
              )}
            </Button>
          </div>
        </form>
      </Card>

      {/* Forecast Results */}
      {forecastResult && (
        <Card
          title="Forecast Results"
          subtitle={`${forecastResult.method.toUpperCase()} • ${forecastResult.forecast.length} periods • ${Math.round(forecastResult.confidence_level * 100)}% CI`}
        >
          {/* Metrics */}
          {forecastResult.metrics &&
            Object.keys(forecastResult.metrics).length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                <MetricCard
                  label="MAE"
                  value={forecastResult.metrics.mae?.toFixed(4)}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="RMSE"
                  value={forecastResult.metrics.rmse?.toFixed(4)}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="MAPE"
                  value={`${(forecastResult.metrics.mape || 0).toFixed(2)}%`}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="sMAPE"
                  value={`${(forecastResult.metrics.smape || 0).toFixed(2)}%`}
                  icon={TrendingDown}
                />
                <MetricCard
                  label="Method"
                  value={forecastResult.method.toUpperCase()}
                  icon={Settings}
                />
              </div>
            )}

          {/* Chart Visualization */}
          <div className="h-80 relative">
            {chartData && chartData.historical && chartData.forecast && (
              <ForecastChart
                historical={chartData.historical}
                forecast={chartData.forecast}
              />
            )}
            {!chartData && (
              <div className="flex items-center justify-center h-full text-muted">
                <p>Chart data not available</p>
              </div>
            )}
          </div>

          {/* Forecast Table */}
          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-muted">
                  <th className="pb-2">Timestamp</th>
                  <th className="pb-2">Forecast</th>
                  <th className="pb-2">Lower Bound</th>
                  <th className="pb-2">Upper Bound</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {forecastResult.timestamps
                  .slice(0, 50)
                  .map((ts: string, i: number) => (
                    <tr key={i} className="hover:bg-canvas/50">
                      <td className="py-2 font-mono">
                        {new Date(ts).toLocaleString()}
                      </td>
                      <td className="py-2 font-medium">
                        {forecastResult.forecast[i]?.toFixed(4)}
                      </td>
                      <td className="py-2 text-muted">
                        {forecastResult.lower_bound?.[i]?.toFixed(4) ?? "N/A"}
                      </td>
                      <td className="py-2 text-muted">
                        {forecastResult.upper_bound?.[i]?.toFixed(4) ?? "N/A"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function DataSourcesPanel({
  dataSources,
  searchQuery,
  setSearchQuery,
  loading,
  onRefresh,
  onRegister,
}: {
  dataSources: any[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  loading: boolean;
  onRefresh: () => void;
  onRegister: () => void;
}) {
  const filtered = useMemo(
    () =>
      dataSources.filter(
        (d) =>
          d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          JSON.stringify(d).toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [dataSources, searchQuery],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search data sources..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-64"
          />
          <Button onClick={onRefresh} variant="outline" disabled={loading}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button onClick={onRegister}>
            <Plus className="h-4 w-4 mr-1" /> Register Data
          </Button>
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Database className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No data sources registered
            </h3>
            <p className="text-faint max-w-md mx-auto">
              Register your first time series to start forecasting
            </p>
            <Button onClick={onRegister} className="mt-4">
              <Plus className="h-4 w-4 mr-1" /> Register Data
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((ds) => (
              <DataSourceCard key={ds.name} dataSource={ds} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DataSourceCard({ dataSource }: { dataSource: any }) {
  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden hover:border-brand/30 transition-colors">
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <Database className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">
                  {dataSource.name}
                </h4>
                <Badge tone="neutral">{dataSource.length || 0} points</Badge>
                {dataSource.frequency && (
                  <Badge tone="neutral">{dataSource.frequency}</Badge>
                )}
              </div>
              <p className="text-sm text-muted">
                Range: {dataSource.start} to {dataSource.end}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Mean</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.mean?.toFixed(2) ?? "N/A"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Std Dev</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.std?.toFixed(2) ?? "N/A"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-canvas border border-line">
              <p className="text-xs font-medium text-muted mb-1">Range</p>
              <p className="font-medium text-ink">
                {dataSource.stats?.min?.toFixed(2)} -{" "}
                {dataSource.stats?.max?.toFixed(2)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ForecastChart({
  historical,
  forecast,
}: {
  historical: { x: string; y: number }[];
  forecast: { x: string; y: number; lower?: number; upper?: number }[];
}) {
  // Simple SVG-based chart
  const allData = [...historical, ...forecast];
  const minX = 0;
  const maxX = allData.length - 1;
  const allY = [
    ...historical.map((d) => d.y),
    ...forecast.map((d) => d.y),
    ...forecast.flatMap((d) => [d.lower, d.upper].filter(Boolean) as number[]),
  ];
  const minY = Math.min(...allY);
  const maxY = Math.max(...allY);
  const padding = 40;
  const width = 800;
  const height = 300;

  const xScale = (i: number) => padding + (i / maxX) * (width - 2 * padding);
  const yScale = (y: number) =>
    height - padding - ((y - minY) / (maxY - minY)) * (height - 2 * padding);

  return (
    <svg
      width="100%"
      height={height}
      viewBox="0 0 ${width} ${height}"
      className="w-full h-full"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id="confidence-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      <g stroke="#e5e7eb" strokeWidth="0.5">
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <line
            key={v}
            x1={padding}
            y1={padding + (1 - v) * (height - 2 * padding)}
            x2={width - padding}
            y2={padding + (1 - v) * (height - 2 * padding)}
          />
        ))}
        {Array.from({ length: 10 }).map((_, i) => (
          <line
            key={i}
            x1={padding + (i * (width - 2 * padding)) / 9}
            y1={padding}
            x2={padding + (i * (width - 2 * padding)) / 9}
            y2={height - padding}
          />
        ))}
      </g>

      {/* Confidence interval */}
      {forecast.some((d) => d.lower !== undefined && d.upper !== undefined) && (
        <path
          d={[
            ...forecast.map(
              (d, i) =>
                `${i === 0 ? "M" : "L"} ${xScale(historical.length + i)} ${yScale(d.upper!)}`,
            ),
            ...forecast
              .slice()
              .reverse()
              .map(
                (d, i) =>
                  `L ${xScale(historical.length + forecast.length - 1 - i)} ${yScale(d.lower!)}`,
              ),
            "Z",
          ].join(" ")}
          fill="url(#confidence-gradient)"
        />
      )}

      {/* Historical line */}
      <path
        d={historical
          .map((d, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(d.y)}`)
          .join(" ")}
        stroke="#6b7280"
        strokeWidth="2"
        fill="none"
        strokeDasharray="4,4"
      />

      {/* Forecast line */}
      <path
        d={forecast
          .map(
            (d, i) =>
              `${i === 0 ? "M" : "L"} ${xScale(historical.length + i)} ${yScale(d.y)}`,
          )
          .join(" ")}
        stroke="#3b82f6"
        strokeWidth="2.5"
        fill="none"
      />

      {/* Historical points */}
      {historical.map((d, i) => (
        <circle key={i} cx={xScale(i)} cy={yScale(d.y)} r={3} fill="#6b7280" />
      ))}

      {/* Forecast points */}
      {forecast.map((d, i) => (
        <circle
          key={i}
          cx={xScale(historical.length + i)}
          cy={yScale(d.y)}
          r={3}
          fill="#3b82f6"
        />
      ))}
    </svg>
  );
}

function AnomalyCard({
  index,
  timestamp,
  value,
  score,
}: {
  index: number;
  timestamp: string;
  value: number;
  score?: number;
}) {
  return (
    <div className="p-3 rounded-lg bg-canvas border border-line flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-red-100 text-red-600">
          <AlertTriangle className="h-4 w-4" />
        </div>
        <div>
          <p className="font-medium text-ink">Anomaly #{index + 1}</p>
          <p className="text-sm text-muted">
            {new Date(timestamp).toLocaleString()}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="px-2 py-1 rounded bg-canvas border border-line">
          <span className="font-medium text-ink">{value.toFixed(4)}</span>
          <span className="text-muted ml-1">value</span>
        </div>
        {score !== undefined && (
          <div className="px-2 py-1 rounded bg-canvas border border-line">
            <span className="font-medium text-red-600">{score.toFixed(3)}</span>
            <span className="text-muted ml-1">score</span>
          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="p-3 rounded-lg bg-canvas border border-line">
      <div className="flex items-center gap-2 mb-1">
        <div className="p-1.5 rounded bg-brand/10 text-brand">
          <Icon className="h-4 w-4" />
        </div>
        <span className="text-xs font-medium text-muted">{label}</span>
      </div>
      <p className="text-lg font-bold text-ink">{value}</p>
    </div>
  );
}
