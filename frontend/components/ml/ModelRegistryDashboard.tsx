"use client";

/**
 * Model Registry Dashboard
 * Browse, register & deploy ML models with stage management
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useModelRegistry } from "@/hooks/useMLPlatform";
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
  Download,
  Upload,
  Eye,
  Edit,
  Trash2,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  Loader2,
  ExternalLink,
  GitBranch,
} from "lucide-react";
import { classNames } from "@/lib/utils";

interface ModelRegistryDashboardProps {
  organizationId: string;
  className?: string;
}

export function ModelRegistryDashboard({
  organizationId,
  className,
}: ModelRegistryDashboardProps) {
  const {
    models,
    loading,
    error,
    listModels,
    createModel,
    registerVersion,
    transitionStage,
    addArtifacts,
    createDeployment,
    listDeployments,
  } = useModelRegistry();
  const [activeTab, setActiveTab] = useState<
    "models" | "versions" | "deployments"
  >("models");
  const [searchQuery, setSearchQuery] = useState("");
  const [stageFilter, setStageFilter] = useState<
    "all" | "production" | "staging" | "archived" | "none"
  >("all");
  const [selectedModel, setSelectedModel] = useState<any>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showVersionModal, setShowVersionModal] = useState(false);
  const [showDeployModal, setShowDeployModal] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Create model form state
  const [newModel, setNewModel] = useState({
    name: "",
    description: "",
    tags: {},
  });
  // New version form state
  const [newVersion, setNewVersion] = useState({
    run_id: "",
    experiment_id: "",
    source: "",
    description: "",
    tags: {},
    params: {},
    metrics: {},
  });
  // Deploy form state
  const [newDeployment, setNewDeployment] = useState({
    endpoint_name: "",
    endpoint_url: "",
    replicas: 1,
    resources: {},
    config: {},
    health_check_url: "",
  });

  const filteredModels = useMemo(() => {
    return models
      .filter(
        (m) =>
          m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          m.description.toLowerCase().includes(searchQuery.toLowerCase()),
      )
      .filter(
        (m) =>
          stageFilter === "all" ||
          (stageFilter === "production" && m.production_version) ||
          (stageFilter === "staging" && m.staging_version) ||
          (stageFilter === "archived" &&
            m.versions.some((v) => v.stage === "archived")) ||
          (stageFilter === "none" &&
            !m.production_version &&
            !m.staging_version),
      );
  }, [models, searchQuery, stageFilter]);

  const fetchModels = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await listModels();
    } finally {
      setIsRefreshing(false);
    }
  }, [listModels]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const handleCreateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    await createModel(newModel);
    setShowCreateModal(false);
    setNewModel({ name: "", description: "", tags: {} });
    fetchModels();
  };

  const handleCreateVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel) return;
    await registerVersion(selectedModel.name, newVersion);
    setShowVersionModal(false);
    setNewVersion({
      run_id: "",
      experiment_id: "",
      source: "",
      description: "",
      tags: {},
      params: {},
      metrics: {},
    });
    fetchModels();
  };

  const handleDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel) return;
    const version =
      selectedModel.production_version || selectedModel.latest_version;
    await createDeployment({
      model_name: selectedModel.name,
      model_version: version,
      ...newDeployment,
    });
    setShowDeployModal(false);
    setNewDeployment({
      endpoint_name: "",
      endpoint_url: "",
      replicas: 1,
      resources: {},
      config: {},
      health_check_url: "",
    });
    // Switch to deployments tab
    setActiveTab("deployments");
  };

  const handleTransition = async (
    modelName: string,
    version: number,
    stage: "staging" | "production" | "archived",
  ) => {
    await transitionStage(modelName, version, stage as any);
    fetchModels();
  };

  const handleViewModel = (model: any) => {
    setSelectedModel(model);
    if (activeTab === "versions") setActiveTab("versions");
    else if (activeTab === "deployments") setActiveTab("deployments");
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
              <GitBranch className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">Model Registry</h2>
              <p className="text-sm text-muted">
                Browse, register & deploy ML models with stage management
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-2 bg-canvas border border-line rounded-lg px-3 py-1">
              <Search className="h-4 w-4 text-muted" />
              <input
                type="text"
                placeholder="Search models..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none w-64"
              />
            </div>

            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <Filter className="h-4 w-4 text-muted" />
              <select
                value={stageFilter}
                onChange={(e) => setStageFilter(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="all">All Stages</option>
                <option value="production">Production</option>
                <option value="staging">Staging</option>
                <option value="archived">Archived</option>
                <option value="none">Unstaged</option>
              </select>
            </div>

            <button
              onClick={fetchModels}
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

            <button
              onClick={() => setShowCreateModal(true)}
              className="p-2 rounded-lg bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Register Model</span>
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-3 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="models" className="py-2">
            Models
          </TabsTrigger>
          <TabsTrigger
            value="versions"
            className="py-2"
            disabled={!selectedModel}
          >
            Versions{" "}
            {selectedModel && `(${selectedModel.versions?.length || 0})`}
          </TabsTrigger>
          <TabsTrigger value="deployments" className="py-2">
            Deployments
          </TabsTrigger>
        </TabsList>

        {/* Models Tab */}
        <TabsContent value="models" className="flex-1 p-4 overflow-auto">
          {filteredModels.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <GitBranch className="h-12 w-12 text-muted/30 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-muted mb-2">
                No models found
              </h3>
              <p className="text-faint max-w-md mx-auto">
                Register your first ML model to get started
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-4 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-strong transition-colors"
              >
                Register Model
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredModels.map((model) => (
                <ModelCard
                  key={model.name}
                  model={model}
                  onView={handleViewModel}
                  onTransition={handleTransition}
                />
              ))}
            </div>
          )}
        </TabsContent>

        {/* Versions Tab */}
        <TabsContent value="versions" className="flex-1 p-4 overflow-auto">
          {selectedModel ? (
            <ModelVersionsPanel
              model={selectedModel}
              onCreateVersion={() => setShowVersionModal(true)}
              onTransition={handleTransition}
              onDeploy={() => {
                setShowDeployModal(true);
                setActiveTab("deployments");
              }}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <GitBranch className="h-12 w-12 text-muted/30 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-muted mb-2">
                Select a model
              </h3>
              <p className="text-faint">
                Choose a model from the Models tab to view its versions
              </p>
            </div>
          )}
        </TabsContent>

        {/* Deployments Tab */}
        <TabsContent value="deployments" className="flex-1 p-4 overflow-auto">
          <DeploymentsPanel
            organizationId={organizationId}
            selectedModel={selectedModel}
            onCreateDeploy={setShowDeployModal}
          />
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {showCreateModal && (
        <Modal
          open={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          title="Register New Model"
        >
          <form onSubmit={handleCreateModel} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Model Name *
              </label>
              <Input
                value={newModel.name}
                onChange={(e) =>
                  setNewModel({ ...newModel, name: e.target.value })
                }
                placeholder="e.g., customer-churn-predictor"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Description
              </label>
              <InputTextarea
                value={newModel.description}
                onChange={(e) =>
                  setNewModel({ ...newModel, description: e.target.value })
                }
                placeholder="Brief description of the model's purpose..."
                rows={3}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Tags (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(newModel.tags, null, 2)}
                onChange={(e) => {
                  try {
                    setNewModel({
                      ...newModel,
                      tags: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"domain": "customer", "team": "ml-team"}'
                rows={3}
                fontMonospace
              />
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t border-line">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowCreateModal(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Register Model</Button>
            </div>
          </form>
        </Modal>
      )}

      {showVersionModal && selectedModel && (
        <Modal
          open={showVersionModal}
          onClose={() => setShowVersionModal(false)}
          title={`New Version for ${selectedModel.name}`}
        >
          <form onSubmit={handleCreateVersion} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Run ID
              </label>
              <Input
                value={newVersion.run_id}
                onChange={(e) =>
                  setNewVersion({ ...newVersion, run_id: e.target.value })
                }
                placeholder="MLflow run ID"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Experiment ID
              </label>
              <Input
                value={newVersion.experiment_id}
                onChange={(e) =>
                  setNewVersion({
                    ...newVersion,
                    experiment_id: e.target.value,
                  })
                }
                placeholder="MLflow experiment ID"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Source Path
              </label>
              <Input
                value={newVersion.source}
                onChange={(e) =>
                  setNewVersion({ ...newVersion, source: e.target.value })
                }
                placeholder="s3://bucket/model/path or local path"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Description
              </label>
              <InputTextarea
                value={newVersion.description}
                onChange={(e) =>
                  setNewVersion({ ...newVersion, description: e.target.value })
                }
                placeholder="Description of this version..."
                rows={2}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Tags (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(newVersion.tags, null, 2)}
                onChange={(e) => {
                  try {
                    setNewVersion({
                      ...newVersion,
                      tags: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"framework": "pytorch", "dataset": "v2"}'
                rows={2}
                fontMonospace
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">
                  Params (JSON)
                </label>
                <InputTextarea
                  value={JSON.stringify(newVersion.params, null, 2)}
                  onChange={(e) => {
                    try {
                      setNewVersion({
                        ...newVersion,
                        params: JSON.parse(e.target.value),
                      });
                    } catch {}
                  }}
                  placeholder='{"learning_rate": 0.001, "epochs": 100}'
                  rows={3}
                  fontMonospace
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">
                  Metrics (JSON)
                </label>
                <InputTextarea
                  value={JSON.stringify(newVersion.metrics, null, 2)}
                  onChange={(e) => {
                    try {
                      setNewVersion({
                        ...newVersion,
                        metrics: JSON.parse(e.target.value),
                      });
                    } catch {}
                  }}
                  placeholder='{"accuracy": 0.95, "f1": 0.92}'
                  rows={3}
                  fontMonospace
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t border-line">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowVersionModal(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Create Version</Button>
            </div>
          </form>
        </Modal>
      )}

      {showDeployModal && selectedModel && (
        <Modal
          open={showDeployModal}
          onClose={() => setShowDeployModal(false)}
          title={`Deploy ${selectedModel.name}`}
        >
          <form onSubmit={handleDeploy} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Endpoint Name *
              </label>
              <Input
                value={newDeployment.endpoint_name}
                onChange={(e) =>
                  setNewDeployment({
                    ...newDeployment,
                    endpoint_name: e.target.value,
                  })
                }
                placeholder="e.g., churn-predictor-prod"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Endpoint URL *
              </label>
              <Input
                value={newDeployment.endpoint_url}
                onChange={(e) =>
                  setNewDeployment({
                    ...newDeployment,
                    endpoint_url: e.target.value,
                  })
                }
                placeholder="https://api.example.com/v1/predict"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1">
                  Replicas
                </label>
                <Input
                  type="number"
                  value={newDeployment.replicas}
                  onChange={(e) =>
                    setNewDeployment({
                      ...newDeployment,
                      replicas: parseInt(e.target.value),
                    })
                  }
                  min={1}
                  max={100}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1">
                  Health Check URL
                </label>
                <Input
                  value={newDeployment.health_check_url}
                  onChange={(e) =>
                    setNewDeployment({
                      ...newDeployment,
                      health_check_url: e.target.value,
                    })
                  }
                  placeholder="https://api.example.com/health"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Resources (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(newDeployment.resources, null, 2)}
                onChange={(e) => {
                  try {
                    setNewDeployment({
                      ...newDeployment,
                      resources: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"cpu": "2", "memory": "4Gi", "gpu": "1"}'
                rows={2}
                fontMonospace
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Config (JSON)
              </label>
              <InputTextarea
                value={JSON.stringify(newDeployment.config, null, 2)}
                onChange={(e) => {
                  try {
                    setNewDeployment({
                      ...newDeployment,
                      config: JSON.parse(e.target.value),
                    });
                  } catch {}
                }}
                placeholder='{"batch_size": 32, "timeout": 30}'
                rows={2}
                fontMonospace
              />
            </div>
            <div className="flex justify-end gap-2 pt-4 border-t border-line">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowDeployModal(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Create Deployment</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

// ==================== Model Card Component ====================

function ModelCard({
  model,
  onView,
  onTransition,
}: {
  model: any;
  onView: (model: any) => void;
  onTransition: (
    name: string,
    version: number,
    stage: "staging" | "production" | "archived",
  ) => void;
}) {
  const hasProduction = !!model.production_version;
  const hasStaging = !!model.staging_version;

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden transition-all hover:border-brand/30">
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <GitBranch className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h4 className="font-semibold text-ink truncate">{model.name}</h4>
              <p className="text-sm text-muted truncate">
                {model.description || "No description"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {model.production_version && (
              <Badge tone="success">
                Production v{model.production_version}
              </Badge>
            )}
            {model.staging_version && !model.production_version && (
              <Badge tone="warning">Staging v{model.staging_version}</Badge>
            )}
            {!model.production_version &&
              !model.staging_version &&
              model.versions.length > 0 && (
                <Badge tone="neutral">Unstaged</Badge>
              )}
            {model.versions.length === 0 && (
              <Badge tone="neutral">No Versions</Badge>
            )}
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-4 text-sm text-muted">
            <span>
              {model.versions.length} version
              {model.versions.length !== 1 ? "s" : ""}
            </span>
            {model.latest_version && (
              <span>Latest: v{model.latest_version}</span>
            )}
            {model.tags && Object.keys(model.tags).length > 0 && (
              <span>
                {Object.keys(model.tags).length} tag
                {Object.keys(model.tags).length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onView(model)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium text-brand hover:bg-brand/10 border border-brand/20 transition-colors"
            >
              <Eye className="h-3.5 w-3.5 inline mr-1" />
              View
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==================== Model Versions Panel ====================

function ModelVersionsPanel({
  model,
  onCreateVersion,
  onTransition,
  onDeploy,
}: any) {
  const [sortBy, setSortBy] = useState<"version" | "stage" | "created">(
    "version",
  );
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const sortedVersions = [...model.versions].sort((a, b) => {
    let aVal: any, bVal: any;
    if (sortBy === "version") {
      aVal = a.version;
      bVal = b.version;
    } else if (sortBy === "stage") {
      aVal = a.stage;
      bVal = b.stage;
    } else {
      aVal = new Date(a.created_at).getTime();
      bVal = new Date(b.created_at).getTime();
    }

    if (aVal < bVal) return sortOrder === "asc" ? -1 : 1;
    if (aVal > bVal) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-line bg-canvas/50">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-brand/10 text-brand">
              <GitBranch className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-semibold text-ink">{model.name}</h3>
              <p className="text-sm text-muted">
                {model.versions.length} version
                {model.versions.length !== 1 ? "s" : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 bg-canvas border border-line rounded-lg px-3 py-1">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none cursor-pointer"
              >
                <option value="version">Version</option>
                <option value="stage">Stage</option>
                <option value="created">Created Date</option>
              </select>
              <button
                onClick={() =>
                  setSortOrder(sortOrder === "asc" ? "desc" : "asc")
                }
                className="p-1 rounded hover:bg-muted text-muted"
                title="Toggle sort order"
              >
                {sortOrder === "asc" ? (
                  <ArrowUp className="h-4 w-4" />
                ) : (
                  <ArrowDown className="h-4 w-4" />
                )}
              </button>
            </div>

            <button
              onClick={onCreateVersion}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              New Version
            </button>

            <button
              onClick={onDeploy}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors flex items-center gap-1"
            >
              <ExternalLink className="h-4 w-4" />
              Deploy
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {model.versions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center">
            <GitBranch className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No versions yet
            </h3>
            <p className="text-faint mb-4">
              Create your first version to get started
            </p>
            <button
              onClick={onCreateVersion}
              className="px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-strong transition-colors"
            >
              Create Version
            </button>
          </div>
        ) : (
          <div className="divide-y divide-line">
            {sortedVersions.map((version: any) => (
              <VersionRow
                key={version.version}
                version={version}
                isProduction={model.production_version === version.version}
                isStaging={model.staging_version === version.version}
                onTransition={onTransition}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function VersionRow({
  version,
  isProduction,
  isStaging,
  onTransition,
}: {
  version: any;
  isProduction: boolean;
  isStaging: boolean;
  onTransition: (
    name: string,
    version: number,
    stage: "staging" | "production" | "archived",
  ) => void;
}) {
  const getStageBadge = () => {
    if (isProduction) return <Badge tone="success">Production</Badge>;
    if (isStaging) return <Badge tone="warning">Staging</Badge>;
    if (version.stage === "archived")
      return <Badge tone="neutral">Archived</Badge>;
    return <Badge tone="neutral">None</Badge>;
  };

  return (
    <div className="p-4 hover:bg-canvas/50 transition-colors">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="text-lg font-mono font-semibold text-ink">
            v{version.version}
          </div>
          {getStageBadge()}
        </div>

        <div className="flex items-center gap-4 text-sm text-muted flex-shrink-0">
          <span>{new Date(version.created_at).toLocaleDateString()}</span>
          {version.run_id && (
            <span className="font-mono text-xs">
              Run: {version.run_id.slice(0, 8)}
            </span>
          )}
          {version.metrics && Object.keys(version.metrics).length > 0 && (
            <span className="text-emerald-600">
              Metrics:{" "}
              {Object.entries(version.metrics)
                .map(([k, v]) => `${k}: ${v}`)
                .join(", ")}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {version.stage !== "production" && (
            <button
              onClick={() =>
                onTransition("model", version.version, "production")
              }
              className="px-2 py-1 text-xs font-medium bg-brand text-white hover:bg-brand-strong rounded transition-colors"
            >
              Promote to Production
            </button>
          )}
          {version.stage !== "staging" && !isProduction && (
            <button
              onClick={() => onTransition("model", version.version, "staging")}
              className="px-2 py-1 text-xs font-medium bg-amber-600 text-white hover:bg-amber-700 rounded transition-colors"
            >
              Promote to Staging
            </button>
          )}
          {version.stage !== "archived" && (
            <button
              onClick={() => onTransition("model", version.version, "archived")}
              className="px-2 py-1 text-xs font-medium bg-neutral text-white hover:bg-neutral-strong rounded transition-colors"
            >
              Archive
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ==================== Deployments Panel ====================

function DeploymentsPanel({
  organizationId,
  selectedModel,
  onCreateDeploy,
}: {
  organizationId: string;
  selectedModel: any | null;
  onCreateDeploy: () => void;
}) {
  const [deployments, setDeployments] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchDeployments = useCallback(async () => {
    setLoading(true);
    try {
      // This would call the deployments API
      setDeployments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDeployments();
  }, [fetchDeployments]);

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-line bg-canvas/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-100 text-emerald-600">
              <ExternalLink className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-semibold text-ink">Model Deployments</h3>
              <p className="text-sm text-muted">
                Manage and monitor deployed model endpoints
              </p>
            </div>
          </div>

          <button
            onClick={onCreateDeploy}
            disabled={!selectedModel}
            className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors flex items-center gap-1"
          >
            <Plus className="h-4 w-4" />
            New Deployment
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <Loader2 className="h-8 w-8 animate-spin text-brand" />
          </div>
        ) : deployments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center">
            <ExternalLink className="h-12 w-12 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">
              No deployments yet
            </h3>
            <p className="text-faint mb-4">
              Deploy a model version to create an endpoint
            </p>
            <button
              onClick={onCreateDeploy}
              disabled={!selectedModel}
              className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 transition-colors"
            >
              Create First Deployment
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {deployments.map((deployment: any) => (
              <DeploymentCard key={deployment.id} deployment={deployment} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DeploymentCard({ deployment }: { deployment: any }) {
  const statusColors =
    {
      running: "bg-emerald-100 text-emerald-700 border-emerald-200",
      deploying: "bg-blue-100 text-blue-700 border-blue-200",
      stopped: "bg-muted text-muted border-line",
      failed: "bg-red-100 text-red-700 border-red-200",
    }[deployment.status] || "bg-muted text-muted border-line";

  return (
    <div className="bg-canvas border border-line rounded-xl overflow-hidden">
      <div className="p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className="p-2 rounded-lg bg-emerald-100 text-emerald-600">
              <ExternalLink className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-ink truncate">
                  {deployment.endpoint_name}
                </h4>
                <Badge tone="neutral">
                  {deployment.model_name} v{deployment.model_version}
                </Badge>
              </div>
              <p className="text-sm text-muted truncate">
                {deployment.endpoint_url}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
            <span
              className={classNames(
                "px-2 py-1 rounded-full text-xs font-medium border",
                statusColors,
              )}
            >
              {deployment.status}
            </span>
            {deployment.replicas > 1 && (
              <span className="px-2 py-1 rounded-full text-xs font-medium bg-canvas border border-line">
                {deployment.replicas} replicas
              </span>
            )}
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-line flex items-center justify-between text-sm text-muted">
          <span>
            Created: {new Date(deployment.created_at).toLocaleDateString()}
          </span>
          {deployment.health_check_url && (
            <a
              href={deployment.health_check_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline flex items-center gap-1"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Health Check
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
