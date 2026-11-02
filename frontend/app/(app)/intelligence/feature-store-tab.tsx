"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  Search,
  Filter,
  Database,
  Eye,
  Edit,
  Trash2,
  Download,
  Upload,
  RefreshCw,
  Loader2,
  Key,
  Layers,
  Zap,
  Server,
  X,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Modal } from "@/components/ui/Modal";
import { Textarea } from "@/components/ui/Textarea";
import { classNames } from "@/lib/utils";

interface FeatureStoreExplorerProps {
  organizationId: string;
  className?: string;
}

export function FeatureStoreExplorer({
  organizationId,
  className,
}: FeatureStoreExplorerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);

  // Entity state
  const [entities, setEntities] = useState<
    Array<{
      id: string;
      name: string;
      description: string;
      features: string[];
      createdAt: string;
      updatedAt: string;
    }>
  >([]);
  const [showCreateEntity, setShowCreateEntity] = useState(false);
  const [newEntity, setNewEntity] = useState({
    name: "",
    description: "",
    features: [] as string[],
  });
  const [newFeature, setNewFeature] = useState("");

  // Feature View state
  const [featureViews, setFeatureViews] = useState<
    Array<{
      id: string;
      name: string;
      description: string;
      entityId: string;
      entityName: string;
      features: string[];
      transformation: string;
      createdAt: string;
      updatedAt: string;
    }>
  >([]);
  const [showCreateView, setShowCreateView] = useState(false);
  const [newView, setNewView] = useState({
    name: "",
    description: "",
    entityId: "",
    features: [] as string[],
    transformation: "",
  });

  // Online Store state
  const [onlineStoreData, setOnlineStoreData] = useState<any>(null);
  const [onlineLoading, setOnlineLoading] = useState(false);
  const [entityIds, setEntityIds] = useState("");
  const [selectedFeatureViewOnline, setSelectedFeatureViewOnline] =
    useState("");

  // Offline Store state
  const [offlineData, setOfflineData] = useState<any>(null);
  const [offlineLoading, setOfflineLoading] = useState(false);
  const [selectedFeatureViewOffline, setSelectedFeatureViewOffline] =
    useState("");

  // Batch/Read options
  const [batchOptions, setBatchOptions] = useState({
    format: "parquet",
    includeMetadata: true,
    overwrite: false,
  });
  const [readOptions, setReadOptions] = useState({
    limit: 1000,
    offset: 0,
    format: "parquet",
    filters: "",
  });
  const [materializeOptions, setMaterializeOptions] = useState({
    outputPath: "",
    format: "parquet",
    compress: true,
    partitionBy: "",
  });

  const fetchEntities = useCallback(async () => {
    // TODO: Implement API call
  }, []);

  const fetchFeatureViews = useCallback(async () => {
    // TODO: Implement API call
  }, []);

  const handleCreateEntity = async () => {
    // TODO: Implement API call
  };

  const handleCreateFeatureView = async () => {
    // TODO: Implement API call
  };

  const handleOnlineRead = async () => {
    setOnlineLoading(true);
    try {
      const ids = entityIds
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean);
      // await featureStore.onlineRead(...)
    } catch (error) {
      console.error("Online read failed:", error);
    } finally {
      setOnlineLoading(false);
    }
  };

  const handleOfflineRead = async () => {
    setOfflineLoading(true);
    try {
      // await featureStore.offlineRead(...)
    } catch (error) {
      console.error("Offline read failed:", error);
    } finally {
      setOfflineLoading(false);
    }
  };

  const handleBatchWrite = async () => {
    // TODO: Implement batch write
  };

  const handleMaterialize = async () => {
    // TODO: Implement materialize
  };

  const removeFeature = (features: string[], index: number) =>
    features.filter((_, i) => i !== index);

  return (
    <div className={classNames("space-y-6", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink">Feature Store</h2>
          <p className="text-muted text-sm mt-1">
            Feast-compatible feature store for ML feature management
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => {}}>
            <span className="flex items-center gap-1.5">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand border-t-transparent" />
              Refresh
            </span>
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="entities" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger
            value="entities"
            className="py-2 flex items-center gap-2"
          >
            <Database className="h-4 w-4" />
            Entities
          </TabsTrigger>
          <TabsTrigger
            value="feature-views"
            className="py-2 flex items-center gap-2"
          >
            <Layers className="h-4 w-4" />
            Feature Views
          </TabsTrigger>
          <TabsTrigger
            value="online-store"
            className="py-2 flex items-center gap-2"
          >
            <Zap className="h-4 w-4" />
            Online Store
          </TabsTrigger>
          <TabsTrigger
            value="offline-store"
            className="py-2 flex items-center gap-2"
          >
            <Database className="h-4 w-4" />
            Offline Store
          </TabsTrigger>
        </TabsList>

        {/* Entities Tab */}
        <TabsContent value="entities" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex-1">
              <Input
                placeholder="Search entities..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="max-w-xs"
              />
            </div>
            <Button onClick={() => setShowCreateEntity(true)}>
              <Plus className="h-4 w-4 mr-1" />
              New Entity
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
              <span className="ml-3 text-muted">Loading entities...</span>
            </div>
          ) : entities.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <div className="h-12 w-12 mx-auto mb-3 opacity-50">
                <Database className="h-12 w-12" />
              </div>
              <h3 className="text-lg font-medium mb-1">No entities found</h3>
              <p className="text-muted text-sm mb-4">
                Create your first entity to get started
              </p>
              <Button onClick={() => setShowCreateEntity(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Create Entity
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {entities.map((entity) => (
                <div
                  key={entity.id}
                  className="border border-line rounded-xl p-4 bg-canvas hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium text-ink truncate">
                          {entity.name}
                        </h3>
                        <Badge tone="neutral" className="text-xs">
                          {entity.features.length} features
                        </Badge>
                      </div>
                      <p className="text-sm text-muted truncate mb-2">
                        {entity.description}
                      </p>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {entity.features.slice(0, 5).map((feature, i) => (
                          <Badge
                            key={i}
                            tone="neutral"
                            className="text-xs"
                          >
                            {feature}
                          </Badge>
                        ))}
                        {entity.features.length > 5 && (
                          <Badge tone="neutral" className="text-xs">
                            +{entity.features.length - 5} more
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-auto shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-brand"
                      >
                        <Eye className="h-4 w-4" />
                        View
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-brand"
                      >
                        <Edit className="h-4 w-4" />
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-red-500"
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Create Entity Modal */}
          {showCreateEntity && (
            <Modal
              open={showCreateEntity}
              onClose={() => setShowCreateEntity(false)}
              title="Create Entity"
              size="lg"
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Name *
                  </label>
                  <Input
                    value={newEntity.name}
                    onChange={(e) =>
                      setNewEntity({ ...newEntity, name: e.target.value })
                    }
                    placeholder="e.g., customer, transaction, product"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Description
                  </label>
                  <Textarea
                    value={newEntity.description}
                    onChange={(e) =>
                      setNewEntity({
                        ...newEntity,
                        description: e.target.value,
                      })
                    }
                    placeholder="Describe this entity..."
                    rows={3}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">
                    Features
                  </label>
                  <div className="flex gap-2 mb-2">
                    <Input
                      value={newFeature}
                      onChange={(e) => setNewFeature(e.target.value)}
                      placeholder="Feature name"
                      className="flex-1"
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        if (newFeature.trim()) {
                          setNewEntity((prev) => ({
                            ...prev,
                            features: [...prev.features, newFeature.trim()],
                          }));
                          setNewFeature("");
                        }
                      }}
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {newEntity.features.map((feature, i) => (
                      <Badge key={i} tone="neutral" className="gap-1">
                        {feature}
                        <button
                          type="button"
                          onClick={() =>
                            setNewEntity((prev) => ({
                              ...prev,
                              features: removeFeature(prev.features, i),
                            }))
                          }
                          className="ml-1 hover:bg-red-100 hover:text-red-600"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-4 border-t border-line">
                  <Button
                    variant="secondary"
                    onClick={() => setShowCreateEntity(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleCreateEntity}
                    disabled={!newEntity.name.trim() || loading}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Create Entity
                  </Button>
                </div>
              </div>
            </Modal>
          )}
        </TabsContent>

        {/* Feature Views Tab */}
        <TabsContent value="feature-views" className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex-1">
              <input
                type="text"
                placeholder="Search feature views..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="max-w-xs"
              />
            </div>
            <Button onClick={() => setShowCreateView(true)}>
              <Plus className="h-4 w-4 mr-1" />
              New Feature View
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand" />
              <span className="ml-3 text-muted">Loading feature views...</span>
            </div>
          ) : featureViews.length === 0 ? (
            <div className="text-center py-12 text-muted">
              <Layers className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <h3 className="text-lg font-medium mb-1">
                No feature views found
              </h3>
              <p className="text-muted text-sm mb-4">
                Create your first feature view to get started
              </p>
              <Button onClick={() => setShowCreateView(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Create Feature View
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {featureViews.map((view) => (
                <div
                  key={view.id}
                  className="border border-line rounded-xl p-4 bg-canvas hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium text-ink truncate">
                          {view.name}
                        </h3>
                        <Badge tone="neutral" className="text-xs">
                          {view.features.length} features
                        </Badge>
                        <Badge tone="neutral" className="text-xs">
                          Entity: {view.entityName}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted truncate mb-2">
                        {view.description}
                      </p>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {view.features.slice(0, 5).map((feature, i) => (
                          <Badge key={i} tone="neutral" className="text-xs">
                            {feature}
                          </Badge>
                        ))}
                        {view.features.length > 5 && (
                          <Badge tone="neutral" className="text-xs">
                            +{view.features.length - 5} more
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-muted text-xs">
                        <span>Entity: {view.entityName}</span>
                        <span>•</span>
                        <span>
                          Created:{" "}
                          {new Date(view.createdAt).toLocaleDateString()}
                        </span>
                        <span>•</span>
                        <span>
                          Updated:{" "}
                          {new Date(view.updatedAt).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-auto shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-brand"
                      >
                        <Eye className="h-4 w-4" />
                        View
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-brand"
                      >
                        <Edit className="h-4 w-4" />
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-red-500"
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Create Feature View Modal */}
          {showCreateView && (
            <Modal
              open={showCreateView}
              onClose={() => setShowCreateView(false)}
              title="Create Feature View"
              size="lg"
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Name *
                  </label>
                  <Input
                    value={newView.name}
                    onChange={(e) =>
                      setNewView({ ...newView, name: e.target.value })
                    }
                    placeholder="e.g., customer_features_v1"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Description
                  </label>
                  <Textarea
                    value={newView.description}
                    onChange={(e) =>
                      setNewView({ ...newView, description: e.target.value })
                    }
                    placeholder="Describe this feature view..."
                    rows={3}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Entity *
                  </label>
                  <select
                    value={newView.entityId}
                    onChange={(e) =>
                      setNewView({ ...newView, entityId: e.target.value })
                    }
                    className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
                  >
                    <option value="">Select entity...</option>
                    {entities.map((entity) => (
                      <option key={entity.id} value={entity.id}>
                        {entity.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-2">
                    Features
                  </label>
                  <div className="flex gap-2 mb-2">
                    <Input
                      value={newFeature}
                      onChange={(e) => setNewFeature(e.target.value)}
                      placeholder="Feature name"
                      className="flex-1"
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        if (newFeature.trim()) {
                          setNewView((prev) => ({
                            ...prev,
                            features: [...prev.features, newFeature.trim()],
                          }));
                          setNewFeature("");
                        }
                      }}
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {newView.features.map((feature, i) => (
                      <Badge key={i} tone="neutral" className="gap-1">
                        {feature}
                        <button
                          type="button"
                          onClick={() =>
                            setNewView((prev) => ({
                              ...prev,
                              features: removeFeature(prev.features, i),
                            }))
                          }
                          className="ml-1 hover:bg-red-100 hover:text-red-600"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Transformation (SQL/Python)
                  </label>
                  <Textarea
                    value={newView.transformation}
                    onChange={(e) =>
                      setNewView({ ...newView, transformation: e.target.value })
                    }
                    placeholder="SELECT ... FROM entity WHERE ..."
                    rows={4}
                    className="font-mono text-sm"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-4 border-t border-line">
                  <Button
                    variant="secondary"
                    onClick={() => setShowCreateView(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleCreateFeatureView}
                    disabled={
                      !newView.name.trim() || !newView.entityId || loading
                    }
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    Create Feature View
                  </Button>
                </div>
              </div>
            </Modal>
          )}
        </TabsContent>

        {/* Online Store Tab */}
        <TabsContent value="online-store" className="space-y-4">
          <Card className="p-4">
            <div className="mb-4">
              <label className="block text-sm font-medium text-ink mb-2">
                Select Feature View
              </label>
              <select
                value={selectedFeatureViewOnline || ""}
                onChange={(e) => setSelectedFeatureViewOnline(e.target.value)}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="">Select a feature view...</option>
                {featureViews.map((view) => (
                  <option key={view.id} value={view.id}>
                    {view.name} ({view.features.length} features)
                  </option>
                ))}
              </select>
            </div>

            {selectedFeatureViewOnline && (
              <div className="p-3 bg-muted/50 rounded-lg mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm">
                    {
                      featureViews.find(
                        (v) => v.id === selectedFeatureViewOnline,
                      )?.name
                    }
                  </span>
                  <Badge tone="neutral" className="text-xs">
                    {featureViews.find(
                      (v) => v.id === selectedFeatureViewOnline,
                    )?.features.length || 0}{" "}
                    features
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-1">
                  {featureViews
                    .find((v) => v.id === selectedFeatureViewOnline)
                    ?.features.slice(0, 5)
                    .map((f, i) => (
                      <Badge key={i} tone="neutral" className="text-xs">
                        {f}
                      </Badge>
                    ))}
                  {(featureViews.find((v) => v.id === selectedFeatureViewOnline)?.features.length ?? 0) > 5 && (
                    <Badge tone="neutral" className="text-xs">
                      +
                      {(featureViews.find((v) => v.id === selectedFeatureViewOnline)?.features.length ?? 0) - 5}{" "}
                      more
                    </Badge>
                  )}
                </div>
              </div>
            )}

            <div className="mb-4">
              <label className="block text-sm font-medium text-ink mb-2">
                Entity IDs (comma-separated)
              </label>
              <textarea
                value={entityIds}
                onChange={(e) => setEntityIds(e.target.value)}
                placeholder="entity_1, entity_2, entity_3..."
                rows={3}
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              />
              <p className="text-xs text-muted mt-1">
                Enter comma-separated entity IDs to fetch features for
              </p>
            </div>

            <div className="flex gap-2">
              <Button
                onClick={handleOnlineRead}
                disabled={
                  onlineLoading ||
                  !selectedFeatureViewOnline ||
                  !entityIds.trim()
                }
                className="flex-1"
              >
                {onlineLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg
                      className="animate-spin h-4 w-4"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                      <path
                        d="M12 2a10 10 0 0 1 10 10"
                        strokeLinecap="round"
                        strokeDasharray="31.4 31.4"
                      />
                    </svg>
                    Reading...
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-2">
                    <Database className="h-4 w-4" />
                    Read from Online Store
                  </span>
                )}
              </Button>
            </div>

            {onlineStoreData && (
              <Card className="mt-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium">Online Store Results</h3>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      navigator.clipboard.writeText(
                        JSON.stringify(onlineStoreData, null, 2),
                      )
                    }
                  >
                    <Download className="h-4 w-4 mr-1" />
                    Copy JSON
                  </Button>
                </div>
                <div className="bg-muted/50 p-4 rounded-lg max-h-96 overflow-auto font-mono text-sm">
                  <pre>{JSON.stringify(onlineStoreData, null, 2)}</pre>
                </div>
              </Card>
            )}
          </Card>
        </TabsContent>

        {/* Offline Store Tab */}
        <TabsContent value="offline-store" className="space-y-4">
          <Card className="p-4">
            <div className="mb-4">
              <label className="block text-sm font-medium text-ink mb-2">
                Select Feature View
              </label>
              <select
                value={selectedFeatureViewOffline || ""}
                onChange={(e) => setSelectedFeatureViewOffline(e.target.value)}
                className="w-full max-w-md px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              >
                <option value="">Select a feature view...</option>
                {featureViews.map((view) => (
                  <option key={view.id} value={view.id}>
                    {view.name} ({view.features.length} features)
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <h3 className="font-medium mb-4">Batch Write Options</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Format
                    </label>
                    <select
                      value={batchOptions.format}
                      onChange={(e) =>
                        setBatchOptions((prev) => ({
                          ...prev,
                          format: e.target.value,
                        }))
                      }
                      className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
                    >
                      <option value="parquet">Parquet</option>
                      <option value="csv">CSV</option>
                      <option value="json">JSON</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="includeMetadata"
                      checked={batchOptions.includeMetadata}
                      onChange={(e) =>
                        setBatchOptions((prev) => ({
                          ...prev,
                          includeMetadata: e.target.checked,
                        }))
                      }
                      className="w-4 h-4 rounded border-line text-brand focus:ring-brand"
                    />
                    <label
                      htmlFor="includeMetadata"
                      className="text-sm text-ink"
                    >
                      Include Metadata
                    </label>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="overwrite"
                      checked={batchOptions.overwrite}
                      onChange={(e) =>
                        setBatchOptions((prev) => ({
                          ...prev,
                          overwrite: e.target.checked,
                        }))
                      }
                      className="w-4 h-4 rounded border-line text-brand focus:ring-brand"
                    />
                    <label htmlFor="overwrite" className="text-sm text-ink">
                      Overwrite Existing
                    </label>
                  </div>
                </div>
                <Button
                  onClick={handleBatchWrite}
                  disabled={offlineLoading || !selectedFeatureViewOffline}
                  className="w-full mt-4"
                >
                  {offlineLoading ? "Writing..." : "Write Batch"}
                </Button>
              </Card>

              <Card>
                <h3 className="font-medium mb-4">Read Data</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Limit
                    </label>
                    <Input
                      type="number"
                      value={readOptions.limit}
                      onChange={(e) =>
                        setReadOptions((prev) => ({
                          ...prev,
                          limit: parseInt(e.target.value) || 0,
                        }))
                      }
                      min={1}
                      max={100000}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Offset
                    </label>
                    <Input
                      type="number"
                      value={readOptions.offset}
                      onChange={(e) =>
                        setReadOptions((prev) => ({
                          ...prev,
                          offset: parseInt(e.target.value) || 0,
                        }))
                      }
                      min={0}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Format
                    </label>
                    <select
                      value={readOptions.format}
                      onChange={(e) =>
                        setReadOptions((prev) => ({
                          ...prev,
                          format: e.target.value,
                        }))
                      }
                      className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
                    >
                      <option value="parquet">Parquet</option>
                      <option value="csv">CSV</option>
                      <option value="json">JSON</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Filters (JSON)
                    </label>
                    <Input
                      value={readOptions.filters}
                      onChange={(e) =>
                        setReadOptions((prev) => ({
                          ...prev,
                          filters: e.target.value,
                        }))
                      }
                      placeholder='{"feature_1": {">": 0.5}}'
                      className="w-full"
                    />
                  </div>
                </div>

                <Button
                  onClick={handleOfflineRead}
                  disabled={offlineLoading || !selectedFeatureViewOffline}
                  className="w-full"
                >
                  {offlineLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg
                        className="animate-spin h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                        <path
                          d="M12 2a10 10 0 0 1 10 10"
                          strokeLinecap="round"
                          strokeDasharray="31.4 31.4"
                        />
                      </svg>
                      Reading...
                    </span>
                  ) : (
                    <span className="flex items-center justify-center gap-2">
                      <Download className="h-4 w-4" />
                      Read Data
                    </span>
                  )}
                </Button>

                {offlineData && (
                  <Card className="mt-4">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-medium">Offline Store Results</h3>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          navigator.clipboard.writeText(
                            JSON.stringify(offlineData, null, 2),
                          )
                        }
                      >
                        <Download className="h-4 w-4 mr-1" />
                        Copy JSON
                      </Button>
                    </div>
                    <div className="bg-muted/50 p-4 rounded-lg max-h-96 overflow-auto font-mono text-sm">
                      <pre>{JSON.stringify(offlineData, null, 2)}</pre>
                    </div>
                  </Card>
                )}
              </Card>
            </div>

            {/* Materialize Section */}
            <Card className="mt-4 p-4">
              <h3 className="font-medium mb-4">Materialize Feature View</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Output Path
                  </label>
                  <Input
                    value={materializeOptions.outputPath}
                    onChange={(e) =>
                      setMaterializeOptions((prev) => ({
                        ...prev,
                        outputPath: e.target.value,
                      }))
                    }
                    placeholder="s3://bucket/path/ or /local/path/"
                    className="w-full"
                  />
                  <p className="text-xs text-muted mt-1">
                    S3 path (s3://bucket/path/) or local file path
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1">
                      Format
                    </label>
                    <select
                      value={materializeOptions.format}
                      onChange={(e) =>
                        setMaterializeOptions((prev) => ({
                          ...prev,
                          format: e.target.value,
                        }))
                      }
                      className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
                    >
                      <option value="parquet">Parquet</option>
                      <option value="csv">CSV</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="compress"
                      checked={materializeOptions.compress}
                      onChange={(e) =>
                        setMaterializeOptions((prev) => ({
                          ...prev,
                          compress: e.target.checked,
                        }))
                      }
                      className="w-4 h-4 rounded border-line text-brand focus:ring-brand"
                    />
                    <label htmlFor="compress" className="text-sm text-ink">
                      Compress Output
                    </label>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-ink mb-1">
                    Partition By (Optional)
                  </label>
                  <Input
                    value={materializeOptions.partitionBy}
                    onChange={(e) =>
                      setMaterializeOptions((prev) => ({
                        ...prev,
                        partitionBy: e.target.value,
                      }))
                    }
                    placeholder="feature_name or date_column"
                    className="w-full"
                  />
                  <p className="text-xs text-muted mt-1">
                    Column name to partition output by
                  </p>
                </div>

                <Button
                  onClick={handleMaterialize}
                  disabled={offlineLoading || !selectedFeatureViewOffline}
                  className="w-full"
                >
                  {offlineLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg
                        className="animate-spin h-4 w-4"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                        <path
                          d="M12 2a10 10 0 0 1 10 10"
                          strokeLinecap="round"
                          strokeDasharray="31.4 31.4"
                        />
                      </svg>
                      Materializing...
                    </span>
                  ) : (
                    <span className="flex items-center justify-center gap-2">
                      <Server className="h-4 w-4" />
                      Materialize to Offline Store
                    </span>
                  )}
                </Button>
              </div>
            </Card>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
