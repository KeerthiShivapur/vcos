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
  Server,
  Cpu,
  MemoryStick,
  Cloud,
  Wifi,
  Activity,
  Thermometer,
  Gauge,
  CheckCircle,
} from "lucide-react";
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
} from "@/components/ui/Table";
import { Modal } from "@/components/ui/Modal";
import { Textarea } from "@/components/ui/Textarea";
import { classNames } from "@/lib/utils";

interface InferenceServiceTabProps {
  organizationId: string;
  className?: string;
}

export function InferenceServiceTab({
  organizationId,
  className,
}: InferenceServiceTabProps) {
  const [activeTab, setActiveTab] = useState<
    "models" | "deployments" | "endpoints" | "health" | "metrics"
  >("models");
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<
    Array<{
      id: string;
      name: string;
      framework: string;
      version: string;
      status: string;
      size: string;
      created_at: string;
    }>
  >([]);
  const [deployments, setDeployments] = useState<
    Array<{
      id: string;
      name: string;
      model_id: string;
      backend: string;
      status: string;
      replicas: number;
      endpoint: string;
      created_at: string;
    }>
  >([]);
  const [endpoints, setEndpoints] = useState<
    Array<{
      id: string;
      name: string;
      url: string;
      model_id: string;
      status: string;
      requests_per_minute: number;
      latency_p99: number;
    }>
  >([]);
  const [health, setHealth] = useState<{
    status: string;
    uptime: number;
    cpu: number;
    memory: number;
    gpu: number;
    models_loaded: number;
  } | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [selectedDeployment, setSelectedDeployment] = useState<string | null>(
    null,
  );
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newDeployment, setNewDeployment] = useState({
    name: "",
    model_id: "",
    backend: "triton",
    replicas: 1,
    resources: { cpu: "1000m", memory: "2Gi", gpu: "0" },
  });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchModels = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/ml/models`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setModels(data);
      }
    } catch (error) {
      console.error("Failed to load models:", error);
    }
  }, []);

  const fetchDeployments = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/ml/deployments`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setDeployments(data.deployments || []);
      }
    } catch (error) {
      console.error("Failed to load deployments:", error);
    }
  }, []);

  const fetchEndpoints = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/ml/endpoints`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setEndpoints(data.endpoints || []);
      }
    } catch (error) {
      console.error("Failed to load endpoints:", error);
    }
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch(`/api/v1/ml/health`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setHealth(data);
      }
    } catch (error) {
      console.error("Failed to load health:", error);
    }
  }, []);

  useEffect(() => {
    fetchModels();
    fetchDeployments();
    fetchEndpoints();
    fetchHealth();
  }, [fetchModels, fetchDeployments, fetchEndpoints, fetchHealth]);

  const handleCreateDeployment = async () => {
    if (!newDeployment.name.trim() || !newDeployment.model_id) return;
    setError(null);
    try {
      const response = await fetch(`/api/v1/ml/deployments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify(newDeployment),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to create deployment");
      }
      const deployment = await response.json();
      setDeployments((prev) => [deployment, ...prev]);
      setShowCreateModal(false);
      setNewDeployment({
        name: "",
        model_id: "",
        backend: "triton",
        replicas: 1,
        resources: { cpu: "1000m", memory: "2Gi", gpu: "0" },
      });
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Failed to create deployment",
      );
    }
  };

  const handleDeleteDeployment = async (deploymentId: string) => {
    if (!confirm("Are you sure you want to delete this deployment?")) return;
    try {
      const response = await fetch(`/api/v1/ml/deployments/${deploymentId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (!response.ok) throw new Error("Failed to delete deployment");
      setDeployments((prev) => prev.filter((d) => d.id !== deploymentId));
    } catch (error) {
      console.error("Failed to delete deployment:", error);
      alert("Failed to delete deployment");
    }
  };

  const handleScaleDeployment = async (
    deploymentId: string,
    replicas: number,
  ) => {
    try {
      const response = await fetch(
        `/api/v1/ml/deployments/${deploymentId}/scale`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ replicas }),
        },
      );
      if (!response.ok) throw new Error("Failed to scale deployment");
      fetchDeployments();
    } catch (error) {
      console.error("Failed to scale deployment:", error);
      alert("Failed to scale deployment");
    }
  };

  const handleLoadModel = async (deploymentId: string, modelId: string) => {
    try {
      const response = await fetch(
        `/api/v1/ml/deployments/${deploymentId}/load`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
          body: JSON.stringify({ model_id: modelId }),
        },
      );
      if (!response.ok) throw new Error("Failed to load model");
      fetchDeployments();
    } catch (error) {
      console.error("Failed to load model:", error);
      alert("Failed to load model");
    }
  };

  return (
    <div className={classNames("space-y-6", className)}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink">Inference Service</h2>
          <p className="text-muted text-sm mt-1">
            Triton/vLLM/TGI compatible model serving
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              fetchModels();
              fetchDeployments();
              fetchEndpoints();
              fetchHealth();
            }}
            disabled={isRefreshing}
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Deployment
          </Button>
        </div>
      </div>

      {/* Health Status */}
      {health && (
        <Card className="mb-6 p-4 bg-gradient-to-r from-green-50 to-emerald-50 border-green-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
              <div>
                <p className="font-medium text-green-800">Service Healthy</p>
                <p className="text-sm text-green-600">
                  Uptime: {Math.floor(health.uptime / 3600)}h{" "}
                  {Math.floor((health.uptime % 3600) / 60)}m
                </p>
              </div>
            </div>
            <div className="flex items-center gap-6 text-sm">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-muted" />
                <span>CPU: {health.cpu}%</span>
              </div>
              <div className="flex items-center gap-2">
                <MemoryStick className="h-4 w-4 text-muted" />
                <span>Memory: {health.memory}%</span>
              </div>
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-muted" />
                <span>GPU: {health.gpu}%</span>
              </div>
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted" />
                <span>Models: {health.models_loaded}</span>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Tabs */}
      <Tabs defaultValue="models" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="models" className="py-2 flex items-center gap-2">
            <Database className="h-4 w-4" />
            Models
          </TabsTrigger>
          <TabsTrigger
            value="deployments"
            className="py-2 flex items-center gap-2"
          >
            <Server className="h-4 w-4" />
            Deployments
          </TabsTrigger>
          <TabsTrigger
            value="endpoints"
            className="py-2 flex items-center gap-2"
          >
            <Link2 className="h-4 w-4" />
            Endpoints
          </TabsTrigger>
          <TabsTrigger value="health" className="py-2 flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Health
          </TabsTrigger>
          <TabsTrigger value="metrics" className="py-2 flex items-center gap-2">
            <Gauge className="h-4 w-4" />
            Metrics
          </TabsTrigger>
        </TabsList>

        {/* Models Tab */}
        <TabsContent value="models" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Model Registry</h3>
              <p className="text-sm text-muted">
                Manage and deploy ML models to inference backends
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
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
            </div>
          ) : models.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <Database className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">No models registered</h3>
              <p className="text-muted text-sm mb-4">
                Register a model to start deploying
              </p>
              <Button
                onClick={() => {
                  setShowCreateModal(true);
                  setActiveTab("models");
                }}
              >
                <Plus className="h-4 w-4 mr-1" />
                Register Model
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-line">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Framework</th>
                    <th className="pb-2 pr-4">Version</th>
                    <th className="pb-2 pr-4">Size</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Created</th>
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
                          {model.framework}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm">{model.version}</td>
                      <td className="py-3 pr-4 text-sm">{model.size}</td>
                      <td className="py-3 pr-4">
                        <Badge
                          tone={
                            model.status === "ready"
                              ? "success"
                              : model.status === "loading"
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
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedModel(model.id);
                              setActiveTab("deployments");
                            }}
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Deploy
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-700"
                            onClick={() => {
                              if (confirm("Delete model?")) {
                                /* delete */
                              }
                            }}
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

        {/* Deployments Tab */}
        <TabsContent value="deployments" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Deployments</h3>
              <p className="text-sm text-muted">
                Manage model deployments across inference backends
              </p>
            </div>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus className="h-4 w-4 mr-1" />
              New Deployment
            </Button>
          </div>

          {deployments.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <Server className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">No deployments yet</h3>
              <p className="text-muted text-sm mb-4">
                Deploy your first model to start serving predictions
              </p>
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Create Deployment
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-line">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Model</th>
                    <th className="pb-2 pr-4">Backend</th>
                    <th className="pb-2 pr-4">Replicas</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Endpoint</th>
                    <th className="pb-2 pr-4">Created</th>
                    <th className="pb-2 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {deployments.map((deployment) => (
                    <tr
                      key={deployment.id}
                      className="border-b border-line/50 hover:bg-muted/50"
                    >
                      <td className="py-3 pr-4 font-medium text-sm">
                        {deployment.name}
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        {deployment.model_id}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge
                          tone={
                            deployment.backend === "triton"
                              ? "neutral"
                              : deployment.backend === "vllm"
                                ? "success"
                                : "neutral"
                          }
                        >
                          {deployment.backend}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        {deployment.replicas}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge
                          tone={
                            deployment.status === "ready"
                              ? "success"
                              : deployment.status === "pending"
                                ? "warning"
                                : "neutral"
                          }
                        >
                          {deployment.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm text-muted font-mono text-xs">
                        {deployment.endpoint}
                      </td>
                      <td className="py-3 pr-4 text-sm text-muted">
                        {new Date(deployment.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedDeployment(deployment.id);
                              setActiveTab("endpoints");
                            }}
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Endpoint
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              /* scale modal */
                            }}
                          >
                            <Gauge className="h-3.5 w-3.5" />
                            Scale
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-700"
                            onClick={() =>
                              handleDeleteDeployment(deployment.id)
                            }
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

        {/* Endpoints Tab */}
        <TabsContent value="endpoints" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">API Endpoints</h3>
              <p className="text-sm text-muted">
                Manage and monitor inference endpoints
              </p>
            </div>
          </div>

          {endpoints.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <Link2 className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">No endpoints yet</h3>
              <p className="text-muted text-sm mb-4">
                Deploy a model to create an inference endpoint
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-line">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Model</th>
                    <th className="pb-2 pr-4">URL</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">RPM</th>
                    <th className="pb-2 pr-4">P99 Latency</th>
                    <th className="pb-2 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {endpoints.map((endpoint) => (
                    <tr
                      key={endpoint.id}
                      className="border-b border-line/50 hover:bg-muted/50"
                    >
                      <td className="py-3 pr-4 font-medium text-sm">
                        {endpoint.name}
                      </td>
                      <td className="py-3 pr-4 text-sm">{endpoint.model_id}</td>
                      <td className="py-3 pr-4 text-sm text-muted font-mono text-xs max-w-xs truncate block">
                        {endpoint.url}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge
                          tone={
                            endpoint.status === "healthy"
                              ? "success"
                              : "neutral"
                          }
                        >
                          {endpoint.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        {endpoint.requests_per_minute}
                      </td>
                      <td className="py-3 pr-4 text-sm">
                        {endpoint.latency_p99}ms
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              navigator.clipboard.writeText(endpoint.url)
                            }
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                            Copy URL
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-500 hover:text-red-700"
                            onClick={() => {
                              /* delete endpoint */
                            }}
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

        {/* Health Tab */}
        <TabsContent value="health" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 rounded-lg">
                  <Activity className="h-6 w-6 text-green-600" />
                </div>
                <div>
                  <p className="text-sm text-muted">Status</p>
                  <p className="text-2xl font-bold text-green-600">Healthy</p>
                </div>
              </div>
            </Card>
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  <Cpu className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm text-muted">CPU Usage</p>
                  <p className="text-2xl font-bold text-blue-600">
                    {health?.cpu || 0}%
                  </p>
                </div>
              </div>
            </Card>
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-100 rounded-lg">
                  <MemoryStick className="h-6 w-6 text-amber-600" />
                </div>
                <div>
                  <p className="text-sm text-muted">Memory Usage</p>
                  <p className="text-2xl font-bold text-amber-600">
                    {health?.memory || 0}%
                  </p>
                </div>
              </div>
            </Card>
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-100 rounded-lg">
                  <Cpu className="h-6 w-6 text-purple-600" />
                </div>
                <div>
                  <p className="text-sm text-muted">GPU Usage</p>
                  <p className="text-2xl font-bold text-purple-600">
                    {health?.gpu || 0}%
                  </p>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="p-4">
              <h3 className="font-medium mb-3">Model Registry Status</h3>
              <div className="space-y-2">
                <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                  <span className="text-sm text-ink">Models Loaded</span>
                  <span className="text-lg font-bold text-brand">
                    {health?.models_loaded || 0}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                  <span className="text-sm text-ink">Uptime</span>
                  <span className="text-lg font-bold text-ink">
                    {health
                      ? `${Math.floor(health.uptime / 3600)}h ${Math.floor((health.uptime % 3600) / 60)}m`
                      : "0h 0m"}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                  <span className="text-sm text-ink">Active Endpoints</span>
                  <span className="text-lg font-bold text-brand">
                    {endpoints.filter((e) => e.status === "healthy").length}
                  </span>
                </div>
              </div>
            </Card>

            <Card className="p-4">
              <h3 className="font-medium mb-3">Quick Actions</h3>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  onClick={fetchHealth}
                  disabled={isRefreshing}
                >
                  <RefreshCw
                    className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
                  />
                  Refresh Health
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setActiveTab("deployments");
                    setShowCreateModal(true);
                  }}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  New Deployment
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setActiveTab("models");
                    setShowCreateModal(true);
                  }}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Register Model
                </Button>
              </div>
            </Card>
          </div>
        </TabsContent>

        {/* Metrics Tab */}
        <TabsContent value="metrics" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Service Metrics</h3>
              <p className="text-sm text-muted">
                Monitor inference service performance
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted">Total Requests (24h)</p>
                  <p className="text-2xl font-bold text-brand">1.2M</p>
                </div>
                <div className="p-2 bg-brand/10 rounded-lg">
                  <ArrowRight className="h-6 w-6 text-brand" />
                </div>
              </div>
            </Card>
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted">Avg Latency (p50)</p>
                  <p className="text-2xl font-bold text-success">45ms</p>
                </div>
                <div className="p-2 bg-green-100 rounded-lg">
                  <TrendingDown className="h-6 w-6 text-green-600" />
                </div>
              </div>
            </Card>
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted">P99 Latency</p>
                  <p className="text-2xl font-bold text-warning">180ms</p>
                </div>
                <div className="p-2 bg-yellow-100 rounded-lg">
                  <Gauge className="h-6 w-6 text-yellow-600" />
                </div>
              </div>
            </Card>
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted">Error Rate</p>
                  <p className="text-2xl font-bold text-success">0.02%</p>
                </div>
                <div className="p-2 bg-green-100 rounded-lg">
                  <CheckCircle className="h-6 w-6 text-green-600" />
                </div>
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <h3 className="font-medium mb-4">Request Volume (24h)</h3>
              <div className="h-64 bg-muted/50 rounded-lg flex items-center justify-center">
                <span className="text-muted">
                  Chart placeholder - integrate with Prometheus/Grafana
                </span>
              </div>
            </Card>
            <Card>
              <h3 className="font-medium mb-4">Latency Distribution</h3>
              <div className="h-64 bg-muted/50 rounded-lg flex items-center justify-center">
                <span className="text-muted">
                  Chart placeholder - integrate with Prometheus/Grafana
                </span>
              </div>
            </Card>
          </div>

          <Card>
            <h3 className="font-medium mb-4">Top Models by Request Volume</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-line">
                    <th className="pb-2 pr-4">Model</th>
                    <th className="pb-2 pr-4">Requests (24h)</th>
                    <th className="pb-2 pr-4">Avg Latency</th>
                    <th className="pb-2 pr-4">P99 Latency</th>
                    <th className="pb-2 pr-4">Error Rate</th>
                    <th className="pb-2 pr-4">Throughput</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    {
                      model: "bert-base-uncased",
                      requests: "45,231",
                      avg: "42ms",
                      p99: "156ms",
                      errors: "0.01%",
                      throughput: "1,884/min",
                    },
                    {
                      model: "gpt-3.5-turbo",
                      requests: "23,456",
                      avg: "1.2s",
                      p99: "3.4s",
                      errors: "0.05%",
                      throughput: "978/min",
                    },
                    {
                      model: "whisper-large-v3",
                      requests: "12,789",
                      avg: "890ms",
                      p99: "2.1s",
                      errors: "0.02%",
                      throughput: "532/min",
                    },
                    {
                      model: "stable-diffusion-xl",
                      requests: "8,901",
                      avg: "4.2s",
                      p99: "8.7s",
                      errors: "0.1%",
                      throughput: "148/min",
                    },
                  ].map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-line/50 hover:bg-muted/50"
                    >
                      <td className="py-3 pr-4 font-medium text-sm">
                        {row.model}
                      </td>
                      <td className="py-3 pr-4 text-sm">{row.requests}</td>
                      <td className="py-3 pr-4 text-sm">{row.avg}</td>
                      <td className="py-3 pr-4 text-sm">{row.p99}</td>
                      <td className="py-3 pr-4 text-sm text-red-500">
                        {row.errors}
                      </td>
                      <td className="py-3 pr-4 text-sm">{row.throughput}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
