"use client";

/**
 * ML Platform Hooks
 * Type-safe React hooks for consuming all ML Platform APIs
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "@/lib/api";

// ==================== Types ====================

// Feature Store Types
export interface Entity {
  name: string;
  join_keys: string[];
  description: string;
  value_type: string;
  tags: Record<string, string>;
}

export interface Feature {
  name: string;
  dtype: string;
  description: string;
  tags: Record<string, string>;
}

export interface FeatureView {
  name: string;
  entities: string[];
  features: Feature[];
  ttl_days: number;
  batch_source?: string;
  stream_source?: string;
  online: boolean;
  description: string;
  tags: Record<string, string>;
}

export interface OnlineFeatureRequest {
  feature_view: string;
  entity_id: string;
  features: Record<string, any>;
  event_timestamp?: string;
}

export interface OnlineReadRequest {
  feature_view: string;
  entity_ids: string[];
}

// Model Registry Types
export interface ModelStage {
  stage: "none" | "staging" | "production" | "archived";
}

export interface ModelArtifact {
  path: string;
  size_bytes: number;
  checksum: string;
  artifact_type: string;
  metadata: Record<string, any>;
}

export interface ModelSignature {
  inputs: Array<{ name: string; type: string; shape: number[] }>;
  outputs: Array<{ name: string; type: string; shape: number[] }>;
  params: Record<string, any>;
}

export interface ModelVersion {
  name: string;
  version: number;
  stage: string;
  status: string;
  run_id: string;
  experiment_id: string;
  source: string;
  artifacts: ModelArtifact[];
  signature?: ModelSignature;
  description: string;
  tags: Record<string, string>;
  params: Record<string, any>;
  metrics: Record<string, number>;
  created_at: string;
  updated_at: string;
  created_by: string;
  parent_version?: number;
  dataset_version: string;
}

export interface RegisteredModel {
  name: string;
  description: string;
  tags: Record<string, string>;
  versions: ModelVersion[];
  latest_version: number;
  production_version?: number;
  staging_version?: number;
  created_at: string;
  updated_at: string;
}

export interface ModelDeployment {
  id: string;
  model_name: string;
  model_version: number;
  endpoint_name: string;
  endpoint_url: string;
  status: string;
  replicas: number;
  resources: Record<string, any>;
  config: Record<string, any>;
  created_at: string;
  updated_at: string;
  health_check_url: string;
  metrics: Record<string, any>;
}

// Inference Types
export interface InferenceBackend {
  backend: "triton" | "vllm" | "tgi" | "local";
  endpoint: string;
}

export interface InferenceRequest {
  model_name: string;
  inputs: Record<string, any>;
  version?: number;
  parameters?: Record<string, any>;
  stream?: boolean;
  priority?: number;
  timeout?: number;
}

export interface InferenceResponse {
  id: string;
  request_id: string;
  model_name: string;
  model_version: number;
  outputs: Record<string, any>;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  latency_ms: number;
  tokens_used?: number;
  error?: string;
}

// Causal Inference Types
export interface CausalGraph {
  name: string;
  nodes: string[];
  edges: string[][];
  latent_variables: string[];
}

export interface TreatmentEffect {
  ate: number;
  ate_ci: [number, number];
  ate_pvalue: number;
  cate?: Record<string, number>;
  cate_ci?: Record<string, [number, number]>;
  ite?: number[];
  method: string;
  estimator: string;
  assumptions: Record<string, any>;
  diagnostics: Record<string, any>;
}

export interface CounterfactualResult {
  factual_outcome: number;
  counterfactual_outcome: number;
  effect: number;
  confidence_interval: [number, number];
  probability_necessary: number;
  probability_sufficient: number;
  explanation: string;
}

export interface MediationAnalysis {
  total_effect: number;
  direct_effect: number;
  indirect_effect: number;
  proportion_mediated: number;
  mediator_effects: Record<string, number>;
  confidence_intervals: Record<string, [number, number]>;
}

// Forecasting Types
export type ForecastMethod =
  | "prophet"
  | "neuralprophet"
  | "arima"
  | "sarima"
  | "exponential_smoothing"
  | "linear_regression"
  | "random_forest"
  | "gradient_boosting"
  | "ensemble";

export interface TimeSeriesDataPoint {
  timestamp: string;
  value: number;
  metadata?: Record<string, any>;
}

export interface RegisterForecastDataRequest {
  name: string;
  data: TimeSeriesDataPoint[];
  date_col?: string;
  value_col?: string;
}

export interface ForecastRequest {
  data_name: string;
  horizon: number;
  method: ForecastMethod;
  frequency?: string;
  confidence_level?: number;
  params?: Record<string, any>;
  include_history?: boolean;
}

export interface ForecastResult {
  timestamps: string[];
  forecast: number[];
  lower_bound?: number[];
  upper_bound?: number[];
  confidence_level: number;
  method: string;
  model_params: Record<string, any>;
  metrics: Record<string, number>;
}

// Text-to-SQL Types
export interface TextToSQLRequest {
  question: string;
  context?: string;
  schema?: string;
  dialect:
    | "postgresql"
    | "mysql"
    | "snowflake"
    | "bigquery"
    | "redshift"
    | "databricks"
    | "spark"
    | "sqlite"
    | "tsql";
  max_tokens?: number;
  temperature?: number;
  include_explanation?: boolean;
  include_lineage?: boolean;
}

export interface TextToSQLResponse {
  sql: string;
  dialect: string;
  explanation: string;
  confidence: number;
  tables_used: string[];
  columns_used: string[];
  lineage: Record<string, any>;
  warnings: string[];
}

export interface ValidateSQLRequest {
  sql: string;
  dialect: string;
}

export interface ValidateSQLResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
  tables_referenced: string[];
  columns_referenced: string[];
  complexity_score: number;
}

// Proactive Insights Types
export type InsightType =
  | "anomaly"
  | "trend_change"
  | "seasonality_shift"
  | "correlation_break"
  | "threshold_breach"
  | "forecast_deviation"
  | "pattern_discovery"
  | "causal_hypothesis";

export type InsightSeverity = "info" | "warning" | "critical";

export interface DataPoint {
  timestamp: string;
  value: number;
  metadata?: Record<string, any>;
}

export interface TimeSeriesMetric {
  name: string;
  data: DataPoint[];
  frequency: string;
  thresholds: Record<string, number>;
  baseline_stats: Record<string, number>;
}

export interface Anomaly {
  id: string;
  metric_name: string;
  timestamp: string;
  value: number;
  expected_range: [number, number];
  severity: InsightSeverity;
  method: string;
  score: number;
  explanation: string;
  context: Record<string, any>;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
}

export interface TrendChange {
  id: string;
  metric_name: string;
  change_point: string;
  direction: string;
  magnitude: number;
  confidence: number;
  before_trend: number;
  after_trend: number;
  method: string;
  explanation: string;
}

export interface Insight {
  id: string;
  type: InsightType;
  title: string;
  description: string;
  severity: InsightSeverity;
  metrics_affected: string[];
  detected_at: string;
  data_points: Record<string, any>[];
  suggested_actions: string[];
  related_anomalies: string[];
  related_trend_changes: string[];
  confidence: number;
  metadata: Record<string, any>;
  acknowledged: boolean;
}

export interface Alert {
  id: string;
  insight_id: string;
  channel: string;
  recipient: string;
  subject: string;
  message: string;
  severity: InsightSeverity;
  sent: boolean;
  sent_at?: string;
  error?: string;
}

export interface AlertRule {
  id: string;
  name: string;
  metric_patterns: string[];
  severity_threshold: InsightSeverity;
  channels: string[];
  recipients: Record<string, string[]>;
  cooldown_minutes: number;
  enabled: boolean;
}

// ==================== Generic API Hook ====================

function useApi<T>(
  apiCall: () => Promise<T>,
  dependencies: any[] = [],
  options: { immediate?: boolean; onError?: (error: Error) => void } = {},
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const execute = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiCall();
      setData(result);
      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      options.onError?.(error);
      throw error;
    } finally {
      setLoading(false);
    }
  }, dependencies);

  useEffect(() => {
    if (options.immediate !== false) {
      execute();
    }
  }, [execute, options.immediate]);

  return { data, loading, error, execute, refetch: execute };
}

// ==================== Feature Store Hooks ====================

export function useFeatureStore() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [featureViews, setFeatureViews] = useState<FeatureView[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const listEntities = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api("/ml/feature-store/entities");
      setEntities(response);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  const listFeatureViews = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api("/ml/feature-store/feature-views");
      setFeatureViews(response);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  const createEntity = useCallback(async (entity: Omit<Entity, "">) => {
    const response = await api("/ml/feature-store/entities", {
      method: "POST",
      body: entity,
    });
    setEntities((prev) => [...prev, response]);
    return response;
  }, []);

  const createFeatureView = useCallback(async (fv: Omit<FeatureView, "">) => {
    const response = await api("/ml/feature-store/feature-views", {
      method: "POST",
      body: fv,
    });
    setFeatureViews((prev) => [...prev, response]);
    return response;
  }, []);

  const onlineWrite = useCallback(async (request: OnlineFeatureRequest) => {
    return api("/ml/feature-store/online/write", {
      method: "POST",
      body: request,
    });
  }, []);

  const onlineRead = useCallback(async (request: OnlineReadRequest) => {
    return api("/ml/feature-store/online/read", {
      method: "POST",
      body: request,
    });
  }, []);

  const getOnlineFeatures = useCallback(
    async (entityId: string, featureViews?: string[]) => {
      return api("/ml/feature-store/online/features", {
        method: "POST",
        body: { entity_id: entityId, feature_views: featureViews },
      });
    },
    [],
  );

  const batchWrite = useCallback(async (featureView: string, data: any[]) => {
    return api("/ml/feature-store/offline/write", {
      method: "POST",
      body: { feature_view: featureView, data },
    });
  }, []);

  const getTrainingData = useCallback(
    async (
      entityIds: string[],
      featureViews: string[],
      startTime: string,
      endTime: string,
    ) => {
      return api("/ml/feature-store/offline/training-data", {
        method: "POST",
        body: {
          entity_ids: entityIds,
          feature_views: featureViews,
          start_time: startTime,
          end_time: endTime,
        },
      });
    },
    [],
  );

  const materialize = useCallback(
    async (
      featureView: string,
      startTime: string,
      endTime: string,
      batchSize = 1000,
    ) => {
      return api("/ml/feature-store/materialize", {
        method: "POST",
        body: {
          feature_view: featureView,
          start_time: startTime,
          end_time: endTime,
          batch_size: batchSize,
        },
      });
    },
    [],
  );

  useEffect(() => {
    listEntities();
    listFeatureViews();
  }, [listEntities, listFeatureViews]);

  return {
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
  };
}

export function useOnlineFeatures(entityId: string, featureViews?: string[]) {
  const [features, setFeatures] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetch = useCallback(async () => {
    if (!entityId) return;
    setLoading(true);
    try {
      const response = await api("/ml/feature-store/online/features", {
        method: "POST",
        body: { entity_id: entityId, feature_views: featureViews },
      });
      setFeatures(response);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [entityId, featureViews]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { features, loading, error, refetch: fetch };
}

// ==================== Model Registry Hooks ====================

export function useModelRegistry() {
  const [models, setModels] = useState<RegisteredModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const listModels = useCallback(async (tags?: Record<string, string>) => {
    setLoading(true);
    try {
      const query = tags
        ? `?tags=${Object.entries(tags)
            .map(([k, v]) => `${k}=${v}`)
            .join(",")}`
        : "";
      const response = await api(`/ml/models${query}`);
      setModels(response.models || []);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  const getModel = useCallback(async (name: string) => {
    return api(`/ml/models/${name}`);
  }, []);

  const createModel = useCallback(
    async (request: {
      name: string;
      description: string;
      tags: Record<string, string>;
    }) => {
      const response = await api("/ml/models", {
        method: "POST",
        body: request,
      });
      setModels((prev) => [...prev, response]);
      return response;
    },
    [],
  );

  const registerVersion = useCallback(async (name: string, request: any) => {
    return api(`/ml/models/${name}/versions`, {
      method: "POST",
      body: request,
    });
  }, []);

  const transitionStage = useCallback(
    async (name: string, version: number, stage: string) => {
      return api(`/ml/models/${name}/versions/${version}/stage`, {
        method: "POST",
        body: { stage },
      });
    },
    [],
  );

  const addArtifacts = useCallback(
    async (name: string, version: number, artifacts: any[]) => {
      return api(`/ml/models/${name}/versions/${version}/artifacts`, {
        method: "POST",
        body: artifacts,
      });
    },
    [],
  );

  const createDeployment = useCallback(
    async (request: {
      model_name: string;
      model_version: number;
      endpoint_name: string;
      endpoint_url: string;
      replicas?: number;
      resources?: Record<string, any>;
      config?: Record<string, any>;
      health_check_url?: string;
    }) => {
      return api("/ml/deployments", { method: "POST", body: request });
    },
    [],
  );

  const listDeployments = useCallback(async (modelName?: string) => {
    const query = modelName ? `?model_name=${modelName}` : "";
    return api(`/ml/deployments${query}`);
  }, []);

  return {
    models,
    loading,
    error,
    listModels,
    getModel,
    createModel,
    registerVersion,
    transitionStage,
    addArtifacts,
    createDeployment,
    listDeployments,
  };
}

export function useModelVersions(modelName: string) {
  const [versions, setVersions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetch = useCallback(async () => {
    if (!modelName) return;
    setLoading(true);
    try {
      const model = await api(`/ml/models/${modelName}`);
      setVersions(model.versions || []);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, [modelName]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { versions, loading, error, refetch: fetch };
}

// ==================== Inference Hooks ====================

export function useInference() {
  const [models, setModels] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadModel = useCallback(
    async (request: {
      model_name: string;
      version?: number;
      backend?: "triton" | "vllm" | "tgi" | "local";
      endpoint?: string;
    }) => {
      setLoading(true);
      try {
        const response = await api("/ml/inference/load", {
          method: "POST",
          body: request,
        });
        setModels((prev) => [
          ...prev.filter((m) => m.id !== response.instance.id),
          response.instance,
        ]);
        return response;
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const unloadModel = useCallback(
    async (modelName: string, version: number) => {
      await api("/ml/inference/unload", {
        method: "POST",
        body: { model_name: modelName, version },
      });
      setModels((prev) =>
        prev.filter((m) => m.id !== `${modelName}:${version}`),
      );
    },
    [],
  );

  const predict = useCallback(
    async (request: {
      model_name: string;
      inputs: Record<string, any>;
      version?: number;
      parameters?: Record<string, any>;
      stream?: boolean;
      priority?: number;
      timeout?: number;
    }) => {
      return api("/ml/inference/predict", { method: "POST", body: request });
    },
    [],
  );

  const streamPredict = useCallback(
    async (request: {
      model_name: string;
      inputs: Record<string, any>;
      version?: number;
      parameters?: Record<string, any>;
      timeout?: number;
    }) => {
      const response = await fetch("/api/v1/ml/inference/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      return response;
    },
    [],
  );

  const batchPredict = useCallback(
    async (request: {
      model_name: string;
      requests: any[];
      version?: number;
    }) => {
      return api("/ml/inference/batch", { method: "POST", body: request });
    },
    [],
  );

  const healthCheck = useCallback(async (modelName?: string) => {
    return api(
      `/ml/inference/health${modelName ? `?model_name=${modelName}` : ""}`,
    );
  }, []);

  const listModels = useCallback(async () => {
    const response = await api("/ml/inference/models");
    setModels(response.models || []);
    return response.models || [];
  }, []);

  useEffect(() => {
    listModels();
  }, [listModels]);

  return {
    models,
    loading,
    error,
    loadModel,
    unloadModel,
    predict,
    streamPredict,
    batchPredict,
    healthCheck,
    listModels,
  };
}

// ==================== Causal Inference Hooks ====================

export function useCausalInference() {
  const [graphs, setGraphs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const createGraph = useCallback(
    async (request: {
      name: string;
      nodes: string[];
      edges: string[][];
      latent_variables?: string[];
    }) => {
      const response = await api("/ml/causal/graph", {
        method: "POST",
        body: request,
      });
      setGraphs((prev) => [...prev, response.graph]);
      return response;
    },
    [],
  );

  const listGraphs = useCallback(async () => {
    const response = await api("/ml/causal/graphs");
    setGraphs(response.graphs || []);
    return response;
  }, []);

  const getGraph = useCallback(async (name: string) => {
    return api(`/ml/causal/graphs/${name}`);
  }, []);

  const validateGraph = useCallback(async (name: string) => {
    return api(`/ml/causal/graphs/${name}/validate`);
  }, []);

  const visualizeGraph = useCallback(async (name: string) => {
    return api(`/ml/causal/graphs/${name}/visualize`);
  }, []);

  const registerData = useCallback(async (name: string, data: any[]) => {
    return api("/ml/causal/data", { method: "POST", body: { name, data } });
  }, []);

  const listData = useCallback(async () => {
    return api("/ml/causal/data");
  }, []);

  const estimateEffect = useCallback(
    async (request: {
      data_name: string;
      treatment: string;
      outcome: string;
      confounders?: string[];
      effect_modifiers?: string[];
      method?: string;
      estimator?: string;
      graph_name?: string;
    }) => {
      return api("/ml/causal/estimate", { method: "POST", body: request });
    },
    [],
  );

  const estimateCounterfactual = useCallback(
    async (request: {
      data_name: string;
      treatment: string;
      outcome: string;
      confounders: string[];
      factual_values: Record<string, any>;
      counterfactual_values: Record<string, any>;
    }) => {
      return api("/ml/causal/counterfactual", {
        method: "POST",
        body: request,
      });
    },
    [],
  );

  const mediationAnalysis = useCallback(
    async (request: {
      data_name: string;
      treatment: string;
      outcome: string;
      mediators: string[];
      confounders?: string[];
    }) => {
      return api("/ml/causal/mediation", { method: "POST", body: request });
    },
    [],
  );

  const sensitivityAnalysis = useCallback(
    async (request: {
      data_name: string;
      treatment: string;
      outcome: string;
      confounders: string[];
      gamma_range?: [number, number];
      gamma_steps?: number;
    }) => {
      return api("/ml/causal/sensitivity", { method: "POST", body: request });
    },
    [],
  );

  const discoverGraph = useCallback(
    async (request: {
      data_name: string;
      method?: string;
      significance_level?: number;
    }) => {
      return api("/ml/causal/discover", { method: "POST", body: request });
    },
    [],
  );

  return {
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
  };
}

// ==================== Forecasting Hooks ====================

export function useForecasting() {
  const [dataSources, setDataSources] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const registerData = useCallback(
    async (request: {
      name: string;
      data: {
        timestamp: string;
        value: number;
        metadata?: Record<string, any>;
      }[];
      date_col?: string;
      value_col?: string;
    }) => {
      const response = await api("/ml/forecasting/data", {
        method: "POST",
        body: request,
      });
      setDataSources((prev) => [
        ...prev.filter((d) => d.name !== request.name),
        response.info,
      ]);
      return response;
    },
    [],
  );

  const listData = useCallback(async () => {
    const response = await api("/ml/forecasting/data");
    setDataSources(response.data || []);
    return response;
  }, []);

  const forecast = useCallback(
    async (request: {
      data_name: string;
      horizon: number;
      method?:
        | "prophet"
        | "neuralprophet"
        | "arima"
        | "sarima"
        | "exponential_smoothing"
        | "linear_regression"
        | "random_forest"
        | "gradient_boosting"
        | "ensemble";
      frequency?: string;
      confidence_level?: number;
      params?: Record<string, any>;
      include_history?: boolean;
    }) => {
      return api("/ml/forecasting/forecast", { method: "POST", body: request });
    },
    [],
  );

  const evaluate = useCallback(
    async (request: {
      data_name: string;
      horizon: number;
      methods?: string[];
      test_size?: number;
      params?: Record<string, any>;
    }) => {
      return api("/ml/forecasting/evaluate", { method: "POST", body: request });
    },
    [],
  );

  const detectAnomalies = useCallback(
    async (
      dataName: string,
      method = "isolation_forest",
      contamination = 0.1,
    ) => {
      return api("/ml/forecasting/anomaly", {
        method: "POST",
        body: { data_name: dataName, method, contamination },
      });
    },
    [],
  );

  useEffect(() => {
    listData();
  }, [listData]);

  return {
    dataSources,
    loading,
    error,
    registerData,
    listData,
    forecast,
    evaluate,
    detectAnomalies,
  };
}

// ==================== Text-to-SQL Hooks ====================

export function useTextToSQL() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const generateSQL = useCallback(
    async (request: {
      question: string;
      context?: string;
      schema?: string;
      dialect?:
        | "postgresql"
        | "mysql"
        | "snowflake"
        | "bigquery"
        | "redshift"
        | "databricks"
        | "spark"
        | "sqlite"
        | "tsql";
      max_tokens?: number;
      temperature?: number;
      include_explanation?: boolean;
      include_lineage?: boolean;
    }) => {
      setLoading(true);
      try {
        return await api("/ml/text-to-sql/generate", {
          method: "POST",
          body: request,
        });
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const validateSQL = useCallback(
    async (sql: string, dialect = "postgresql") => {
      return api("/ml/text-to-sql/validate", {
        method: "POST",
        body: { sql, dialect },
      });
    },
    [],
  );

  const explainQuery = useCallback(
    async (sql: string, dialect = "postgresql") => {
      return api("/ml/text-to-sql/explain", {
        method: "POST",
        body: { sql, dialect },
      });
    },
    [],
  );

  const getLineage = useCallback(async (sql: string) => {
    return api("/ml/text-to-sql/lineage", { method: "POST", body: sql });
  }, []);

  const transpileSQL = useCallback(
    async (sql: string, targetDialect: string) => {
      return api("/ml/text-to-sql/transpile", {
        method: "POST",
        body: { sql, target_dialect: targetDialect },
      });
    },
    [],
  );

  const getSemanticMetric = useCallback(
    async (request: {
      model_name: string;
      metric_name: string;
      dimensions?: string[];
      filters?: Record<string, any>;
      time_range?: [string, string];
      limit?: number;
    }) => {
      return api("/ml/text-to-sql/semantic/metric", {
        method: "POST",
        body: request,
      });
    },
    [],
  );

  const executeQuery = useCallback(async (sql: string) => {
    return api("/ml/text-to-sql/execute", { method: "POST", body: sql });
  }, []);

  return {
    loading,
    error,
    generateSQL,
    validateSQL,
    explainQuery,
    getLineage,
    transpileSQL,
    getSemanticMetric,
    executeQuery,
  };
}

// ==================== Proactive Insights Hooks ====================

export function useProactiveInsights() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [trends, setTrends] = useState<TrendChange[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const registerMetric = useCallback(
    async (request: {
      name: string;
      data: {
        timestamp: string;
        value: number;
        metadata?: Record<string, any>;
      }[];
      frequency?: string;
      thresholds?: Record<string, number>;
    }) => {
      return api("/ml/insights/metrics", { method: "POST", body: request });
    },
    [],
  );

  const updateMetric = useCallback(
    async (
      name: string,
      value: number,
      timestamp?: string,
      metadata?: Record<string, any>,
    ) => {
      return api("/ml/insights/metrics/update", {
        method: "POST",
        body: { name, value, timestamp, metadata },
      });
    },
    [],
  );

  const addAlertRule = useCallback(
    async (rule: {
      id: string;
      name: string;
      metric_patterns: string[];
      severity_threshold: "info" | "warning" | "critical";
      channels: string[];
      recipients: Record<string, string[]>;
      cooldown_minutes?: number;
      enabled?: boolean;
    }) => {
      return api("/ml/insights/alert-rules", { method: "POST", body: rule });
    },
    [],
  );

  const listAlertRules = useCallback(async () => {
    return api("/ml/insights/alert-rules");
  }, []);

  const startMonitoring = useCallback(async () => {
    return api("/ml/insights/start", { method: "POST" });
  }, []);

  const stopMonitoring = useCallback(async () => {
    return api("/ml/insights/stop", { method: "POST" });
  }, []);

  const getStatus = useCallback(async () => {
    const status = await api("/ml/insights/status");
    setStatus(status);
    return status;
  }, []);

  const getInsights = useCallback(
    async (options?: {
      severity?: string;
      metric?: string;
      limit?: number;
    }) => {
      const params = new URLSearchParams();
      if (options?.severity) params.append("severity", options.severity);
      if (options?.metric) params.append("metric", options.metric);
      if (options?.limit) params.append("limit", String(options.limit));
      const response = await api(`/ml/insights?${params.toString()}`);
      setInsights(response.insights || []);
      return response;
    },
    [],
  );

  const getAnomalies = useCallback(
    async (options?: {
      metric?: string;
      severity?: string;
      limit?: number;
    }) => {
      const params = new URLSearchParams();
      if (options?.metric) params.append("metric", options.metric);
      if (options?.severity) params.append("severity", options.severity);
      if (options?.limit) params.append("limit", String(options.limit));
      const response = await api(`/ml/insights/anomalies?${params.toString()}`);
      setAnomalies(response.anomalies || []);
      return response;
    },
    [],
  );

  const getTrends = useCallback(async (metric?: string, limit = 100) => {
    const response = await api(
      `/ml/insights/trends?metric=${metric || ""}&limit=${limit}`,
    );
    setTrends(response.trends || []);
    return response;
  }, []);

  const getAlerts = useCallback(async (limit = 100) => {
    const response = await api(`/ml/insights/alerts?limit=${limit}`);
    setAlerts(response.alerts || []);
    return response;
  }, []);

  const acknowledgeInsight = useCallback(async (insightId: string) => {
    await api(`/ml/insights/acknowledge/insight/${insightId}`, {
      method: "POST",
    });
    setInsights((prev) =>
      prev.map((i) => (i.id === insightId ? { ...i, acknowledged: true } : i)),
    );
  }, []);

  const acknowledgeAnomaly = useCallback(async (anomalyId: string) => {
    await api(`/ml/insights/acknowledge/anomaly/${anomalyId}`, {
      method: "POST",
    });
    setAnomalies(
      (prev) => (a) => (a.id === anomalyId ? { ...a, acknowledged: true } : a),
    );
  }, []);

  return {
    insights,
    anomalies,
    trends,
    alerts,
    status,
    loading,
    error,
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
  };
}

// ==================== Combined Hook ====================

export function useMLPlatform() {
  const featureStore = useFeatureStore();
  const modelRegistry = useModelRegistry();
  const inference = useInference();
  const causal = useCausalInference();
  const forecasting = useForecasting();
  const textToSQL = useTextToSQL();
  const insights = useProactiveInsights();

  return useMemo(
    () => ({
      featureStore,
      modelRegistry,
      inference,
      causal,
      forecasting,
      textToSQL,
      insights,
    }),
    [
      featureStore,
      modelRegistry,
      inference,
      causal,
      forecasting,
      textToSQL,
      insights,
    ],
  );
}

// ==================== Missing imports ====================

import { useState, useEffect, useCallback, useMemo } from "react";
