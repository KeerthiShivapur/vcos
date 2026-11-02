"""
ML Platform for VCOS Intelligence Layer.

Provides:
- Feature Store (Feast-compatible)
- Model Registry (MLflow-compatible)
- Inference Service (Triton/vLLM/TGI compatible)
- Causal Inference Engine (DoWhy/EconML)
- Forecasting Engine (Prophet/NeuralProphet/ARIMA/ML)
- Text-to-SQL / Semantic Layer
- Proactive Insights & Anomaly Detection
- Experiment Tracking
- Model Deployment & Monitoring
"""

from app.ml.feature_store import (
    FeatureStore, FeatureView, Entity, Feature, FeatureView as FV, ValueType,
    get_feature_store, init_feature_store,
)
from app.ml.model_registry import (
    ModelRegistry, ModelVersion, ModelStage, ModelStatus,
    RegisteredModel, ModelSignature, ModelDeployment,
    get_model_registry, init_model_registry,
)
from app.ml.inference_service import (
    InferenceService, InferenceRequest, InferenceResponse,
    InferenceBackend, ModelInstance,
    get_inference_service, init_inference_service,
)
from app.ml.causal_inference import (
    CausalInferenceEngine, TreatmentEffect, CounterfactualResult,
    MediationAnalysis, CausalMethod, EstimatorType,
    get_causal_engine, init_causal_engine,
)
from app.ml.forecasting import (
    ForecastingEngine, ForecastResult, ModelEvaluation,
    ForecastMethod, Frequency, TimeSeriesData,
    get_forecasting_engine, init_forecasting_engine,
)
from app.ml.text_to_sql import (
    TextToSQLService, TextToSQLRequest, TextToSQLResponse,
    SQLDialect, QueryValidationResult, SemanticLayer,
    SemanticModel, BusinessMetric,
    get_text_to_sql_service, init_text_to_sql_service,
)
from app.ml.proactive_insights import (
    ProactiveInsightsEngine, Insight, Anomaly, TrendChange, Alert,
    InsightType, InsightSeverity, AnomalyMethod, DataPoint,
    TimeSeriesMetric, AlertRule, AlertChannel,
    get_proactive_engine, init_proactive_engine,
)
# from app.ml.experiment_tracking import ExperimentTracker, get_experiment_tracker

__all__ = [
    # Feature Store
    "FeatureStore", "FeatureView", "Entity", "Feature", "ValueType",
    "get_feature_store", "init_feature_store",
    # Model Registry
    "ModelRegistry", "ModelVersion", "ModelStage", "ModelStatus",
    "RegisteredModel", "ModelSignature", "ModelDeployment",
    "get_model_registry", "init_model_registry",
    # Inference Service
    "InferenceService", "InferenceRequest", "InferenceResponse",
    "InferenceBackend", "ModelInstance",
    "get_inference_service", "init_inference_service",
    # Causal Inference
    "CausalInferenceEngine", "TreatmentEffect", "CounterfactualResult",
    "MediationAnalysis", "CausalMethod", "EstimatorType",
    "get_causal_engine", "init_causal_engine",
    # Forecasting
    "ForecastingEngine", "ForecastResult", "ModelEvaluation",
    "ForecastMethod", "Frequency", "TimeSeriesData",
    "get_forecasting_engine", "init_forecasting_engine",
    # Text-to-SQL
    "TextToSQLService", "TextToSQLRequest", "TextToSQLResponse",
    "SQLDialect", "QueryValidationResult", "SemanticLayer",
    "SemanticModel", "BusinessMetric",
    "get_text_to_sql_service", "init_text_to_sql_service",
    # Proactive Insights
    "ProactiveInsightsEngine", "Insight", "Anomaly", "TrendChange", "Alert",
    "InsightType", "InsightSeverity", "AnomalyMethod", "DataPoint",
    "TimeSeriesMetric", "AlertRule", "AlertChannel",
    "get_proactive_engine", "init_proactive_engine",
    #     "ExperimentTracker", "get_experiment_tracker",
]