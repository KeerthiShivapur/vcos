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

interface CausalInferenceTabProps {
  organizationId: string;
  className?: string;
}

export function CausalInferenceTab({
  organizationId,
  className,
}: CausalInferenceTabProps) {
  const [activeTab, setActiveTab] = useState<
    "graphs" | "estimate" | "counterfactual" | "discover" | "graphs-list"
  >("graphs");
  const [loading, setLoading] = useState(false);
  const [graphs, setGraphs] = useState<
    Array<{
      id: string;
      name: string;
      nodes: number;
      edges: number;
      status: string;
      created_at: string;
    }>
  >([]);
  const [selectedGraph, setSelectedGraph] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newGraph, setNewGraph] = useState({
    name: "",
    description: "",
    nodes: [] as any[],
    edges: [] as any[],
  });
  const [estimateParams, setEstimateParams] = useState({
    treatment: "",
    outcome: "",
    confounders: [] as string[],
    effect_modifiers: [] as string[],
    method: "causal_forest",
  });
  const [estimateResult, setEstimateResult] = useState<any>(null);
  const [counterfactualParams, setCounterfactualParams] = useState({
    treatment_value: "",
    outcome_value: "",
  });
  const [counterfactualResult, setCounterfactualResult] = useState<any>(null);
  const [discoveryParams, setDiscoveryParams] = useState({
    variables: [] as string[],
    method: "pc",
  });
  const [discoveryResult, setDiscoveryResult] = useState<any>(null);
  const [counterfactualLoading, setCounterfactualLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [graphsList, setGraphsList] = useState<
    Array<{
      id: string;
      name: string;
      nodes: number;
      edges: number;
      status: string;
      created_at: string;
    }>
  >([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchGraphs = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const response = await fetch(`/api/v1/causal/graphs`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setGraphsList(data.graphs || []);
      } else {
        setError("Failed to load graphs");
      }
    } catch (error) {
      console.error("Failed to load graphs:", error);
      setError("Failed to load graphs");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchGraphs();
  }, [fetchGraphs]);

  const handleCreateGraph = async () => {
    if (!newGraph.name.trim()) return;
    setError(null);
    try {
      const response = await fetch(`/api/v1/causal/graphs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          name: newGraph.name,
          description: newGraph.description,
          nodes: newGraph.nodes,
          edges: newGraph.edges,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to create graph");
      }
      const graph = await response.json();
      setGraphsList((prev) => [graph, ...prev]);
      setShowCreateModal(false);
      setNewGraph({ name: "", description: "", nodes: [], edges: [] });
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Failed to create graph",
      );
    }
  };

  const handleEstimateEffect = async () => {
    if (!selectedGraph) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/causal/estimate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          graph_id: selectedGraph,
          treatment: estimateParams.treatment,
          outcome: estimateParams.outcome,
          confounders: estimateParams.confounders,
          effect_modifiers: estimateParams.effect_modifiers,
          method: estimateParams.method,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Estimation failed");
      }
      const result = await response.json();
      setEstimateResult(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Estimation failed");
    } finally {
      setLoading(false);
    }
  };

  const handleCounterfactual = async () => {
    if (!selectedGraph) return;
    setCounterfactualLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/causal/counterfactual`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          graph_id: selectedGraph,
          treatment_value: counterfactualParams.treatment_value,
          outcome_value: counterfactualParams.outcome_value,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Counterfactual failed");
      }
      const result = await response.json();
      setCounterfactualResult(result);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Counterfactual failed",
      );
    } finally {
      setCounterfactualLoading(false);
    }
  };

  const handleDiscover = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/causal/discover`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          variables: discoveryParams.variables,
          method: discoveryParams.method,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Discovery failed");
      }
      const result = await response.json();
      setDiscoveryResult(result);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Discovery failed");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteGraph = async (graphId: string) => {
    if (!confirm("Are you sure you want to delete this graph?")) return;
    try {
      const response = await fetch(`/api/v1/causal/graphs/${graphId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (!response.ok) throw new Error("Failed to delete graph");
      setGraphsList((prev) => prev.filter((g) => g.id !== graphId));
      if (selectedGraph === graphId) setSelectedGraph(null);
    } catch (error) {
      console.error("Failed to delete graph:", error);
      alert("Failed to delete graph");
    }
  };

  return (
    <div className={classNames("space-y-6", className)}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink">Causal Inference</h2>
          <p className="text-muted text-sm mt-1">
            Causal graphs, effect estimation, counterfactuals & discovery
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchGraphs}
            disabled={isRefreshing}
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Graph
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="graphs" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="graphs" className="py-2 flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            Causal Graphs
          </TabsTrigger>
          <TabsTrigger
            value="estimate"
            className="py-2 flex items-center gap-2"
          >
            <TargetIcon className="h-4 w-4" />
            Effect Estimation
          </TabsTrigger>
          <TabsTrigger
            value="counterfactual"
            className="py-2 flex items-center gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Counterfactuals
          </TabsTrigger>
          <TabsTrigger
            value="discover"
            className="py-2 flex items-center gap-2"
          >
            <Microscope className="h-4 w-4" />
            Discovery
          </TabsTrigger>
          <TabsTrigger
            value="graphs-list"
            className="py-2 flex items-center gap-2"
          >
            <GitBranch className="h-4 w-4" />
            Graph Registry
          </TabsTrigger>
        </TabsList>

        {/* Causal Graphs Tab */}
        <TabsContent value="graphs" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Causal Graphs</h3>
              <p className="text-sm text-muted">
                Define and manage causal graphs for effect estimation
              </p>
            </div>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus className="h-4 w-4 mr-1" />
              New Graph
            </Button>
          </div>

          {loading && !graphs.length ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
            </div>
          ) : graphs.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <GitBranch className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">No causal graphs yet</h3>
              <p className="text-muted text-sm mb-4">
                Create your first causal graph to get started
              </p>
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Create Graph
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {graphs.map((graph) => (
                <div
                  key={graph.id}
                  className="border border-line rounded-xl p-4 bg-canvas hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium text-ink truncate">
                          {graph.name}
                        </h3>
                        <Badge tone="neutral" className="text-xs">
                          {graph.nodes} nodes
                        </Badge>
                        <Badge tone="neutral" className="text-xs">
                          {graph.edges} edges
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 text-muted text-sm">
                        <span>
                          Created:{" "}
                          {new Date(graph.created_at).toLocaleDateString()}
                        </span>
                        <span>•</span>
                        <Badge tone="neutral" className="text-xs">
                          {graph.status}
                        </Badge>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-auto shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedGraph(graph.id)}
                      >
                        <Eye className="h-4 w-4" /> View
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-brand"
                      >
                        <GitBranch className="h-3.5 w-3.5" /> Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-red-500"
                        onClick={() => handleDeleteGraph(graph.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Create Graph Modal */}
          {showCreateModal && (
            <Modal
              open={showCreateModal}
              onClose={() => setShowCreateModal(false)}
              title="Create Causal Graph"
              size="lg"
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Name *
                  </label>
                  <Input
                    value={newGraph.name}
                    onChange={(e) =>
                      setNewGraph({ ...newGraph, name: e.target.value })
                    }
                    placeholder="e.g., marketing_attribution, churn_causality"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Description
                  </label>
                  <Textarea
                    value={newGraph.description}
                    onChange={(e) =>
                      setNewGraph({ ...newGraph, description: e.target.value })
                    }
                    placeholder="Describe this causal graph..."
                    rows={3}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Nodes (JSON)
                  </label>
                  <Textarea
                    value={JSON.stringify(newGraph.nodes, null, 2)}
                    onChange={(e) => {
                      try {
                        setNewGraph({
                          ...newGraph,
                          nodes: JSON.parse(e.target.value),
                        });
                      } catch {}
                    }}
                    rows={4}
                    className="font-mono text-sm"
                    placeholder='[{"id": "X", "name": "Treatment"}, {"id": "Y", "name": "Outcome"}]'
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Edges (JSON)
                  </label>
                  <Textarea
                    value={JSON.stringify(newGraph.edges, null, 2)}
                    onChange={(e) => {
                      try {
                        setNewGraph({
                          ...newGraph,
                          edges: JSON.parse(e.target.value),
                        });
                      } catch {}
                    }}
                    rows={4}
                    className="font-mono text-sm"
                    placeholder='[{"from": "X", "to": "Y", "weight": 0.8}]'
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
                    onClick={handleCreateGraph}
                    disabled={!newGraph.name.trim() || loading}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Create Graph
                  </Button>
                </div>
              </div>
            </Modal>
          )}
        </TabsContent>

        {/* Effect Estimation Tab */}
        <TabsContent value="estimate" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Effect Estimation</h3>
              <p className="text-sm text-muted">
                Estimate causal effects using various methods
              </p>
            </div>
            <Button
              onClick={handleEstimateEffect}
              disabled={!selectedGraph || loading}
              className="ml-auto"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Estimating...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <TargetIcon className="h-4 w-4" /> Estimate Effect
                </span>
              )}
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Select Causal Graph
              </label>
              <select
                value={selectedGraph || ""}
                onChange={(e) => setSelectedGraph(e.target.value)}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="">Select a causal graph...</option>
                {graphs.map((graph) => (
                  <option key={graph.id} value={graph.id}>
                    {graph.name} ({graph.nodes} nodes, {graph.edges} edges)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Method
              </label>
              <select
                value={estimateParams.method}
                onChange={(e) =>
                  setEstimateParams({
                    ...estimateParams,
                    method: e.target.value,
                  })
                }
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="causal_forest">
                  Causal Forest (Recommended)
                </option>
                <option value="linear_dml">Linear DML</option>
                <option value="sparse_dml">Sparse DML</option>
                <option value="iv_dml">Instrumental Variable DML</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Treatment Variable
              </label>
              <Input
                value={estimateParams.treatment}
                onChange={(e) =>
                  setEstimateParams({
                    ...estimateParams,
                    treatment: e.target.value,
                  })
                }
                placeholder="Treatment variable name"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Outcome Variable
              </label>
              <Input
                value={estimateParams.outcome}
                onChange={(e) =>
                  setEstimateParams({
                    ...estimateParams,
                    outcome: e.target.value,
                  })
                }
                placeholder="e.g., conversion, revenue"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">
                  Confounders (comma-separated)
                </label>
                <Input
                  value={estimateParams.confounders.join(", ")}
                  onChange={(e) =>
                    setEstimateParams({
                      ...estimateParams,
                      confounders: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="confounder1, confounder2, ..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">
                  Effect Modifiers (comma-separated)
                </label>
                <Input
                  value={estimateParams.effect_modifiers.join(", ")}
                  onChange={(e) =>
                    setEstimateParams({
                      ...estimateParams,
                      effect_modifiers: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="modifier1, modifier2, ..."
                />
              </div>

              <Button
                onClick={handleEstimateEffect}
                disabled={!selectedGraph || loading}
                className="w-full"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" /> Estimating...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <TargetIcon className="h-4 w-4" /> Estimate Effect
                  </span>
                )}
              </Button>
            </div>
          </div>

          {estimateResult && (
            <Card className="p-4 mt-4">
              <h3 className="font-medium mb-4">Estimation Results</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">
                    Average Treatment Effect (ATE)
                  </p>
                  <p className="text-2xl font-bold text-brand">
                    {estimateResult.ate?.toFixed(4)}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">95% CI</p>
                  <p className="font-medium">
                    [{estimateResult.ci_lower?.toFixed(4)},{" "}
                    {estimateResult.ci_upper?.toFixed(4)}]
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Method</p>
                  <p className="font-medium capitalize">
                    {estimateParams.method.replace("_", " ")}
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="font-medium">
                  Conditional Average Treatment Effects (CATE)
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted border-b border-line">
                        <th className="pb-2 pr-4">Subgroup</th>
                        <th className="pb-2 pr-4">CATE</th>
                        <th className="pb-2 pr-4">CI Lower</th>
                        <th className="pb-2 pr-4">CI Upper</th>
                        <th className="pb-2 pr-4">Sample Size</th>
                      </tr>
                    </thead>
                    <tbody>
                      {estimateResult.cate?.map((cate: any, i: number) => (
                        <tr key={i} className="border-b border-line/50">
                          <td className="py-2 pr-4 font-mono text-sm">
                            {cate.subgroup}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm">
                            {cate.cate?.toFixed(4)}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm text-muted">
                            {cate.ci_lower?.toFixed(4)}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm text-muted">
                            {cate.ci_upper?.toFixed(4)}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm">
                            {cate.n}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </Card>
          )}
        </TabsContent>

        {/* Counterfactual Tab */}
        <TabsContent value="counterfactual" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Counterfactual Inference</h3>
              <p className="text-sm text-muted">
                Answer "what-if" questions with counterfactual reasoning
              </p>
            </div>
            <Button
              onClick={handleCounterfactual}
              disabled={!selectedGraph || loading}
              className="ml-auto"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Computing...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <ArrowLeft className="h-4 w-4" /> Compute Counterfactual
                </span>
              )}
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Select Causal Graph
              </label>
              <select
                value={selectedGraph || ""}
                onChange={(e) => setSelectedGraph(e.target.value)}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="">Select a causal graph...</option>
                {graphs.map((graph) => (
                  <option key={graph.id} value={graph.id}>
                    {graph.name} ({graph.nodes} nodes, {graph.edges} edges)
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Counterfactual Outcome Value
              </label>
              <Input
                value={counterfactualParams.outcome_value}
                onChange={(e) =>
                  setCounterfactualParams({
                    ...counterfactualParams,
                    outcome_value: e.target.value,
                  })
                }
                placeholder="e.g., 1.5"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Treatment Value
              </label>
              <Input
                value={counterfactualParams.treatment_value}
                onChange={(e) =>
                  setCounterfactualParams({
                    ...counterfactualParams,
                    treatment_value: e.target.value,
                  })
                }
                placeholder="e.g., 1000"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Outcome Value
              </label>
              <Input
                value={counterfactualParams.outcome_value}
                onChange={(e) =>
                  setCounterfactualParams({
                    ...counterfactualParams,
                    outcome_value: e.target.value,
                  })
                }
                placeholder="e.g., 1.5"
              />
            </div>
          </div>

          <Button
            onClick={handleCounterfactual}
            disabled={!selectedGraph || loading}
            className="w-full"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Computing...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <ArrowLeft className="h-4 w-4" /> Compute Counterfactual
              </span>
            )}
          </Button>

          {counterfactualResult && (
            <Card className="p-4 mt-4">
              <h3 className="font-medium mb-4">Counterfactual Result</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Factual Outcome</p>
                  <p className="text-2xl font-bold text-brand">
                    {counterfactualResult.factual_outcome?.toFixed(4)}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Counterfactual Outcome</p>
                  <p className="text-2xl font-bold text-brand">
                    {counterfactualResult.counterfactual_outcome?.toFixed(4)}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Difference</p>
                  <p className="text-2xl font-bold text-brand">
                    {(
                      (counterfactualResult.counterfactual_outcome || 0) -
                      (counterfactualResult.factual_outcome || 0)
                    ).toFixed(4)}
                  </p>
                </div>
              </div>

              {counterfactualResult.explanation && (
                <div className="mt-4 p-3 bg-muted/50 rounded-lg">
                  <h4 className="font-medium mb-2">Explanation</h4>
                  <p className="text-sm text-muted">
                    {counterfactualResult.explanation}
                  </p>
                </div>
              )}
            </Card>
          )}
        </TabsContent>

        {/* Discovery Tab */}
        <TabsContent value="discover" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Causal Discovery</h3>
              <p className="text-sm text-muted">
                Discover causal graphs from observational data
              </p>
            </div>
            <Button
              onClick={handleDiscover}
              disabled={loading || !discoveryParams.variables.length}
              className="ml-auto"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Discovering...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Microscope className="h-4 w-4" /> Discover Graph
                </span>
              )}
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Variables (comma-separated)
              </label>
              <Input
                value={discoveryParams.variables.join(", ")}
                onChange={(e) =>
                  setDiscoveryParams({
                    ...discoveryParams,
                    variables: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="X, Y, Z, confounder1, confounder2"
                className="w-full"
              />
              <p className="text-xs text-muted mt-1">
                Comma-separated variable names
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Discovery Method
              </label>
              <select
                value={discoveryParams.method}
                onChange={(e) =>
                  setDiscoveryParams({
                    ...discoveryParams,
                    method: e.target.value,
                  })
                }
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="pc">PC Algorithm (Constraint-based)</option>
                <option value="ges">GES (Score-based)</option>
                <option value="fci">FCI (Latent confounders)</option>
                <option value="notears">NOTEARS (Continuous)</option>
              </select>
            </div>
          </div>

          <Button
            onClick={handleDiscover}
            disabled={!discoveryParams.variables.length || loading}
            className="w-full"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Discovering...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Microscope className="h-4 w-4" /> Discover Graph
              </span>
            )}
          </Button>

          {discoveryResult && (
            <Card className="p-4 mt-4">
              <h3 className="font-medium mb-4">Discovered Graph</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Nodes</p>
                  <p className="text-2xl font-bold text-brand">
                    {discoveryResult.nodes?.length || 0}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Edges</p>
                  <p className="text-2xl font-bold text-brand">
                    {discoveryResult.edges?.length || 0}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Method</p>
                  <p className="font-medium capitalize">
                    {discoveryParams.method}
                  </p>
                </div>
                <div className="p-3 bg-muted/50 rounded-lg">
                  <p className="text-xs text-muted">Time</p>
                  <p className="font-medium">
                    {discoveryResult.time_seconds?.toFixed(2)}s
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="font-medium">Discovered Edges</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted border-b border-line">
                        <th className="pb-2 pr-4">From</th>
                        <th className="pb-2 pr-4">To</th>
                        <th className="pb-2 pr-4">Weight</th>
                        <th className="pb-2 pr-4">P-Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {discoveryResult.edges?.map((edge: any, i: number) => (
                        <tr key={i} className="border-b border-line/50">
                          <td className="py-2 pr-4 font-mono text-sm">
                            {edge.from}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm">
                            {edge.to}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm">
                            {edge.weight?.toFixed(4)}
                          </td>
                          <td className="py-2 pr-4 font-mono text-sm text-muted">
                            {edge.p_value?.toExponential(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Button
                  onClick={() => setSelectedGraph(discoveryResult.graph_id)}
                  className="w-full mt-4"
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Save as Causal Graph
                </Button>
              </div>
            </Card>
          )}
        </TabsContent>

        {/* Graph Registry Tab */}
        <TabsContent value="graphs-list" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-medium mb-1">Graph Registry</h3>
              <p className="text-sm text-muted">
                Manage and version your causal graphs
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchGraphs}
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
          ) : graphsList.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <GitBranch className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">No graphs registered</h3>
              <p className="text-muted text-sm mb-4">
                Create your first causal graph to get started
              </p>
              <Button
                onClick={() => {
                  setActiveTab("graphs");
                  setShowCreateModal(true);
                }}
              >
                <Plus className="h-4 w-4 mr-1" />
                Create Graph
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-line">
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4">Nodes</th>
                    <th className="pb-2 pr-4">Edges</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Created</th>
                    <th className="pb-2 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {graphsList.map((graph) => (
                    <tr
                      key={graph.id}
                      className="border-b border-line/50 hover:bg-muted/50"
                    >
                      <td className="py-3 pr-4 font-medium text-sm">
                        {graph.name}
                      </td>
                      <td className="py-3 pr-4">{graph.nodes}</td>
                      <td className="py-3 pr-4">{graph.edges}</td>
                      <td className="py-3 pr-4">
                        <Badge
                          tone={
                            graph.status === "active" ? "success" : "neutral"
                          }
                        >
                          {graph.status}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 text-sm text-muted">
                        {new Date(graph.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedGraph(graph.id);
                              setActiveTab("graphs");
                            }}
                          >
                            <Eye className="h-3.5 w-3.5" />
                            View
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteGraph(graph.id)}
                            className="text-red-500 hover:text-red-700"
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
