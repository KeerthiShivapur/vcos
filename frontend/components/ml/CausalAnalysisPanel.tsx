"use client";

/**
 * Causal Analysis Panel
 * Build causal graphs, estimate treatment effects, counterfactuals & mediation
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useCausalInference } from "@/hooks/useMLPlatform";
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
  Zap,
  GitBranch,
  Target,
  Link,
  RefreshCw,
  Loader2,
  Settings,
  Eye,
  Trash2,
  Download,
  Share2,
  Lightbulb,
  Brain,
  Database,
} from "lucide-react";
import { classNames } from "@/lib/utils";
import {
  CausalGraph,
  TreatmentEffect,
  CounterfactualResult,
  MediationAnalysis,
  CausalMethod,
  EstimatorType,
} from "@/hooks/useMLPlatform";

interface CausalAnalysisPanelProps {
  organizationId: string;
  className?: string;
}

export function CausalAnalysisPanel({
  organizationId,
  className,
}: CausalAnalysisPanelProps) {
  const {
    graphs,
    loading,
    error,
    createGraph,
    listGraphs,
    getGraph,
    validateGraph,
    visualizeGraph,
    registerData,
    listData,
    estimateEffect,
    estimateCounterfactual,
    mediationAnalysis,
    sensitivityAnalysis,
    discoverGraph,
  } = useCausalInference();

  const [activeTab, setActiveTab] = useState<
    | "graphs"
    | "estimate"
    | "counterfactual"
    | "mediation"
    | "sensitivity"
    | "discover"
    | "data"
  >("graphs");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedGraph, setSelectedGraph] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Graph form state
  const [showCreateGraph, setShowCreateGraph] = useState(false);
  const [newGraph, setNewGraph] = useState({
    name: "",
    nodes: [] as string[],
    edges: [] as string[][],
    latent_variables: [] as string[],
  });

  // Data state
  const [showRegisterData, setShowRegisterData] = useState(false);
  const [registerDataRequest, setRegisterDataRequest] = useState({
    name: "",
    data: [] as Record<string, any>[],
  });

  // Estimate effect state
  const [estimateRequest, setEstimateRequest] = useState({
    data_name: "",
    treatment: "",
    outcome: "",
    confounders: [] as string[],
    effect_modifiers: [] as string[],
    method: "backdoor" as
      | "backdoor"
      | "frontdoor"
      | "iv"
      | "mediation"
      | "double_ml"
      | "causal_forest"
      | "orthogonal_forest"
      | "s_learner"
      | "t_learner"
      | "x_learner"
      | "counterfactual",
    estimator: "linear_regression" as
      | "linear_regression"
      | "random_forest"
      | "gradient_boosting"
      | "neural_network"
      | "causal_forest"
      | "orthogonal_forest"
      | "dr_learner"
      | "x_learner",
    graph_name: "",
  });
  const [estimateResult, setEstimateResult] = useState<any | null>(null);
  const [estimating, setEstimating] = useState(false);

  // Counterfactual state
  const [counterfactualRequest, setCounterfactualRequest] = useState({
    data_name: "",
    treatment: "",
    outcome: "",
    confounders: [] as string[],
    factual_values: {} as Record<string, any>,
    counterfactual_values: {} as Record<string, any>,
  });
  const [counterfactualResult, setCounterfactualResult] = useState<any | null>(
    null,
  );
  const [estimatingCounterfactual, setEstimatingCounterfactual] =
    useState(false);

  // Mediation state
  const [mediationRequest, setMediationRequest] = useState({
    data_name: "",
    treatment: "",
    outcome: "",
    mediators: [] as string[],
    confounders: [] as string[],
  });
  const [mediationResult, setMediationResult] = useState<any | null>(null);
  const [runningMediation, setRunningMediation] = useState(false);

  // Sensitivity state
  const [sensitivityRequest, setSensitivityRequest] = useState({
    data_name: "",
    treatment: "",
    outcome: "",
    confounders: [] as string[],
    gamma_range: [0.5, 2.0] as [number, number],
    gamma_steps: 10,
  });
  const [sensitivityResult, setSensitivityResult] = useState<any | null>(null);
  const [runningSensitivity, setRunningSensitivity] = useState(false);

  // Discovery state
  const [discoverRequest, setDiscoverRequest] = useState({
    data_name: "",
    method: "pc",
    significance_level: 0.05,
  });
  const [discoveredGraph, setDiscoveredGraph] = useState<any | null>(null);
  const [discovering, setDiscovering] = useState(false);

  const fetchData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([listGraphs(), listData()]);
    } finally {
      setIsRefreshing(false);
    }
  }, [listGraphs, listData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreateGraph = async (e: React.FormEvent) => {
    e.preventDefault();
    await createGraph(newGraph);
    setShowCreateGraph(false);
    setNewGraph({ name: "", nodes: [], edges: [], latent_variables: [] });
    fetchData();
  };

  const handleRegisterData = async (e: React.FormEvent) => {
    e.preventDefault();
    await registerData(registerDataRequest.name, registerDataRequest.data);
    setShowRegisterData(false);
    setRegisterDataRequest({ name: "", data: [] });
    fetchData();
  };

  const handleEstimate = async (e: React.FormEvent) => {
    e.preventDefault();
    setEstimating(true);
    try {
      const result = await estimateEffect({
        data_name: estimateRequest.data_name,
        treatment: estimateRequest.treatment,
        outcome: estimateRequest.outcome,
        confounders: estimateRequest.confounders,
        effect_modifiers: estimateRequest.effect_modifiers,
        method: estimateRequest.method,
        estimator: estimateRequest.estimator,
        graph_name: estimateRequest.graph_name,
      });
      setEstimateResult(result);
    } catch (err) {
      console.error("Estimation failed:", err);
    } finally {
      setEstimating(false);
    }
  };

  const handleCounterfactual = async (e: React.FormEvent) => {
    e.preventDefault();
    setEstimatingCounterfactual(true);
    try {
      const result = await estimateCounterfactual(counterfactualRequest);
      setCounterfactualResult(result);
    } catch (err) {
      console.error("Counterfactual failed:", err);
    } finally {
      setEstimatingCounterfactual(false);
    }
  };

  const handleMediation = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunningMediation(true);
    try {
      const result = await mediationAnalysis(mediationRequest);
      setMediationResult(result);
    } catch (err) {
      console.error("Mediation failed:", err);
    } finally {
      setRunningMediation(false);
    }
  };

  const handleSensitivity = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunningSensitivity(true);
    try {
      const result = await sensitivityAnalysis(sensitivityRequest);
      setSensitivityResult(result);
    } catch (err) {
      console.error("Sensitivity failed:", err);
    } finally {
      setRunningSensitivity(false);
    }
  };

  const handleDiscover = async (e: React.FormEvent) => {
    e.preventDefault();
    setDiscovering(true);
    try {
      const result = await discoverGraph(discoverRequest);
      setDiscoveredGraph(result);
    } catch (err) {
      console.error("Discovery failed:", err);
    } finally {
      setDiscovering(false);
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
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">
                Causal Analysis
              </h2>
              <p className="text-sm text-muted">
                Build graphs, estimate effects, counterfactuals & mediation
                analysis
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={fetchData}
              disabled={isRefreshing}
              className="p-2 rounded-lg bg-canvas border border-line text-ink hover:bg-muted transition-colors"
              title="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </button>

            <button
              onClick={() => setShowCreateGraph(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New Graph</span>
            </button>

            <button
              onClick={() => setShowRegisterData(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Register Data</span>
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-7 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="graphs" className="py-2 flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            Causal Graphs
          </TabsTrigger>
          <TabsTrigger value="data" className="py-2 flex items-center gap-2">
            <Database className="h-4 w-4" />
            Data
          </TabsTrigger>
          <TabsTrigger
            value="estimate"
            className="py-2 flex items-center gap-2"
          >
            <Target className="h-4 w-4" />
            Estimate Effect
          </TabsTrigger>
          <TabsTrigger
            value="counterfactual"
            className="py-2 flex items-center gap-2"
          >
            <Lightbulb className="h-4 w-4" />
            Counterfactuals
          </TabsTrigger>
          <TabsTrigger
            value="mediation"
            className="py-2 flex items-center gap-2"
          >
            <Link className="h-4 w-4" />
            Mediation
          </TabsTrigger>
          <TabsTrigger
            value="sensitivity"
            className="py-2 flex items-center gap-2"
          >
            <Settings className="h-4 w-4" />
            Sensitivity
          </TabsTrigger>
          <TabsTrigger
            value="discover"
            className="py-2 flex items-center gap-2"
          >
            <Zap className="h-4 w-4" />
            Discovery
          </TabsTrigger>
        </TabsList>

        {/* Graphs Tab */}
        <TabsContent value="graphs" className="flex-1 p-4 overflow-auto">
          <GraphsPanel
            graphs={graphs}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            loading={loading}
            selectedGraph={selectedGraph}
            setSelectedGraph={setSelectedGraph}
            onCreate={setShowCreateGraph}
            onRefresh={fetchData}
            onView={setSelectedGraph}
          />
        </TabsContent>

        {/* Data Tab */}
        <TabsContent value="data" className="flex-1 p-4 overflow-auto">
          <DataPanel
            dataSources={listData()}
            loading={loading}
            onRegister={setShowRegisterData}
            onRefresh={fetchData}
          />
        </TabsContent>

        {/* Estimate Effect Tab */}
        <TabsContent value="estimate" className="flex-1 p-4 overflow-auto">
          <EstimatePanel
            dataSources={listData()}
            graphs={graphs}
            estimateRequest={estimateRequest}
            setEstimateRequest={setEstimateRequest}
            estimateResult={estimateResult}
            estimating={estimating}
            onEstimate={handleEstimate}
          />
        </TabsContent>

        {/* Counterfactual Tab */}
        <TabsContent
          value="counterfactual"
          className="flex-1 p-4 overflow-auto"
        >
          <CounterfactualPanel
            dataSources={listData()}
            counterfactualRequest={counterfactualRequest}
            setCounterfactualRequest={setCounterfactualRequest}
            counterfactualResult={counterfactualResult}
            estimating={estimatingCounterfactual}
            onEstimate={handleCounterfactual}
          />
        </TabsContent>

        {/* Mediation Tab */}
        <TabsContent value="mediation" className="flex-1 p-4 overflow-auto">
          <MediationPanel
            dataSources={listData()}
            mediationRequest={mediationRequest}
            setMediationRequest={setMediationRequest}
            mediationResult={mediationResult}
            running={runningMediation}
            onRun={handleMediation}
          />
        </TabsContent>

        {/* Sensitivity Tab */}
        <TabsContent value="sensitivity" className="flex-1 p-4 overflow-auto">
          <SensitivityPanel
            dataSources={listData()}
            sensitivityRequest={sensitivityRequest}
            setSensitivityRequest={setSensitivityRequest}
            sensitivityResult={sensitivityResult}
            running={runningSensitivity}
            onRun={handleSensitivity}
          />
        </TabsContent>

        {/* Discovery Tab */}
        <TabsContent value="discover" className="flex-1 p-4 overflow-auto">
          <DiscoveryPanel
            dataSources={listData()}
            discoverRequest={discoverRequest}
            setDiscoverRequest={setDiscoverRequest}
            discoveredGraph={discoveredGraph}
            discovering={discovering}
            onDiscover={handleDiscover}
          />
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {createGraphModal()}
      {registerDataModal()}
    </div>
  );

  function createGraphModal() {
    return (
      <Modal
        open={showCreateGraph}
        onClose={() => setShowCreateGraph(false)}
        title="Create Causal Graph"
        size="lg"
      >
        <form
          onSubmit={handleCreateGraph}
          className="space-y-4 max-h-[80vh] overflow-y-auto"
        >
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Graph Name *
            </label>
            <Input
              value={newGraph.name}
              onChange={(e) =>
                setNewGraph({ ...newGraph, name: e.target.value })
              }
              placeholder="e.g., customer_churn_causal"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Nodes (comma-separated) *
            </label>
            <Input
              value={newGraph.nodes.join(", ")}
              onChange={(e) =>
                setNewGraph({
                  ...newGraph,
                  nodes: e.target.value
                    .split(",")
                    .map((n) => n.trim())
                    .filter(Boolean),
                })
              }
              placeholder="e.g., price, demand, marketing_spend, seasonality"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Edges (one per line: cause &rarr; effect) *
            </label>
            <InputTextarea
              value={newGraph.edges.map((e) => e.join(" -> ")).join("\n")}
              onChange={(e) =>
                setNewGraph({
                  ...newGraph,
                  edges: e.target.value
                    .split("\n")
                    .map((line) => line.split("->").map((s) => s.trim()))
                    .filter((e) => e.length === 2),
                })
              }
              placeholder="price -> demand\nmarketing_spend -> demand\nseasonality -> demand"
              rows={4}
              fontMonospace
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Latent Variables (comma-separated)
            </label>
            <Input
              value={newGraph.latent_variables.join(", ")}
              onChange={(e) =>
                setNewGraph({
                  ...newGraph,
                  latent_variables: e.target.value
                    .split(",")
                    .map((v) => v.trim())
                    .filter(Boolean),
                })
              }
              placeholder="e.g., unobserved_confounder"
            />
          </div>
          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowCreateGraph(false)}
            >
              Cancel
            </Button>
            <Button type="submit">Create Graph</Button>
          </div>
        </form>
      </Modal>
    );
  }

  function registerDataModal() {
    return (
      <Modal
        open={showRegisterData}
        onClose={() => setShowRegisterData(false)}
        title="Register Data for Causal Analysis"
        size="lg"
      >
        <form
          onSubmit={handleRegisterData}
          className="space-y-4 max-h-[80vh] overflow-y-auto"
        >
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Data Name *
            </label>
            <Input
              value={registerDataRequest.name}
              onChange={(e) =>
                setRegisterDataRequest({
                  ...registerDataRequest,
                  name: e.target.value,
                })
              }
              placeholder="e.g., customer_churn_data"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Data (JSON array of objects)
            </label>
            <InputTextarea
              value={JSON.stringify(registerDataRequest.data, null, 2)}
              onChange={(e) => {
                try {
                  setRegisterDataRequest({
                    ...registerDataRequest,
                    data: JSON.parse(e.target.value),
                  });
                } catch {}
              }}
              placeholder='[{"treatment": 1, "outcome": 100, "confounder": 0.5}, ...]'
              rows={6}
              fontMonospace
            />
          </div>
          {registerDataRequest.data.length > 0 && (
            <div className="p-3 bg-canvas border border-line rounded">
              <p className="text-sm font-medium text-ink mb-1">
                Preview ({registerDataRequest.data.length} rows):
              </p>
              <div className="overflow-x-auto text-xs font-mono max-h-40 overflow-y-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-line">
                      {Object.keys(registerDataRequest.data[0]).map((key) => (
                        <th key={key} className="p-1 text-left">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {registerDataRequest.data.slice(0, 5).map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((val, j) => (
                          <td key={j} className="p-1">
                            {String(val)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {registerDataRequest.data.length > 5 && (
                <p className="text-xs text-muted mt-1">
                  ... and {registerDataRequest.data.length - 5} more rows
                </p>
              )}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setShowRegisterData(false);
                setRegisterDataRequest({ name: "", data: [] });
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                !registerDataRequest.name ||
                registerDataRequest.data.length === 0
              }
            >
              Register Data
            </Button>
          </div>
        </form>
      </Modal>
    );
  }
}

function GraphsPanel({
  graphs,
  searchQuery,
  setSearchQuery,
  loading,
  selectedGraph,
  setSelectedGraph,
  onCreate,
  onRefresh,
  onView,
}: {
  graphs: any[];
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  loading: boolean;
  selectedGraph: string | null;
  setSelectedGraph: (s: string | null) => void;
  onCreate: () => void;
  onRefresh: () => void;
  onView: (name: string) => void;
}) {
  const filtered = useMemo(
    () =>
      graphs.filter(
        (g) =>
          g.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          g.nodes.some((n: string) =>
            n.toLowerCase().includes(searchQuery.toLowerCase()),
          ),
      ),
    [graphs, searchQuery],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search graphs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-64"
          />
          <Button onClick={onRefresh} variant="outline" disabled={loading}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button onClick={onCreate}>
            <Plus className="h-4 w-4 mr-1" /> New Graph
          </Button>
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <GitBranch className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No causal graphs yet
            </h3>
            <p className="text-faint max-w-md mx-auto">
              Create your first causal graph to start analyzing causal
              relationships
            </p>
            <Button onClick={onCreate} className="mt-4">
              <Plus className="h-4 w-4 mr-1" /> Create Graph
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((graph) => (
              <GraphCard
                key={graph.name}
                graph={graph}
                isSelected={selectedGraph === graph.name}
                onSelect={() => setSelectedGraph(graph.name)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function GraphCard({
  graph,
  isSelected,
  onSelect,
}: {
  graph: any;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <div
      className={classNames(
        "p-4 rounded-xl bg-canvas border border-line transition-all cursor-pointer hover:border-brand/30",
        isSelected && "border-brand bg-brand/5",
      )}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="p-2 rounded-lg bg-brand/10 text-brand">
            <GitBranch className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h4 className="font-semibold text-ink truncate">{graph.name}</h4>
            <div className="flex items-center gap-2 text-sm text-muted mt-1">
              <span>{graph.nodes.length} nodes</span>
              <span>•</span>
              <span>{graph.edges.length} edges</span>
              {graph.latent_variables.length > 0 && (
                <span className="text-amber-600">
                  {graph.latent_variables.length} latent
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Badge tone="neutral">{graph.nodes.length} nodes</Badge>
          <Badge tone="neutral">{graph.edges.length} edges</Badge>
        </div>
      </div>
    </div>
  );
}

// The remaining panels (EstimatePanel, CounterfactualPanel, MediationPanel, SensitivityPanel, DiscoveryPanel, DataPanel)
// would follow similar patterns. Due to length constraints, I'll provide the key ones.

function EstimatePanel({
  dataSources,
  graphs,
  estimateRequest,
  setEstimateRequest,
  estimateResult,
  estimating,
  onEstimate,
}: any) {
  return (
    <div className="space-y-6">
      <Card
        title="Estimate Treatment Effect"
        subtitle="Configure causal estimation parameters"
      >
        <form onSubmit={onEstimate} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={estimateRequest.data_name}
                onValueChange={(v) =>
                  setEstimateRequest({ ...estimateRequest, data_name: v })
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
                Treatment Variable *
              </label>
              <Input
                value={estimateRequest.treatment}
                onChange={(e) =>
                  setEstimateRequest({
                    ...estimateRequest,
                    treatment: e.target.value,
                  })
                }
                placeholder="e.g., treatment, price, marketing_spend"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Outcome Variable *
              </label>
              <Input
                value={estimateRequest.outcome}
                onChange={(e) =>
                  setEstimateRequest({
                    ...estimateRequest,
                    outcome: e.target.value,
                  })
                }
                placeholder="e.g., sales, conversion, churn"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Confounders (comma-separated)
              </label>
              <Input
                value={estimateRequest.confounders.join(", ")}
                onChange={(e) =>
                  setEstimateRequest({
                    ...estimateRequest,
                    confounders: e.target.value
                      .split(",")
                      .map((c) => c.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="e.g., age, income, region, season"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Effect Modifiers (comma-separated)
              </label>
              <Input
                value={estimateRequest.effect_modifiers.join(", ")}
                onChange={(e) =>
                  setEstimateRequest({
                    ...estimateRequest,
                    effect_modifiers: e.target.value
                      .split(",")
                      .map((c) => c.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="e.g., segment, channel, region"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Causal Graph (optional)
              </label>
              <Select
                value={estimateRequest.graph_name}
                onValueChange={(v) =>
                  setEstimateRequest({ ...estimateRequest, graph_name: v })
                }
                options={[
                  { value: "", label: "None (auto)" },
                  ...graphs.map((g) => ({ value: g.name, label: g.name })),
                ]}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Method
              </label>
              <Select
                value={estimateRequest.method}
                onValueChange={(v) =>
                  setEstimateRequest({ ...estimateRequest, method: v as any })
                }
                options={[
                  { value: "backdoor", label: "Backdoor Adjustment" },
                  { value: "frontdoor", label: "Frontdoor Adjustment" },
                  { value: "iv", label: "Instrumental Variable" },
                  { value: "double_ml", label: "Double ML" },
                  { value: "causal_forest", label: "Causal Forest" },
                  { value: "orthogonal_forest", label: "Orthogonal Forest" },
                  { value: "s_learner", label: "S-Learner" },
                  { value: "t_learner", label: "T-Learner" },
                  { value: "x_learner", label: "X-Learner" },
                  { value: "counterfactual", label: "Counterfactual" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Estimator
              </label>
              <Select
                value={estimateRequest.estimator}
                onValueChange={(v) =>
                  setEstimateRequest({
                    ...estimateRequest,
                    estimator: v as any,
                  })
                }
                options={[
                  { value: "linear_regression", label: "Linear Regression" },
                  { value: "random_forest", label: "Random Forest" },
                  { value: "gradient_boosting", label: "Gradient Boosting" },
                  { value: "neural_network", label: "Neural Network" },
                  { value: "causal_forest", label: "Causal Forest" },
                  { value: "orthogonal_forest", label: "Orthogonal Forest" },
                  { value: "dr_learner", label: "DR Learner" },
                  { value: "x_learner", label: "X-Learner" },
                ]}
              />
            </div>
          </div>

          <Button
            type="submit"
            disabled={estimating}
            className="w-full md:w-auto"
          >
            {estimating ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Estimating...
              </>
            ) : (
              <>
                <Target className="h-4 w-4 mr-1" />
                Estimate Effect
              </>
            )}
          </Button>
        </form>
      </Card>

      {estimateResult && (
        <Card
          title="Estimation Results"
          subtitle={`Method: ${estimateResult.method} • Estimator: ${estimateResult.estimator}`}
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <MetricCard
              label="ATE"
              value={estimateResult.ate.toFixed(4)}
              icon={Target}
            />
            <MetricCard
              label="95% CI"
              value={`[${estimateResult.ate_ci[0].toFixed(4)}, ${estimateResult.ate_ci[1].toFixed(4)}]`}
              icon={Target}
            />
            <MetricCard
              label="P-value"
              value={estimateResult.ate_pvalue.toFixed(4)}
              icon={Target}
            />
          </div>

          {estimateResult.cate &&
            Object.keys(estimateResult.cate).length > 0 && (
              <div className="mb-6">
                <h4 className="font-medium text-ink mb-3">
                  Conditional Average Treatment Effects (CATE)
                </h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(estimateResult.cate).map(
                    ([subgroup, value]) => (
                      <MetricCard
                        key={subgroup}
                        label={subgroup}
                        value={value.toFixed(4)}
                        icon={Target}
                      />
                    ),
                  )}
                </div>
              </div>
            )}

          {estimateResult.ite && estimateResult.ite.length > 0 && (
            <div className="mb-6">
              <h4 className="font-medium text-ink mb-3">
                Individual Treatment Effects (first 20)
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-muted">
                      <th className="pb-2">Index</th>
                      <th className="pb-2">ITE</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {estimateResult.ite.slice(0, 20).map((ite, i) => (
                      <tr key={i} className="hover:bg-canvas/50">
                        <td className="py-2 font-mono">{i}</td>
                        <td className="py-2">{ite.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="p-3 rounded-lg bg-canvas border border-line">
            <h4 className="font-medium text-ink mb-2">
              Assumptions & Diagnostics
            </h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="font-medium text-ink mb-1">Assumptions</p>
                <pre className="text-xs text-muted bg-canvas/50 p-2 rounded">
                  {JSON.stringify(estimateResult.assumptions, null, 2)}
                </pre>
              </div>
              <div>
                <p className="font-medium text-ink mb-1">Diagnostics</p>
                <pre className="text-xs text-muted bg-canvas/50 p-2 rounded">
                  {JSON.stringify(estimateResult.diagnostics, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function CounterfactualPanel({
  dataSources,
  counterfactualRequest,
  setCounterfactualRequest,
  counterfactualResult,
  estimating,
  onEstimate,
}: any) {
  return (
    <div className="space-y-6">
      <Card
        title="Counterfactual Estimation"
        subtitle="What would have happened if...?"
      >
        <form onSubmit={onEstimate} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={counterfactualRequest.data_name}
                onValueChange={(v) =>
                  setCounterfactualRequest({
                    ...counterfactualRequest,
                    data_name: v,
                  })
                }
                options={dataSources.map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
                placeholder="Select data source"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Treatment Variable *
              </label>
              <Input
                value={counterfactualRequest.treatment}
                onChange={(e) =>
                  setCounterfactualRequest({
                    ...counterfactualRequest,
                    treatment: e.target.value,
                  })
                }
                placeholder="e.g., treatment"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Outcome Variable *
              </label>
              <Input
                value={counterfactualRequest.outcome}
                onChange={(e) =>
                  setCounterfactualRequest({
                    ...counterfactualRequest,
                    outcome: e.target.value,
                  })
                }
                placeholder="e.g., outcome"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Confounders (comma-separated)
              </label>
              <Input
                value={counterfactualRequest.confounders.join(", ")}
                onChange={(e) =>
                  setCounterfactualRequest({
                    ...counterfactualRequest,
                    confounders: e.target.value
                      .split(",")
                      .map((c) => c.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="e.g., age, income, region"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Factual Values (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(
                  counterfactualRequest.factual_values,
                  null,
                  2,
                )}
                onChange={(e) => {
                  try {
                    setCounterfactualRequest({
                      ...counterfactualRequest,
                      factual_values: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"treatment": 1, "age": 35, "income": 50000}'
                rows={4}
                fontMonospace
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Counterfactual Values (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(
                  counterfactualRequest.counterfactual_values,
                  null,
                  2,
                )}
                onChange={(e) => {
                  try {
                    setCounterfactualRequest({
                      ...counterfactualRequest,
                      counterfactual_values: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"treatment": 0, "age": 35, "income": 50000}'
                rows={4}
                fontMonospace
              />
            </div>
          </div>

          <Button
            type="submit"
            disabled={estimating}
            className="w-full md:w-auto"
          >
            {estimating ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Estimating...
              </>
            ) : (
              <>
                <Lightbulb className="h-4 w-4 mr-1" />
                Estimate Counterfactual
              </>
            )}
          </Button>
        </form>
      </Card>

      {counterfactualResult && (
        <Card
          title="Counterfactual Result"
          subtitle="What would have happened if treatment was different?"
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <MetricCard
              label="Factual Outcome"
              value={counterfactualResult.factual_outcome.toFixed(4)}
              icon={Target}
            />
            <MetricCard
              label="Counterfactual Outcome"
              value={counterfactualResult.counterfactual_outcome.toFixed(4)}
              icon={Lightbulb}
            />
            <MetricCard
              label="Effect"
              value={counterfactualResult.effect.toFixed(4)}
              icon={Zap}
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <MetricCard
              label="P(Necessary)"
              value={counterfactualResult.probability_necessary.toFixed(3)}
              icon={Lightbulb}
            />
            <MetricCard
              label="P(Sufficient)"
              value={counterfactualResult.probability_sufficient.toFixed(3)}
              icon={Lightbulb}
            />
          </div>
          <div className="p-3 rounded-lg bg-canvas border border-line">
            <p className="text-sm text-muted">
              {counterfactualResult.explanation}
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}

function MediationPanel({
  dataSources,
  mediationRequest,
  setMediationRequest,
  mediationResult,
  running,
  onRun,
}: any) {
  return (
    <div className="space-y-6">
      <Card
        title="Mediation Analysis"
        subtitle="Decompose total effect into direct and indirect effects"
      >
        <form onSubmit={onRun} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={mediationRequest.data_name}
                onValueChange={(v) =>
                  setMediationRequest({ ...mediationRequest, data_name: v })
                }
                options={dataSources.map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Treatment *
              </label>
              <Input
                value={mediationRequest.treatment}
                onChange={(e) =>
                  setMediationRequest({
                    ...mediationRequest,
                    treatment: e.target.value,
                  })
                }
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Outcome *
              </label>
              <Input
                value={mediationRequest.outcome}
                onChange={(e) =>
                  setMediationRequest({
                    ...mediationRequest,
                    outcome: e.target.value,
                  })
                }
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Mediators (comma-separated) *
              </label>
              <Input
                value={mediationRequest.mediators.join(", ")}
                onChange={(e) =>
                  setMediationRequest({
                    ...mediationRequest,
                    mediators: e.target.value
                      .split(",")
                      .map((m) => m.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="e.g., mediator1, mediator2"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Confounders (comma-separated)
              </label>
              <Input
                value={mediationRequest.confounders.join(", ")}
                onChange={(e) =>
                  setMediationRequest({
                    ...mediationRequest,
                    confounders: e.target.value
                      .split(",")
                      .map((c) => c.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="e.g., age, income, region"
              />
            </div>
          </div>

          <Button type="submit" disabled={running} className="w-full md:w-auto">
            {running ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Link className="h-4 w-4 mr-1" />
                Run Mediation Analysis
              </>
            )}
          </Button>
        </form>
      </Card>

      {mediationResult && (
        <Card title="Mediation Results" subtitle="Effect decomposition">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <MetricCard
              label="Total Effect"
              value={mediationResult.total_effect.toFixed(4)}
              icon={Target}
            />
            <MetricCard
              label="Direct Effect"
              value={mediationResult.direct_effect.toFixed(4)}
              icon={Target}
            />
            <MetricCard
              label="Indirect Effect"
              value={mediationResult.indirect_effect.toFixed(4)}
              icon={Link}
            />
            <MetricCard
              label="Proportion Mediated"
              value={`${(mediationResult.proportion_mediated * 100).toFixed(1)}%`}
              icon={Link}
            />
          </div>

          {mediationResult.mediator_effects &&
            Object.keys(mediationResult.mediator_effects).length > 0 && (
              <div>
                <h4 className="font-medium text-ink mb-3">Mediator Effects</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(mediationResult.mediator_effects).map(
                    ([mediator, effect]) => (
                      <MetricCard
                        key={mediator}
                        label={mediator}
                        value={effect.toFixed(4)}
                        icon={Link}
                      />
                    ),
                  )}
                </div>
              </div>
            )}
        </Card>
      )}
    </div>
  );
}

function SensitivityPanel({
  dataSources,
  sensitivityRequest,
  setSensitivityRequest,
  sensitivityResult,
  running,
  onRun,
}: any) {
  return (
    <div className="space-y-6">
      <Card
        title="Sensitivity Analysis"
        subtitle="How robust are your causal estimates to unobserved confounding?"
      >
        <form onSubmit={onRun} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={sensitivityRequest.data_name}
                onValueChange={(v) =>
                  setSensitivityRequest({ ...sensitivityRequest, data_name: v })
                }
                options={dataSources.map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Treatment *
              </label>
              <Input
                value={sensitivityRequest.treatment}
                onChange={(e) =>
                  setSensitivityRequest({
                    ...sensitivityRequest,
                    treatment: e.target.value,
                  })
                }
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Outcome *
              </label>
              <Input
                value={sensitivityRequest.outcome}
                onChange={(e) =>
                  setSensitivityRequest({
                    ...sensitivityRequest,
                    outcome: e.target.value,
                  })
                }
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Confounders (comma-separated)
              </label>
              <Input
                value={sensitivityRequest.confounders.join(", ")}
                onChange={(e) =>
                  setSensitivityRequest({
                    ...sensitivityRequest,
                    confounders: e.target.value
                      .split(",")
                      .map((c) => c.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="e.g., age, income, region"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Gamma Range
              </label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  value={sensitivityRequest.gamma_range[0]}
                  onChange={(e) =>
                    setSensitivityRequest({
                      ...sensitivityRequest,
                      gamma_range: [
                        parseFloat(e.target.value),
                        sensitivityRequest.gamma_range[1],
                      ],
                    })
                  }
                  min={0.1}
                  max={10}
                  step={0.1}
                  placeholder="Min"
                  className="w-24"
                />
                <span className="text-muted">to</span>
                <Input
                  type="number"
                  value={sensitivityRequest.gamma_range[1]}
                  onChange={(e) =>
                    setSensitivityRequest({
                      ...sensitivityRequest,
                      gamma_range: [
                        sensitivityRequest.gamma_range[0],
                        parseFloat(e.target.value),
                      ],
                    })
                  }
                  min={0.1}
                  max={10}
                  step={0.1}
                  placeholder="Max"
                  className="w-24"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Gamma Steps
              </label>
              <Input
                type="number"
                value={sensitivityRequest.gamma_steps}
                onChange={(e) =>
                  setSensitivityRequest({
                    ...sensitivityRequest,
                    gamma_steps: parseInt(e.target.value),
                  })
                }
                min={5}
                max={50}
                className="w-24"
              />
            </div>
          </div>

          <Button type="submit" disabled={running} className="w-full md:w-auto">
            {running ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Settings className="h-4 w-4 mr-1" />
                Run Sensitivity Analysis
              </>
            )}
          </Button>
        </form>
      </Card>

      {sensitivityResult && (
        <Card
          title="Sensitivity Analysis Results"
          subtitle="Bounds on ATE under unobserved confounding"
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-muted">
                  <th className="pb-2">Gamma</th>
                  <th className="pb-2">ATE Lower Bound</th>
                  <th className="pb-2">ATE Upper Bound</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {sensitivityResult.results?.map((r: any, i: number) => (
                  <tr key={i} className="hover:bg-canvas/50">
                    <td className="py-2 font-mono">{r.gamma.toFixed(2)}</td>
                    <td className="py-2">
                      {r.ate_bound_lower?.toFixed(4) ?? "N/A"}
                    </td>
                    <td className="py-2">
                      {r.ate_bound_upper?.toFixed(4) ?? "N/A"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 p-3 rounded-lg bg-canvas border border-line text-sm text-muted">
            {sensitivityResult.interpretation}
          </div>
        </Card>
      )}
    </div>
  );
}

function DiscoveryPanel({
  dataSources,
  discoverRequest,
  setDiscoverRequest,
  discoveredGraph,
  discovering,
  onDiscover,
}: any) {
  return (
    <div className="space-y-6">
      <Card
        title="Causal Discovery"
        subtitle="Learn causal structure from observational data"
      >
        <form onSubmit={onDiscover} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Data Source *
              </label>
              <Select
                value={discoverRequest.data_name}
                onValueChange={(v) =>
                  setDiscoverRequest({ ...discoverRequest, data_name: v })
                }
                options={dataSources.map((d) => ({
                  value: d.name,
                  label: d.name,
                }))}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Method
              </label>
              <Select
                value={discoverRequest.method}
                onValueChange={(v) =>
                  setDiscoverRequest({ ...discoverRequest, method: v })
                }
                options={[
                  { value: "pc", label: "PC Algorithm" },
                  { value: "ges", label: "GES" },
                  { value: "fci", label: "FCI" },
                ]}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Significance Level
              </label>
              <Input
                type="number"
                value={discoverRequest.significance_level}
                onChange={(e) =>
                  setDiscoverRequest({
                    ...discoverRequest,
                    significance_level: parseFloat(e.target.value),
                  })
                }
                min={0.001}
                max={0.1}
                step={0.001}
                className="w-32"
              />
            </div>
          </div>

          <Button
            type="submit"
            disabled={discovering}
            className="w-full md:w-auto"
          >
            {discovering ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Discovering...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4 mr-1" />
                Discover Causal Graph
              </>
            )}
          </Button>
        </form>
      </Card>

      {discoveredGraph && (
        <Card
          title="Discovered Causal Graph"
          subtitle={`${discoveredGraph.nodes.length} nodes, ${discoveredGraph.edges.length} edges`}
        >
          <div className="font-mono text-sm bg-canvas/50 p-4 rounded max-h-96 overflow-auto">
            <pre>{JSON.stringify(discoveredGraph, null, 2)}</pre>
          </div>
        </Card>
      )}
    </div>
  );
}

function DataPanel({ dataSources, loading, onRegister, onRefresh }: any) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <Button onClick={onRefresh} variant="outline" disabled={loading}>
            <RefreshCw className="h-4 w-4 mr-1" /> Refresh
          </Button>
          <Button onClick={onRegister}>
            <Plus className="h-4 w-4 mr-1" /> Register Data
          </Button>
        </div>

        {dataSources.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Database className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No data registered
            </h3>
            <p className="text-faint max-w-md mx-auto">
              Register data to use for causal analysis
            </p>
            <Button onClick={onRegister} className="mt-4">
              <Plus className="h-4 w-4 mr-1" /> Register Data
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {dataSources.map((ds: any) => (
              <div
                key={ds.name}
                className="p-4 rounded-lg bg-canvas border border-line flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-brand/10 text-brand">
                    <Database className="h-5 w-5" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-ink">{ds.name}</h4>
                    <p className="text-sm text-muted">
                      {ds.shape?.join(" × ") || "Unknown shape"} •{" "}
                      {Object.keys(ds.columns || {}).length} columns
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">{ds.rows || 0} rows</Badge>
                </div>
              </div>
            ))}
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
