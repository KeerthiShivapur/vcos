"""
ML Platform API Routes.

Provides REST endpoints for:
- Feature Store
- Model Registry
- Inference Service
- Causal Inference
- Forecasting
- Text-to-SQL
- Proactive Insights
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User

# ML Components
from app.ml.feature_store import (
    FeatureStore, Entity, Feature, FeatureView, ValueType,
    get_feature_store, init_feature_store,
)
from app.ml.model_registry import (
    ModelRegistry, ModelVersion, ModelStage, ModelStatus,
    RegisteredModel, ModelSignature, ModelDeployment,
    get_model_registry, init_model_registry,
)
from app.ml.inference_service import (
    InferenceService, InferenceRequest, InferenceResponse,
    InferenceBackend, get_inference_service, init_inference_service,
)
from app.ml.causal_inference import (
    CausalInferenceEngine, TreatmentEffect, CounterfactualResult,
    CausalMethod, EstimatorType, get_causal_engine, init_causal_engine,
)
from app.ml.forecasting import (
    ForecastingEngine, ForecastResult, ModelEvaluation,
    ForecastMethod, Frequency, TimeSeriesData,
    get_forecasting_engine, init_forecasting_engine,
)
from app.ml.text_to_sql import (
    TextToSQLService, TextToSQLRequest, TextToSQLResponse,
    SQLDialect, QueryValidationResult, SemanticLayer,
    get_text_to_sql_service, init_text_to_sql_service,
)
from app.ml.proactive_insights import (
    ProactiveInsightsEngine, Insight, Anomaly, TrendChange, Alert,
    InsightType, InsightSeverity, AnomalyMethod, DataPoint,
    TimeSeriesMetric, AlertRule, AlertChannel,
    get_proactive_engine, init_proactive_engine,
)

router = APIRouter(tags=["ML Platform"])

logger = logging.getLogger(__name__)


# ==================== Dependency Initialization ====================

async def get_ml_components():
    """Ensure all ML components are initialized."""
    # Initialize all singletons
    await init_feature_store()
    await init_model_registry()
    await init_inference_service()
    await init_causal_engine()
    await init_forecasting_engine()
    await init_text_to_sql_service()
    await init_proactive_engine()


# ==================== Feature Store Endpoints ====================

class EntityRequest(BaseModel):
    name: str
    join_keys: List[str]
    description: str = ""
    value_type: str = "string"
    tags: Dict[str, str] = {}


class FeatureRequest(BaseModel):
    name: str
    dtype: str
    description: str = ""
    tags: Dict[str, str] = {}


class FeatureViewRequest(BaseModel):
    name: str
    entities: List[str]
    features: List[FeatureRequest]
    ttl_days: int = 1
    batch_source: Optional[str] = None
    stream_source: Optional[str] = None
    online: bool = True
    description: str = ""
    tags: Dict[str, str] = {}


class OnlineWriteRequest(BaseModel):
    feature_view: str
    entity_id: str
    features: Dict[str, Any]
    event_timestamp: Optional[str] = None


class OnlineReadRequest(BaseModel):
    feature_view: str
    entity_ids: List[str]


class BatchWriteRequest(BaseModel):
    feature_view: str
    data: List[Dict[str, Any]]


class TrainingDataRequest(BaseModel):
    entity_ids: List[str]
    feature_views: List[str]
    start_time: str
    end_time: str


@router.post("/ml/feature-store/entities")
async def create_entity(
    request: EntityRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a feature store entity."""
    fs = get_feature_store()
    await fs.initialize()

    entity = Entity(
        name=request.name,
        join_keys=request.join_keys,
        description=request.description,
        value_type=ValueType(request.value_type),
        tags=request.tags,
    )
    fs.apply_entity(entity)
    return {"success": True, "entity": entity.name}


@router.get("/ml/feature-store/entities")
async def list_entities(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all entities."""
    fs = get_feature_store()
    return {"entities": [{"name": e.name, "join_keys": e.join_keys, "description": e.description} for e in fs.list_entities()]}


@router.post("/ml/feature-store/feature-views")
async def create_feature_view(
    request: FeatureViewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a feature view."""
    fs = get_feature_store()
    await fs.initialize()

    features = [Feature(name=f.name, dtype=ValueType(f.dtype), description=f.description, tags=f.tags) for f in request.features]

    fv = FeatureView(
        name=request.name,
        entities=request.entities,
        features=features,
        ttl=timedelta(days=request.ttl_days),
        batch_source=request.batch_source,
        stream_source=request.stream_source,
        online=request.online,
        description=request.description,
        tags=request.tags,
    )
    fs.apply_feature_view(fv)
    return {"success": True, "feature_view": fv.name}


@router.get("/ml/feature-store/feature-views")
async def list_feature_views(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all feature views."""
    fs = get_feature_store()
    return {"feature_views": [{"name": fv.name, "entities": fv.entities, "features": [f.name for f in fv.features]} for fv in fs.list_feature_views()]}


@router.post("/ml/feature-store/online/write")
async def online_write(
    request: OnlineWriteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write features to online store."""
    fs = get_feature_store()
    await fs.initialize()

    timestamp = datetime.fromisoformat(request.event_timestamp) if request.event_timestamp else None
    await fs.online_write(request.feature_view, request.entity_id, request.features, timestamp)
    return {"success": True}


@router.post("/ml/feature-store/online/read")
async def online_read(
    request: OnlineReadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read features from online store."""
    fs = get_feature_store()
    features = await fs.online_read(request.feature_view, request.entity_ids)
    return {"features": features}


@router.post("/ml/feature-store/online/features")
async def get_online_features(
    entity_id: str = Body(...),
    feature_views: Optional[List[str]] = Body(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all online features for an entity."""
    fs = get_feature_store()
    features = await fs.get_online_features(entity_id, feature_views)
    return {"features": features}


@router.post("/ml/feature-store/offline/write")
async def batch_write(
    request: BatchWriteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write batch features to offline store."""
    fs = get_feature_store()
    await fs.initialize()
    await fs.write_batch(request.feature_view, request.data)
    return {"success": True, "count": len(request.data)}


@router.post("/ml/feature-store/offline/training-data")
async def get_training_data(
    request: TrainingDataRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get training data with point-in-time correctness."""
    fs = get_feature_store()
    start = datetime.fromisoformat(request.start_time)
    end = datetime.fromisoformat(request.end_time)
    data = await fs.get_training_data(request.entity_ids, request.feature_views, start, end)
    return {"data": data}


@router.post("/ml/feature-store/materialize")
async def materialize(
    feature_view: str = Body(...),
    start_time: str = Body(...),
    end_time: str = Body(...),
    batch_size: int = Body(1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Materialize features from offline to online store."""
    fs = get_feature_store()
    await fs.initialize()
    start = datetime.fromisoformat(start_time)
    end = datetime.fromisoformat(end_time)
    await fs.materialize(feature_view, start, end, batch_size)
    return {"success": True}


# ==================== Model Registry Endpoints ====================

class CreateModelRequest(BaseModel):
    name: str
    description: str = ""
    tags: Dict[str, str] = {}


class RegisterModelRequest(BaseModel):
    name: str
    run_id: str = ""
    experiment_id: str = ""
    source: str = ""
    version: Optional[int] = None
    description: str = ""
    tags: Dict[str, str] = {}
    params: Dict[str, Any] = {}
    metrics: Dict[str, float] = {}
    signature: Optional[Dict[str, Any]] = None
    parent_version: Optional[int] = None
    dataset_version: str = ""
    created_by: str = ""


class TransitionStageRequest(BaseModel):
    stage: str  # staging, production, archived


class ArtifactRequest(BaseModel):
    path: str
    size_bytes: int
    checksum: str
    artifact_type: str
    metadata: Dict[str, Any] = {}


class CreateDeploymentRequest(BaseModel):
    model_name: str
    model_version: int
    endpoint_name: str
    endpoint_url: str
    replicas: int = 1
    resources: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    health_check_url: str = ""


@router.post("/ml/models")
async def create_model(
    request: CreateModelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a model."""
    mr = get_model_registry()
    await mr.initialize()
    model = await mr.create_model(request.name, request.description, request.tags)
    return {"success": True, "model": {"name": model.name, "description": model.description}}


@router.get("/ml/models")
async def list_models(
    tags: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all models."""
    mr = get_model_registry()
    filter_tags = {}
    if tags:
        for t in tags.split(","):
            k, v = t.split("=", 1)
            filter_tags[k] = v
    models = await mr.list_models(filter_tags)
    return {"models": [{"name": m.name, "description": m.description, "latest_version": m.latest_version, "production_version": m.production_version, "staging_version": m.staging_version} for m in models]}


@router.get("/ml/models/{name}")
async def get_model(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get model details."""
    mr = get_model_registry()
    model = await mr.get_model(name)
    if not model:
        raise HTTPException(404, "Model not found")
    return {
        "name": model.name,
        "description": model.description,
        "tags": model.tags,
        "versions": [
            {
                "version": v.version,
                "stage": v.stage.value,
                "status": v.status.value,
                "run_id": v.run_id,
                "metrics": v.metrics,
                "created_at": v.created_at.isoformat(),
            }
            for v in model.versions
        ],
        "latest_version": model.latest_version,
        "production_version": model.production_version,
        "staging_version": model.staging_version,
    }


@router.post("/ml/models/{name}/versions")
async def register_model_version(
    name: str,
    request: RegisterModelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a model version."""
    mr = get_model_registry()
    version = await mr.register_model(
        name=name,
        run_id=request.run_id,
        experiment_id=request.experiment_id,
        source=request.source,
        version=request.version,
        description=request.description,
        tags=request.tags,
        params=request.params,
        metrics=request.metrics,
        signature=ModelSignature(**request.signature) if request.signature else None,
        parent_version=request.parent_version,
        dataset_version=request.dataset_version,
        created_by=request.created_by,
    )
    return {"success": True, "version": version.version}


@router.post("/ml/models/{name}/versions/{version}/stage")
async def transition_stage(
    name: str,
    version: int,
    request: TransitionStageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transition model version to a new stage."""
    mr = get_model_registry()
    await mr.transition_stage(name, version, ModelStage(request.stage))
    return {"success": True}


@router.post("/ml/models/{name}/versions/{version}/artifacts")
async def add_artifacts(
    name: str,
    version: int,
    artifacts: List[ArtifactRequest],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add artifacts to model version."""
    mr = get_model_registry()
    artifacts_list = [
        ModelArtifact(
            path=a.path,
            size_bytes=a.size_bytes,
            checksum=a.checksum,
            artifact_type=a.artifact_type,
            metadata=a.metadata,
        )
        for a in artifacts
    ]
    await mr.add_artifacts(name, version, artifacts_list)
    return {"success": True}


@router.post("/ml/models/{name}/versions/{version}/signature")
async def set_signature(
    name: str,
    version: int,
    signature: Dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set model signature."""
    mr = get_model_registry()
    await mr.set_signature(name, version, ModelSignature(**signature))
    return {"success": True}


@router.post("/ml/models/{name}/versions/{version}/transition/staging")
async def transition_to_staging(
    name: str,
    version: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mr = get_model_registry()
    await mr.transition_to_staging(name, version)
    return {"success": True}


@router.post("/ml/models/{name}/versions/{version}/transition/production")
async def transition_to_production(
    name: str,
    version: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mr = get_model_registry()
    await mr.transition_to_production(name, version)
    return {"success": True}


@router.post("/ml/models/{name}/versions/{version}/archive")
async def archive_version(
    name: str,
    version: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mr = get_model_registry()
    await mr.archive(name, version)
    return {"success": True}


@router.post("/ml/deployments")
async def create_deployment(
    request: CreateDeploymentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create model deployment."""
    mr = get_model_registry()
    deployment = await mr.create_deployment(
        model_name=request.model_name,
        model_version=request.model_version,
        endpoint_name=request.endpoint_name,
        endpoint_url=request.endpoint_url,
        replicas=request.replicas,
        resources=request.resources,
        config=request.config,
        health_check_url=request.health_check_url,
    )
    return {"success": True, "deployment_id": deployment.id}


@router.get("/ml/deployments")
async def list_deployments(
    model_name: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mr = get_model_registry()
    deployments = await mr.list_deployments(model_name)
    return {"deployments": [{"id": d.id, "model_name": d.model_name, "model_version": d.model_version, "endpoint_name": d.endpoint_name, "endpoint_url": d.endpoint_url, "status": d.status, "replicas": d.replicas} for d in deployments]}


@router.post("/ml/deployments/{deployment_id}/status")
async def update_deployment_status(
    deployment_id: str,
    status: str = Body(...),
    metrics: Dict[str, Any] = Body({}),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mr = get_model_registry()
    await mr.update_deployment_status(deployment_id, status, metrics)
    return {"success": True}


# ==================== Inference Service Endpoints ====================

class InferenceRequestModel(BaseModel):
    model_name: str
    inputs: Dict[str, Any]
    version: Optional[int] = None
    parameters: Dict[str, Any] = {}
    stream: bool = False
    priority: int = 0
    timeout: float = 30.0


class BatchInferenceRequest(BaseModel):
    model_name: str
    requests: List[Dict[str, Any]]
    version: Optional[int] = None


class LoadModelRequest(BaseModel):
    model_name: str
    version: Optional[int] = None
    backend: Optional[str] = None
    endpoint: Optional[str] = None


@router.post("/ml/inference/load")
async def load_model(
    request: LoadModelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Load model into inference service."""
    isvc = get_inference_service()
    await isvc.initialize()
    backend = InferenceBackend(request.backend) if request.backend else None
    instance = await isvc.load_model(request.model_name, request.version, backend, request.endpoint)
    return {"success": True, "instance": {"id": instance.id, "model_name": instance.model_name, "model_version": instance.model_version, "backend": instance.backend.value, "status": instance.status}}


@router.post("/ml/inference/unload")
async def unload_model(
    model_name: str = Body(...),
    version: int = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unload model from inference service."""
    isvc = get_inference_service()
    await isvc.unload_model(model_name, version)
    return {"success": True}


@router.post("/ml/inference/predict")
async def predict(
    request: InferenceRequestModel,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run inference."""
    isvc = get_inference_service()
    result = await isvc.infer(
        model_name=request.model_name,
        inputs=request.inputs,
        version=request.version,
        parameters=request.parameters,
        stream=request.stream,
        priority=request.priority,
        timeout=request.timeout,
    )
    return {
        "id": result.id,
        "request_id": result.request_id,
        "model_name": result.model_name,
        "model_version": result.model_version,
        "outputs": result.outputs,
        "status": result.status.value,
        "latency_ms": result.latency_ms,
        "tokens_used": result.tokens_used,
        "error": result.error,
    }


@router.post("/ml/inference/stream")
async def stream_predict(
    request: InferenceRequestModel,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream inference."""
    isvc = get_inference_service()
    from fastapi.responses import StreamingResponse
    import json

    async def generate():
        async for chunk in isvc.stream_infer(
            model_name=request.model_name,
            inputs=request.inputs,
            version=request.version,
            parameters=request.parameters,
            timeout=request.timeout,
        ):
            yield f"data: {json.dumps({'outputs': chunk.outputs, 'status': chunk.status.value, 'latency_ms': chunk.latency_ms})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/ml/inference/batch")
async def batch_predict(
    request: BatchInferenceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch inference."""
    isvc = get_inference_service()
    results = await isvc.batch_infer(request.model_name, request.requests, request.version)
    return {"results": [{"id": r.id, "outputs": r.outputs, "status": r.status.value, "latency_ms": r.latency_ms} for r in results]}


@router.get("/ml/inference/health")
async def inference_health(
    model_name: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check inference service health."""
    isvc = get_inference_service()
    health = await isvc.health_check(model_name)
    return health


@router.get("/ml/inference/models")
async def list_loaded_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    isvc = get_inference_service()
    models = isvc.list_loaded_models()
    return {"models": [{"id": m.id, "model_name": m.model_name, "model_version": m.model_version, "backend": m.backend.value, "status": m.status, "loaded_at": m.loaded_at.isoformat()} for m in models]}


# ==================== Causal Inference Endpoints ====================

class CausalGraphRequest(BaseModel):
    name: str
    nodes: List[str]
    edges: List[List[str]]
    latent_variables: List[str] = []


class TreatmentEffectRequest(BaseModel):
    data_name: str
    treatment: str
    outcome: str
    confounders: List[str] = []
    effect_modifiers: List[str] = []
    method: str = "backdoor"
    estimator: str = "linear_regression"
    graph_name: Optional[str] = None


class CounterfactualRequest(BaseModel):
    data_name: str
    treatment: str
    outcome: str
    confounders: List[str]
    factual_values: Dict[str, Any]
    counterfactual_values: Dict[str, Any]


class MediationRequest(BaseModel):
    data_name: str
    treatment: str
    outcome: str
    mediators: List[str]
    confounders: List[str] = []


class SensitivityRequest(BaseModel):
    data_name: str
    treatment: str
    outcome: str
    confounders: List[str]
    gamma_range: List[float] = [0.5, 2.0]
    gamma_steps: int = 10


class DiscoveryRequest(BaseModel):
    data_name: str
    method: str = "pc"
    significance_level: float = 0.05


@router.post("/ml/causal/graph")
async def create_causal_graph(
    request: CausalGraphRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create causal graph."""
    ce = get_causal_engine()
    graph = ce.create_graph(request.name, request.nodes, request.edges, request.latent_variables)
    return {"success": True, "graph": {"name": graph.name, "nodes": graph.nodes, "edges": graph.edges}}


@router.get("/ml/causal/graphs")
async def list_graphs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ce = get_causal_engine()
    return {"graphs": ce.list_graphs()}


@router.get("/ml/causal/graphs/{name}")
async def get_graph(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ce = get_causal_engine()
    graph = ce.get_graph(name)
    if not graph:
        raise HTTPException(404, "Graph not found")
    return {"name": graph.name, "nodes": graph.nodes, "edges": graph.edges, "latent_variables": graph.latent_variables}


@router.get("/ml/causal/graphs/{name}/validate")
async def validate_graph(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ce = get_causal_engine()
    return ce.validate_graph(name)


@router.get("/ml/causal/graphs/{name}/visualize")
async def visualize_graph(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ce = get_causal_engine()
    dot = ce.visualize_graph(name)
    return {"dot": dot}


@router.post("/ml/causal/data")
async def register_causal_data(
    name: str = Body(...),
    data: List[Dict[str, Any]] = Body(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register data for causal analysis."""
    ce = get_causal_engine()
    df = pd.DataFrame(data)
    ce.register_data(name, df)
    return {"success": True, "info": ce.get_data_info(name)}


@router.get("/ml/causal/data")
async def list_causal_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ce = get_causal_engine()
    return {"data": ce.list_data()}


@router.post("/ml/causal/estimate")
async def estimate_treatment_effect(
    request: TreatmentEffectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimate treatment effect."""
    ce = get_causal_engine()
    result = await ce.estimate_treatment_effect(
        data_name=request.data_name,
        treatment=request.treatment,
        outcome=request.outcome,
        confounders=request.confounders,
        effect_modifiers=request.effect_modifiers,
        method=CausalMethod(request.method),
        estimator=EstimatorType(request.estimator),
        graph_name=request.graph_name,
    )
    return {
        "ate": result.ate,
        "ate_ci": result.ate_ci,
        "ate_pvalue": result.ate_pvalue,
        "cate": result.cate,
        "cate_ci": result.cate_ci,
        "ite": result.ite.tolist() if result.ite is not None else None,
        "method": result.method,
        "estimator": result.estimator,
        "assumptions": result.assumptions,
        "diagnostics": result.diagnostics,
    }


@router.post("/ml/causal/counterfactual")
async def estimate_counterfactual(
    request: CounterfactualRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimate counterfactual."""
    ce = get_causal_engine()
    result = await ce.estimate_counterfactual(
        data_name=request.data_name,
        treatment=request.treatment,
        outcome=request.outcome,
        confounders=request.confounders,
        factual_values=request.factual_values,
        counterfactual_values=request.counterfactual_values,
    )
    return {
        "factual_outcome": result.factual_outcome,
        "counterfactual_outcome": result.counterfactual_outcome,
        "effect": result.effect,
        "confidence_interval": result.confidence_interval,
        "probability_necessary": result.probability_necessary,
        "probability_sufficient": result.probability_sufficient,
        "explanation": result.explanation,
    }


@router.post("/ml/causal/mediation")
async def mediation_analysis(
    request: MediationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mediation analysis."""
    ce = get_causal_engine()
    result = await ce.mediation_analysis(
        data_name=request.data_name,
        treatment=request.treatment,
        outcome=request.outcome,
        mediators=request.mediators,
        confounders=request.confounders,
    )
    return {
        "total_effect": result.total_effect,
        "direct_effect": result.direct_effect,
        "indirect_effect": result.indirect_effect,
        "proportion_mediated": result.proportion_mediated,
        "mediator_effects": result.mediator_effects,
        "confidence_intervals": result.confidence_intervals,
    }


@router.post("/ml/causal/sensitivity")
async def sensitivity_analysis(
    request: SensitivityRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sensitivity analysis."""
    ce = get_causal_engine()
    return await ce.sensitivity_analysis(
        data_name=request.data_name,
        treatment=request.treatment,
        outcome=request.outcome,
        confounders=request.confounders,
        gamma_range=tuple(request.gamma_range),
        gamma_steps=request.gamma_steps,
    )


@router.post("/ml/causal/discover")
async def discover_causal_graph(
    request: DiscoveryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discover causal graph from data."""
    ce = get_causal_engine()
    graph = await ce.discover_causal_graph(request.data_name, request.method, request.significance_level)
    return {"name": graph.name, "nodes": graph.nodes, "edges": graph.edges}


# ==================== Forecasting Endpoints ====================

class ForecastRequest(BaseModel):
    data_name: str
    horizon: int
    method: str = "prophet"
    frequency: Optional[str] = None
    confidence_level: float = 0.95
    params: Dict[str, Any] = {}
    include_history: bool = False


class RegisterDataRequest(BaseModel):
    name: str
    data: List[Dict[str, Any]]
    date_col: str = "ds"
    value_col: str = "y"


class EvaluateRequest(BaseModel):
    data_name: str
    horizon: int
    methods: List[str] = ["prophet", "arima", "random_forest", "gradient_boosting"]
    test_size: float = 0.2
    params: Dict[str, Any] = {}


class AnomalyDetectionRequest(BaseModel):
    data_name: str
    method: str = "isolation_forest"
    contamination: float = 0.1


@router.post("/ml/forecasting/data")
async def register_forecast_data(
    request: RegisterDataRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register time series data."""
    fe = get_forecasting_engine()
    fe.register_data(request.name, request.data, request.date_col, request.value_col)
    return {"success": True, "info": fe.get_data_info(request.name)}


@router.get("/ml/forecasting/data")
async def list_forecast_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fe = get_forecasting_engine()
    return {"data": fe.list_data()}


@router.post("/ml/forecasting/forecast")
async def generate_forecast(
    request: ForecastRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate forecast."""
    fe = get_forecasting_engine()
    result = await fe.forecast(
        data_name=request.data_name,
        horizon=request.horizon,
        method=ForecastMethod(request.method),
        frequency=Frequency(request.frequency) if request.frequency else None,
        confidence_level=request.confidence_level,
        params=request.params,
        include_history=request.include_history,
    )
    return {
        "timestamps": [t.isoformat() for t in result.timestamps],
        "forecast": result.forecast.tolist(),
        "lower_bound": result.lower_bound.tolist() if result.lower_bound is not None else None,
        "upper_bound": result.upper_bound.tolist() if result.upper_bound is not None else None,
        "confidence_level": result.confidence_level,
        "method": result.method,
        "model_params": result.model_params,
        "metrics": result.metrics,
    }


@router.post("/ml/forecasting/evaluate")
async def evaluate_models(
    request: EvaluateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate forecasting methods."""
    fe = get_forecasting_engine()
    methods = [ForecastMethod(m) for m in request.methods]
    results = await fe.evaluate(request.data_name, request.horizon, methods, request.test_size, request.params)
    return {
        "results": {
            k: {
                "mae": v.mae,
                "mse": v.mse,
                "rmse": v.rmse,
                "mape": v.mape,
                "smape": v.smape,
                "coverage": v.coverage,
            }
            for k, v in results.items()
        }
    }


@router.post("/ml/forecasting/anomaly")
async def detect_forecast_anomalies(
    request: AnomalyDetectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect anomalies in time series."""
    fe = get_forecasting_engine()
    return await fe.detect_anomalies(request.data_name, request.method, request.contamination)


# ==================== Text-to-SQL Endpoints ====================

class TextToSQLRequestModel(BaseModel):
    question: str
    context: Optional[str] = None
    schema: Optional[str] = None
    dialect: str = "postgresql"
    max_tokens: int = 2000
    temperature: float = 0.1
    include_explanation: bool = True
    include_lineage: bool = False


class ValidateSQLRequest(BaseModel):
    sql: str
    dialect: str = "postgresql"


class ExplainQueryRequest(BaseModel):
    sql: str
    dialect: str = "postgresql"


class TranspileSQLRequest(BaseModel):
    sql: str
    target_dialect: str


class SemanticMetricRequest(BaseModel):
    model_name: str
    metric_name: str
    dimensions: List[str] = []
    filters: Dict[str, Any] = {}
    time_range: Optional[List[str]] = None
    limit: int = 1000


class SemanticModelRequest(BaseModel):
    name: str
    description: str
    tables: List[Dict[str, Any]]
    metrics: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]] = []


@router.post("/ml/text-to-sql/generate")
async def generate_sql(
    request: TextToSQLRequestModel,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate SQL from natural language."""
    tts = get_text_to_sql_service()
    await tts.initialize()

    dialect = SQLDialect(request.dialect)
    request_obj = TextToSQLRequest(
        question=request.question,
        context=request.context,
        schema=request.schema,
        dialect=dialect,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        include_explanation=request.include_explanation,
        include_lineage=request.include_lineage,
    )
    result = await tts.generate_sql(request_obj)
    return {
        "sql": result.sql,
        "dialect": result.dialect.value,
        "explanation": result.explanation,
        "confidence": result.confidence,
        "tables_used": result.tables_used,
        "columns_used": result.columns_used,
        "lineage": result.lineage,
        "warnings": result.warnings,
    }


@router.post("/ml/text-to-sql/validate")
async def validate_sql(
    request: ValidateSQLRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate SQL query."""
    tts = get_text_to_sql_service()
    dialect = SQLDialect(request.dialect)
    result = await tts.validate_sql(request.sql, dialect)
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "tables_referenced": result.tables_referenced,
        "columns_referenced": result.columns_referenced,
        "complexity_score": result.complexity_score,
    }


@router.post("/ml/text-to-sql/explain")
async def explain_query(
    request: ExplainQueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Explain SQL query."""
    tts = get_text_to_sql_service()
    explanation = await tts.explain_query(request.sql, SQLDialect(request.dialect))
    return {"explanation": explanation}


@router.post("/ml/text-to-sql/lineage")
async def get_lineage(
    sql: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get data lineage."""
    tts = get_text_to_sql_service()
    return tts.get_lineage(sql)


@router.post("/ml/text-to-sql/transpile")
async def transpile_sql(
    request: TranspileSQLRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transpile SQL to another dialect."""
    tts = get_text_to_sql_service()
    target = SQLDialect(request.target_dialect)
    sql = await tts.transpile_sql(request.sql, target)
    return {"sql": sql, "target_dialect": target.value}


@router.post("/ml/text-to-sql/semantic/metric")
async def get_semantic_metric(
    request: SemanticMetricRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get SQL for a semantic metric."""
    tts = get_text_to_sql_service()
    time_range = None
    if request.time_range:
        time_range = (datetime.fromisoformat(request.time_range[0]), datetime.fromisoformat(request.time_range[1]))
    sql = tts.get_semantic_metric(
        request.model_name,
        request.metric_name,
        request.dimensions,
        request.filters,
        time_range,
        request.limit,
    )
    return {"sql": sql}


@router.post("/ml/text-to-sql/semantic/model")
async def register_semantic_model(
    request: SemanticModelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register semantic model."""
    tts = get_text_to_sql_service()
    # Build model from request
    # This is simplified - in production would parse full model
    return {"success": True, "message": "Semantic model registration not fully implemented in this endpoint"}


@router.post("/ml/text-to-sql/execute")
async def execute_query(
    sql: str = Body(..., embed=True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute SQL query."""
    tts = get_text_to_sql_service()
    try:
        await tts.initialize()
        results = await tts.execute_query(sql)
        return {"results": results}
    except Exception as e:
        raise HTTPException(400, str(e))


# ==================== Proactive Insights Endpoints ====================

class RegisterMetricRequest(BaseModel):
    name: str
    data: List[Dict[str, Any]]
    frequency: str = "1h"
    thresholds: Dict[str, float] = {}


class UpdateMetricRequest(BaseModel):
    name: str
    value: float
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = {}


class AlertRuleRequest(BaseModel):
    id: str
    name: str
    metric_patterns: List[str]
    severity_threshold: str = "warning"
    channels: List[str] = []
    recipients: Dict[str, List[str]] = {}
    cooldown_minutes: int = 60
    enabled: bool = True


@router.post("/ml/insights/metrics")
async def register_metric(
    request: RegisterMetricRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register metric for monitoring."""
    pe = get_proactive_engine()
    data_points = [
        DataPoint(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            value=d["value"],
            metadata=d.get("metadata", {}),
        )
        for d in request.data
    ]
    pe.register_metric(request.name, data_points, request.frequency, request.thresholds)
    return {"success": True}


@router.post("/ml/insights/metrics/update")
async def update_metric(
    request: UpdateMetricRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update metric with new value."""
    pe = get_proactive_engine()
    timestamp = datetime.fromisoformat(request.timestamp) if request.timestamp else None
    pe.update_metric(request.name, request.value, timestamp, request.metadata)
    return {"success": True}


@router.post("/ml/insights/alert-rules")
async def add_alert_rule(
    request: AlertRuleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add alert routing rule."""
    pe = get_proactive_engine()
    rule = AlertRule(
        id=request.id,
        name=request.name,
        metric_patterns=request.metric_patterns,
        severity_threshold=InsightSeverity(request.severity_threshold),
        channels=[AlertChannel(c) for c in request.channels],
        recipients={AlertChannel(k): v for k, v in request.recipients.items()},
        cooldown_minutes=request.cooldown_minutes,
        enabled=request.enabled,
    )
    pe.alert_manager.add_rule(rule)
    return {"success": True}


@router.get("/ml/insights/alert-rules")
async def list_alert_rules(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pe = get_proactive_engine()
    return {"rules": [{"id": r.id, "name": r.name, "metric_patterns": r.metric_patterns, "severity_threshold": r.severity_threshold.value, "channels": [c.value for c in r.channels], "recipients": {k.value: v for k, v in r.recipients.items()}, "cooldown_minutes": r.cooldown_minutes, "enabled": r.enabled} for r in pe.alert_manager.get_rules()]}


@router.post("/ml/insights/start")
async def start_monitoring(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start proactive monitoring."""
    pe = get_proactive_engine()
    await pe.start_monitoring()
    return {"success": True, "message": "Monitoring started"}


@router.post("/ml/insights/stop")
async def stop_monitoring(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop proactive monitoring."""
    pe = get_proactive_engine()
    await pe.stop_monitoring()
    return {"success": True, "message": "Monitoring stopped"}


@router.get("/ml/insights/status")
async def get_insights_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get insights engine status."""
    pe = get_proactive_engine()
    return pe.get_status()


@router.get("/ml/insights")
async def get_insights(
    severity: Optional[str] = Query(None),
    metric: Optional[str] = Query(None),
    limit: int = Query(100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent insights."""
    pe = get_proactive_engine()
    sev = InsightSeverity(severity) if severity else None
    insights = pe.get_insights(severity=sev, metric=metric, limit=limit)
    return {
        "insights": [
            {
                "id": i.id,
                "type": i.type.value,
                "title": i.title,
                "description": i.description,
                "severity": i.severity.value,
                "metrics_affected": i.metrics_affected,
                "detected_at": i.detected_at.isoformat(),
                "suggested_actions": i.suggested_actions,
                "confidence": i.confidence,
                "acknowledged": i.acknowledged,
            }
            for i in insights
        ]
    }


@router.get("/ml/insights/anomalies")
async def get_anomalies(
    metric: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent anomalies."""
    pe = get_proactive_engine()
    sev = InsightSeverity(severity) if severity else None
    anomalies = pe.get_anomalies(metric=metric, severity=sev, limit=limit)
    return {
        "anomalies": [
            {
                "id": a.id,
                "metric_name": a.metric_name,
                "timestamp": a.timestamp.isoformat(),
                "value": a.value,
                "expected_range": a.expected_range,
                "severity": a.severity.value,
                "method": a.method.value,
                "score": a.score,
                "explanation": a.explanation,
                "acknowledged": a.acknowledged,
            }
            for a in anomalies
        ]
    }


@router.get("/ml/insights/trends")
async def get_trend_changes(
    metric: Optional[str] = Query(None),
    limit: int = Query(100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trend changes."""
    pe = get_proactive_engine()
    trends = pe.get_trend_changes(metric, limit)
    return {
        "trends": [
            {
                "id": t.id,
                "metric_name": t.metric_name,
                "change_point": t.change_point.isoformat(),
                "direction": t.direction,
                "magnitude": t.magnitude,
                "confidence": t.confidence,
                "before_trend": t.before_trend,
                "after_trend": t.after_trend,
                "method": t.method,
            }
            for t in trends
        ]
    }


@router.get("/ml/insights/alerts")
async def get_alerts(
    limit: int = Query(100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent alerts."""
    pe = get_proactive_engine()
    alerts = pe.get_alerts(limit)
    return {
        "alerts": [
            {
                "id": a.id,
                "insight_id": a.insight_id,
                "channel": a.channel.value,
                "recipient": a.recipient,
                "subject": a.subject,
                "message": a.message,
                "severity": a.severity.value,
                "sent": a.sent,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                "error": a.error,
            }
            for a in alerts
        ]
    }


@router.post("/ml/insights/acknowledge/insight/{insight_id}")
async def acknowledge_insight(
    insight_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pe = get_proactive_engine()
    pe.acknowledge_insight(insight_id, user.id)
    return {"success": True}


@router.post("/ml/insights/acknowledge/anomaly/{anomaly_id}")
async def acknowledge_anomaly(
    anomaly_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pe = get_proactive_engine()
    pe.acknowledge_anomaly(anomaly_id, user.id)
    return {"success": True}


# ==================== System Endpoints ====================

@router.get("/ml/status")
async def ml_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get ML platform status."""
    # Check all components
    status = {
        "feature_store": "initialized" if _feature_store else "not_initialized",
        "model_registry": "initialized" if _model_registry else "not_initialized",
        "inference_service": "initialized" if _inference_service else "not_initialized",
        "causal_inference": "initialized" if _causal_engine else "not_initialized",
        "forecasting": "initialized" if _forecasting_engine else "not_initialized",
        "text_to_sql": "initialized" if _text_to_sql_service else "not_initialized",
        "proactive_insights": "initialized" if _proactive_engine else "not_initialized",
    }
    return {"components": status}


# Global instances
_feature_store = None
_model_registry = None
_inference_service = None
_causal_engine = None
_forecasting_engine = None
_text_to_sql_service = None
_proactive_engine = None


# Import missing modules
from datetime import timedelta
import pandas as pd
from fastapi import Body
from fastapi.responses import StreamingResponse
from app.ml.feature_store import _feature_store as fs_global
from app.ml.model_registry import _model_registry as mr_global
from app.ml.inference_service import _inference_service as isvc_global
from app.ml.causal_inference import _causal_engine as ce_global
from app.ml.forecasting import _forecasting_engine as fe_global
from app.ml.text_to_sql import _text_to_sql_service as tts_global
from app.ml.proactive_insights import _proactive_engine as pe_global

# Update globals
def get_feature_store():
    global _feature_store
    if _feature_store is None:
        from app.ml.feature_store import FeatureStore
        _feature_store = FeatureStore()
    return _feature_store


def get_model_registry():
    global _model_registry
    if _model_registry is None:
        from app.ml.model_registry import ModelRegistry
        _model_registry = ModelRegistry()
    return _model_registry


def get_inference_service():
    global _inference_service
    if _inference_service is None:
        from app.ml.inference_service import InferenceService
        _inference_service = InferenceService()
    return _inference_service


def get_causal_engine():
    global _causal_engine
    if _causal_engine is None:
        from app.ml.causal_inference import CausalInferenceEngine
        _causal_engine = CausalInferenceEngine()
    return _causal_engine


def get_forecasting_engine():
    global _forecasting_engine
    if _forecasting_engine is None:
        from app.ml.forecasting import ForecastingEngine
        _forecasting_engine = ForecastingEngine()
    return _forecasting_engine


def get_text_to_sql_service():
    global _text_to_sql_service
    if _text_to_sql_service is None:
        from app.ml.text_to_sql import TextToSQLService
        _text_to_sql_service = TextToSQLService()
    return _text_to_sql_service


def get_proactive_engine():
    global _proactive_engine
    if _proactive_engine is None:
        from app.ml.proactive_insights import ProactiveInsightsEngine
        _proactive_engine = ProactiveInsightsEngine()
    return _proactive_engine


# Update init functions
async def init_feature_store():
    global _feature_store
    from app.ml.feature_store import FeatureStore
    _feature_store = FeatureStore()
    await _feature_store.initialize()


async def init_model_registry():
    global _model_registry
    from app.ml.model_registry import ModelRegistry
    _model_registry = ModelRegistry()
    await _model_registry.initialize()


async def init_inference_service():
    global _inference_service
    from app.ml.inference_service import InferenceService
    _inference_service = InferenceService()
    await _inference_service.initialize()


async def init_causal_engine():
    global _causal_engine
    from app.ml.causal_inference import CausalInferenceEngine
    _causal_engine = CausalInferenceEngine()


async def init_forecasting_engine():
    global _forecasting_engine
    from app.ml.forecasting import ForecastingEngine
    _forecasting_engine = ForecastingEngine()


async def init_text_to_sql_service():
    global _text_to_sql_service
    from app.ml.text_to_sql import TextToSQLService
    _text_to_sql_service = TextToSQLService()
    await _text_to_sql_service.initialize()


async def init_proactive_engine():
    global _proactive_engine
    from app.ml.proactive_insights import ProactiveInsightsEngine
    _proactive_engine = ProactiveInsightsEngine()
    await _proactive_engine.start_monitoring()