"use client";

/**
 * Feature Store Explorer
 * View entities, feature views, online/offline data management
 */

import { useState, useEffect, useCallback } from "react";
import { useFeatureStore, useOnlineFeatures } from "@/hooks/useMLPlatform";
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
} from "lucide-react";
import { classNames } from "@/lib/utils";
import { EntityExplorer } from "./EntityExplorer";
import { FeatureViewExplorer } from "./FeatureViewExplorer";
import { OnlineStorePanel } from "./OnlineStorePanel";
import { OfflineTrainingPanel } from "./OfflineTrainingPanel";

interface FeatureStoreExplorerProps {
  organizationId: string;
  className?: string;
}

export function FeatureStoreExplorer({
  organizationId,
  className,
}: FeatureStoreExplorerProps) {
  const {
    entities,
    featureViews,
    loading,
    error,
    listEntities,
    listFeatureViews,
    createEntity,
    createFeatureView,
    onlineWrite,
    onlineRead,
    getOnlineFeatures,
    batchWrite,
    getTrainingData,
    materialize,
  } = useFeatureStore();

  const [activeTab, setActiveTab] = useState<
    "entities" | "views" | "online" | "offline"
  >("entities");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateEntity, setShowCreateEntity] = useState(false);
  const [showCreateView, setShowCreateView] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedFeatureView, setSelectedFeatureView] = useState<string | null>(
    null,
  );
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Entity form state
  const [newEntity, setNewEntity] = useState({
    name: "",
    join_keys: [] as string[],
    description: "",
    value_type: "string",
    tags: {} as Record<string, string>,
  });

  // Feature view form state
  const [newView, setNewView] = useState({
    name: "",
    entities: [] as string[],
    features: [] as { name: string; dtype: string; description: string }[],
    ttl_days: 1,
    batch_source: "",
    stream_source: "",
    online: true,
    description: "",
    tags: {} as Record<string, string>,
  });

  const fetchData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await Promise.all([listEntities(), listFeatureViews()]);
    } finally {
      setIsRefreshing(false);
    }
  }, [listEntities, listFeatureViews]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Entity form handlers
  const handleCreateEntity = async (e: React.FormEvent) => {
    e.preventDefault();
    await createEntity(newEntity);
    setShowCreateEntity(false);
    setNewEntity({
      name: "",
      join_keys: [],
      description: "",
      value_type: "string",
      tags: {},
    });
    fetchData();
  };

  // Feature view form handlers
  const handleCreateFeatureView = async (e: React.FormEvent) => {
    e.preventDefault();
    const features = newView.features.map((f) => ({
      name: f.name,
      dtype: f.dtype,
      description: f.description,
      tags: {},
    }));

    await createFeatureView({
      ...newView,
      features,
      ttl: { days: newView.ttl_days } as any,
    });
    setShowCreateView(false);
    setNewView({
      name: "",
      entities: [],
      features: [],
      ttl_days: 1,
      batch_source: "",
      stream_source: "",
      online: true,
      description: "",
      tags: {},
    });
    fetchData();
  };

  // Modal functions (defined inside component to access state)
  function createEntityModal() {
    return (
      <Modal
        open={showCreateEntity}
        onClose={() => setShowCreateEntity(false)}
        title="Create New Entity"
      >
        <form onSubmit={handleCreateEntity} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Entity Name *
            </label>
            <Input
              value={newEntity.name}
              onChange={(e) =>
                setNewEntity({ ...newEntity, name: e.target.value })
              }
              placeholder="e.g., customer, transaction, product"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Join Keys (comma-separated) *
            </label>
            <Input
              value={newEntity.join_keys.join(", ")}
              onChange={(e) =>
                setNewEntity({
                  ...newEntity,
                  join_keys: e.target.value
                    .split(",")
                    .map((k) => k.trim())
                    .filter(Boolean),
                })
              }
              placeholder="e.g., customer_id, organization_id"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Value Type
            </label>
            <Select
              value={newEntity.value_type}
              onValueChange={(v) =>
                setNewEntity({ ...newEntity, value_type: v })
              }
              options={[
                { value: "string", label: "String" },
                { value: "int32", label: "Int32" },
                { value: "int64", label: "Int64" },
                { value: "float32", label: "Float32" },
                { value: "float64", label: "Float64" },
                { value: "bool", label: "Boolean" },
                { value: "bytes", label: "Bytes" },
                { value: "unix_timestamp", label: "Unix Timestamp" },
              ]}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Description
            </label>
            <InputTextarea
              value={newEntity.description}
              onChange={(e) =>
                setNewEntity({ ...newEntity, description: e.target.value })
              }
              placeholder="Description of this entity..."
              rows={2}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Tags (JSON)
            </label>
            <InputTextarea
              value={JSON.stringify(newEntity.tags, null, 2)}
              onChange={(e) => {
                try {
                  setNewEntity({
                    ...newEntity,
                    tags: JSON.parse(e.target.value),
                  });
                } catch {}
              }}
              placeholder='{"domain": "customer", "team": "ml-team"}'
              rows={2}
              fontMonospace
            />
          </div>
          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowCreateEntity(false)}
            >
              Cancel
            </Button>
            <Button type="submit">Create Entity</Button>
          </div>
        </form>
      </Modal>
    );
  }

  function createFeatureViewModal() {
    return (
      <Modal
        open={showCreateView}
        onClose={() => setShowCreateView(false)}
        title="Create Feature View"
        size="lg"
      >
        <form
          onSubmit={handleCreateFeatureView}
          className="space-y-4 max-h-[80vh] overflow-y-auto"
        >
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                Feature View Name *
              </label>
              <Input
                value={newView.name}
                onChange={(e) =>
                  setNewView({ ...newView, name: e.target.value })
                }
                placeholder="e.g., customer_features"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1">
                TTL (days)
              </label>
              <Input
                type="number"
                value={newView.ttl_days}
                onChange={(e) =>
                  setNewView({ ...newView, ttl_days: parseInt(e.target.value) })
                }
                min={1}
                max={365}
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Entities *
            </label>
            <div className="space-y-2">
              {newView.entities.map((entity, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Select
                    value={entity}
                    onValueChange={(v) => {
                      const arr = [...newView.entities];
                      arr[i] = v;
                      setNewView({ ...newView, entities: arr });
                    }}
                    options={[
                      { value: "", label: "Select entity" },
                      ...entities.map((e) => ({
                        value: e.name,
                        label: e.name,
                      })),
                    ]}
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setNewView({
                        ...newView,
                        entities: newView.entities.filter(
                          (_, idx) => idx !== i,
                        ),
                      })
                    }
                    className="p-1 text-red-600 hover:text-red-800"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setNewView({
                    ...newView,
                    entities: [...newView.entities, ""],
                  })
                }
                className="text-sm text-brand hover:underline"
              >
                + Add Entity
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Features
            </label>
            <div className="space-y-2">
              {newView.features.map((feature, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    placeholder="Feature name"
                    value={feature.name}
                    onChange={(e) => {
                      const arr = [...newView.features];
                      arr[i] = { ...arr[i], name: e.target.value };
                      setNewView({ ...newView, features: arr });
                    }}
                    className="flex-1"
                  />
                  <Select
                    value={feature.dtype}
                    onValueChange={(v) => {
                      const arr = [...newView.features];
                      arr[i] = { ...arr[i], dtype: v };
                      setNewView({ ...newView, features: arr });
                    }}
                    options={[
                      { value: "string", label: "String" },
                      { value: "int32", label: "Int32" },
                      { value: "int64", label: "Int64" },
                      { value: "float32", label: "Float32" },
                      { value: "float64", label: "Float64" },
                      { value: "bool", label: "Boolean" },
                    ]}
                    className="w-36"
                  />
                  <Input
                    placeholder="Description"
                    value={feature.description}
                    onChange={(e) => {
                      const arr = [...newView.features];
                      arr[i] = { ...arr[i], description: e.target.value };
                      setNewView({ ...newView, features: arr });
                    }}
                    className="flex-1"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setNewView({
                        ...newView,
                        features: newView.features.filter(
                          (_, idx) => idx !== i,
                        ),
                      })
                    }
                    className="p-1 text-red-600 hover:text-red-800"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setNewView({
                    ...newView,
                    features: [
                      ...newView.features,
                      { name: "", dtype: "string", description: "" },
                    ],
                  })
                }
                className="text-sm text-brand hover:underline"
              >
                + Add Feature
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              TTL (days)
            </label>
            <Input
              type="number"
              value={newView.ttl_days}
              onChange={(e) =>
                setNewView({ ...newView, ttl_days: parseInt(e.target.value) })
              }
              min={1}
              max={365}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Batch Source (table/query)
            </label>
            <Input
              value={newView.batch_source}
              onChange={(e) =>
                setNewView({ ...newView, batch_source: e.target.value })
              }
              placeholder="e.g., customer_features_table"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Stream Source (Kafka topic)
            </label>
            <Input
              value={newView.stream_source}
              onChange={(e) =>
                setNewView({ ...newView, stream_source: e.target.value })
              }
              placeholder="e.g., customer_events_stream"
            />
          </div>
          <div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={newView.online}
                onChange={(e) =>
                  setNewView({ ...newView, online: e.target.checked })
                }
                className="rounded border-line"
              />
              <span className="text-sm text-ink">Enable Online Store</span>
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Description
            </label>
            <InputTextarea
              value={newView.description}
              onChange={(e) =>
                setNewView({ ...newView, description: e.target.value })
              }
              placeholder="Description of this feature view..."
              rows={2}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink mb-1">
              Tags (JSON)
            </label>
            <InputTextarea
              value={JSON.stringify(newView.tags, null, 2)}
              onChange={(e) => {
                try {
                  setNewView({ ...newView, tags: JSON.parse(e.target.value) });
                } catch {}
              }}
              placeholder='{"domain": "customer", "team": "ml-team"}'
              rows={2}
              fontMonospace
            />
          </div>
          <div className="flex justify-end gap-2 pt-4 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setShowCreateView(false)}
            >
              Cancel
            </Button>
            <Button type="submit">Create Feature View</Button>
          </div>
        </form>
      </Modal>
    );
  }

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
              <Database className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">
                Feature Store Explorer
              </h2>
              <p className="text-sm text-muted">
                Manage entities, feature views & online/offline data
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-2 bg-canvas border border-line rounded-lg px-3 py-1">
              <Search className="h-4 w-4 text-muted" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent border-none text-sm text-ink focus:outline-none w-64"
              />
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

            <button
              onClick={() => setShowCreateEntity(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-brand text-white hover:bg-brand-strong transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New Entity</span>
            </button>

            <button
              onClick={() => setShowCreateView(true)}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors flex items-center gap-1"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New Feature View</span>
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
        <TabsList className="grid w-full grid-cols-4 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger
            value="entities"
            className="py-2 flex items-center gap-2"
          >
            <Layers className="h-4 w-4" />
            Entities
          </TabsTrigger>
          <TabsTrigger value="views" className="py-2 flex items-center gap-2">
            <Layers className="h-4 w-4" />
            Feature Views
          </TabsTrigger>
          <TabsTrigger value="online" className="py-2 flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Online Store
          </TabsTrigger>
          <TabsTrigger value="offline" className="py-2 flex items-center gap-2">
            <Database className="h-4 w-4" />
            Offline / Training
          </TabsTrigger>
        </TabsList>

        {/* Entities Tab */}
        <TabsContent value="entities" className="flex-1 p-4 overflow-auto">
          <EntityExplorer
            entities={entities}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            loading={loading}
            onCreate={setShowCreateEntity}
            onRefresh={fetchData}
          />
        </TabsContent>

        {/* Feature Views Tab */}
        <TabsContent value="views" className="flex-1 p-4 overflow-auto">
          <FeatureViewExplorer
            featureViews={featureViews}
            entities={entities}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            loading={loading}
            onCreate={setShowCreateView}
            onRefresh={fetchData}
          />
        </TabsContent>

        {/* Online Store Tab */}
        <TabsContent value="online" className="flex-1 p-4 overflow-auto">
          <OnlineStorePanel
            featureViews={featureViews}
            selectedFeatureView={selectedFeatureView}
            setSelectedFeatureView={setSelectedFeatureView}
            onRead={onlineRead}
            onGetFeatures={getOnlineFeatures}
          />
        </TabsContent>

        {/* Offline/Training Tab */}
        <TabsContent value="offline" className="flex-1 p-4 overflow-auto">
          <OfflineTrainingPanel
            featureViews={featureViews}
            onBatchWrite={batchWrite}
            onGetTrainingData={getTrainingData}
            onMaterialize={materialize}
          />
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {createEntityModal()}
      {createFeatureViewModal()}
    </div>
  );
}
required;
