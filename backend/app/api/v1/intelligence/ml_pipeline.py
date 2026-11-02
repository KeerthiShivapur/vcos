"""
ML Pipeline API Endpoints for VCOS Intelligence Layer.

Provides REST API for:
- Feature Store (entity/feature view management, online/offline serving)
- Model Registry (model versioning, stage management, deployments)
- Inference Service (multi-backend inference, streaming, batch)
- Text-to-SQL / Semantic Layer (natural language to SQL, business metrics)
- Proactive Insights (anomaly detection, trend analysis, alerting)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.ml.feature_store import (
    FeatureStore,
    Entity,
    Feature,
    FeatureView,
    ValueType,
    get_feature_store,
)
from app.ml.model_registry import (
    ModelRegistry,
    ModelStage,
    ModelSignature,
    ModelArtifact,
    get_model_registry,
)
from app.ml.inference_service import (
    InferenceService,
    InferenceBackend,
    InferenceRequest,
    get_inference_service,
)
from app.ml.text_to_sql import (
    TextToSQLService,
    TextToSQLRequest,
    TextToSQLResponse,
    SQLDialect,
    TableSchema,
    ColumnSchema,
    BusinessMetric,
    SemanticModel,
    get_text_to_sql_service,
)
from app.ml.proactive_insights import (
    ProactiveInsightsEngine,
    TimeSeriesMetric,
    DataPoint,
    InsightType,
    InsightSeverity,
    AnomalyMethod,
    AlertChannel,
    AlertRule,
    get_proactive_engine,
)
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence/ml", tags=["ML Pipeline"])


# ==================== Feature Store Models ====================

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


class MaterializeRequest(BaseModel):
    feature_view: str
    start_time: str
    end_time: str
    batch_size: int = 1000


# ==================== Model Registry Models ====================

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
    version: int
    stage: str


class CreateDeploymentRequest(BaseModel):
    model_name: str
    model_version: int
    endpoint_name: str
    endpoint_url: str
    replicas: int = 1
    resources: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    health_check_url: str = ""


# ==================== Inference Service Models ====================

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


# ==================== Text-to-SQL Models ====================

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


class SemanticModelRequest(BaseModel):
    name: str
    description: str
    tables: List[Dict[str, Any]]
    metrics: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]] = []


class MetricQueryRequest(BaseModel):
    model_name: str
    metric_name: str
    dimensions: List[str] = []
    filters: Dict[str, Any] = {}
    time_range: Optional[List[str]] = None
    limit: int = 1000


# ==================== Proactive Insights Models ====================

class RegisterMetricRequest(BaseModel):
    name: str
    data: List[Dict[str, Any]]
    frequency: str = "1h"
    thresholds: Dict[str, float] = {}


class UpdateMetricRequest(BaseModel):
    value: float
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = {}


class AlertRuleRequest(BaseModel):
    id: str
    name: str
    metric_patterns: List[str]
    severity_threshold: str
    channels: List[str]
    recipients: Dict[str, List[str]]
    cooldown_minutes: int = 60
    enabled: bool = True
    metadata: Dict[str, Any] = {}


# ==================== Feature Store Endpoints ====================

@router.post("/feature-store/entities")
async def create_entity(
    request: EntityRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Register a new entity in the feature store."""
    store = get_feature_store()
    await store.initialize()
    
    entity = Entity(
        name=request.name,
        join_keys=request.join_keys,
        description=request.description,
        value_type=ValueType(request.value_type),
        tags=request.tags,
    )
    store.apply_entity(entity)
    return {"success": True, "entity": entity.name}


@router.get("/feature-store/entities")
async def list_entities(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all entities in the feature store."""
    store = get_feature_store()
    await store.initialize()
    entities = store.list_entities()
    return {"entities": [
        {"name": e.name, "join_keys": e.join_keys, "description": e.description, "value_type": e.value_type.value}
        for e in entities
    ]}


@router.post("/feature-store/feature-views")
async def create_feature_view(
    request: FeatureViewRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Register a new feature view in the feature store."""
    store = get_feature_store()
    await store.initialize()
    
    features = [Feature(name=f.name, dtype=ValueType(f.dtype), description=f.description, tags=f.tags) for f in request.features]
    fv = FeatureView(
        name=request.name,
        entities=request.entities,
        features=features,
        ttl=datetime.timedelta(days=request.ttl_days),
        batch_source=request.batch_source,
        stream_source=request.stream_source,
        online=request.online,
        description=request.description,
        tags=request.tags,
    )
    store.apply_feature_view(fv)
    return {"success": True, "feature_view": fv.name}


@router.get("/feature-store/feature-views")
async def list_feature_views(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all feature views."""
    store = get_feature_store()
    await store.initialize()
    fvs = store.list_feature_views()
    return {"feature_views": [
        {
            "name": fv.name,
            "entities": fv.entities,
            "features": [{"name": f.name, "dtype": f.dtype.value} for f in fv.features],
            "ttl_days": fv.ttl.days,
            "online": fv.online,
        }
        for fv in fvs
    ]}


@router.post("/feature-store/online/write")
async def online_write(
    request: OnlineWriteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Write features to online store."""
    store = get_feature_store()
    await store.initialize()
    
    timestamp = datetime.fromisoformat(request.event_timestamp) if request.event_timestamp else datetime.utcnow()
    await store.online_write(request.feature_view, request.entity_id, request.features, timestamp)
    return {"success": True}


@router.post("/feature-store/online/read")
async def online_read(
    request: OnlineReadRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Read features from online store."""
    store = get_feature_store()
    await store.initialize()
    
    results = await store.online_read(request.feature_view, request.entity_ids)
    return {
        "feature_view": request.feature_view,
        "results": [
            {"entity_id": eid, "features": features}
            for eid, features in zip(request.entity_ids, results)
        ],
    }


@router.post("/feature-store/online/entity/{entity_id}")
async def get_entity_features(
    entity_id: str,
    feature_views: Optional[List[str]] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get all online features for an entity."""
    store = get_feature_store()
    await store.initialize()
    
    results = await store.get_online_features(entity_id, feature_views)
    return {"entity_id": entity_id, "features": results}


@router.post("/feature-store/offline/write")
async def offline_write(
    request: BatchWriteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Write batch features to offline store."""
    store = get_feature_store()
    await store.initialize()
    await store.write_batch(request.feature_view, request.data)
    return {"success": True, "rows_written": len(request.data)}


@router.post("/feature-store/offline/training-data")
async def get_training_data(
    request: TrainingDataRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get training data with point-in-time correctness."""
    store = get_feature_store()
    await store.initialize()
    
    start_time = datetime.fromisoformat(request.start_time)
    end_time = datetime.fromisoformat(request.end_time)
    
    data = await store.get_training_data(request.entity_ids, request.feature_views, start_time, end_time)
    return {"training_data": data}


@router.post("/feature-store/materialize")
async def materialize_features(
    request: MaterializeRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Materialize features from offline to online store."""
    store = get_feature_store()
    await store.initialize()
    
    start_time = datetime.fromisoformat(request.start_time)
    end_time = datetime.fromisoformat(request.end_time)
    
    await store.materialize(request.feature_view, start_time, end_time, request.batch_size)
    return {"success": True, "message": f"Materialized {request.feature_view}"}


# ==================== Model Registry Endpoints ====================

@router.post("/model-registry/models")
async def create_model(
    request: CreateModelRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Create a new registered model."""
    registry = get_model_registry()
    await registry.initialize()
    
    model = await registry.create_model(request.name, request.description, request.tags)
    return {"success": True, "model": model.name}


@router.get("/model-registry/models")
async def list_models(
    tags: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all registered models."""
    registry = get_model_registry()
    await registry.initialize()
    
    filter_tags = {}
    if tags:
        import json
        filter_tags = json.loads(tags)
    
    models = await registry.list_models(filter_tags)
    return {"models": [
        {
            "name": m.name,
            "description": m.description,
            "tags": m.tags,
            "latest_version": m.latest_version,
            "production_version": m.production_version,
            "staging_version": m.staging_version,
        }
        for m in models
    ]}


@router.get("/model-registry/models/{name}")
async def get_model(
    name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get model details with all versions."""
    registry = get_model_registry()
    await registry.initialize()
    
    model = await registry.get_model(name)
    if not model:
        raise HTTPException(404, "Model not found")
    
    return {
        "name": model.name,
        "description": model.description,
        "tags": model.tags,
        "latest_version": model.latest_version,
        "production_version": model.production_version,
        "staging_version": model.staging_version,
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
    }


@router.post("/model-registry/models/{name}/versions")
async def register_model_version(
    name: str,
    request: RegisterModelRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Register a new model version."""
    registry = get_model_registry()
    await registry.initialize()
    
    signature = None
    if request.signature:
        signature = ModelSignature(**request.signature)
    
    version = await registry.register_model(
        name=name,
        run_id=request.run_id,
        experiment_id=request.experiment_id,
        source=request.source,
        version=request.version,
        description=request.description,
        tags=request.tags,
        params=request.params,
        metrics=request.metrics,
        signature=signature,
        parent_version=request.parent_version,
        dataset_version=request.dataset_version,
        created_by=request.created_by,
    )
    
    return {"success": True, "version": version.version}


@router.get("/model-registry/models/{name}/versions")
async def list_model_versions(
    name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all versions of a model."""
    registry = get_model_registry()
    await registry.initialize()
    
    versions = await registry.list_versions(name)
    return {"versions": [
        {
            "version": v.version,
            "stage": v.stage.value,
            "status": v.status.value,
            "run_id": v.run_id,
            "metrics": v.metrics,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]}


@router.get("/model-registry/models/{name}/versions/{version}")
async def get_model_version(
    name: str,
    version: int,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get specific model version details."""
    registry = get_model_registry()
    await registry.initialize()
    
    version_obj = await registry.get_version(name, version)
    if not version_obj:
        raise HTTPException(404, "Model version not found")
    
    return {
        "name": version_obj.name,
        "version": version_obj.version,
        "stage": version_obj.stage.value,
        "status": version_obj.status.value,
        "run_id": version_obj.run_id,
        "experiment_id": version_obj.experiment_id,
        "source": version_obj.source,
        "artifacts": [
            {"path": a.path, "type": a.artifact_type, "size_bytes": a.size_bytes}
            for a in version_obj.artifacts
        ],
        "signature": version_obj.signature.__dict__ if version_obj.signature else None,
        "description": version_obj.description,
        "tags": version_obj.tags,
        "params": version_obj.params,
        "metrics": version_obj.metrics,
        "created_at": version_obj.created_at.isoformat(),
    }


@router.post("/model-registry/models/{name}/versions/{version}/stage")
async def transition_stage(
    name: str,
    version: int,
    request: TransitionStageRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Transition model version to a new stage."""
    registry = get_model_registry()
    await registry.initialize()
    
    stage = ModelStage(request.stage)
    await registry.transition_stage(name, version, stage)
    return {"success": True, "model": name, "version": version, "stage": stage.value}


@router.post("/model-registry/models/{name}/versions/{version}/artifacts")
async def add_model_artifacts(
    name: str,
    version: int,
    artifacts: List[Dict[str, Any]],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Add artifacts to a model version."""
    registry = get_model_registry()
    await registry.initialize()
    
    artifact_objs = [ModelArtifact(**a) for a in artifacts]
    await registry.add_artifacts(name, version, artifact_objs)
    return {"success": True}


@router.post("/model-registry/models/{name}/versions/{version}/signature")
async def set_model_signature(
    name: str,
    version: int,
    signature: Dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Set model input/output signature."""
    registry = get_model_registry()
    await registry.initialize()
    
    sig = ModelSignature(**signature)
    await registry.set_signature(name, version, sig)
    return {"success": True}


@router.post("/model-registry/deployments")
async def create_deployment(
    request: CreateDeploymentRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Create a model deployment."""
    registry = get_model_registry()
    await registry.initialize()
    
    deployment = await registry.create_deployment(
        model_name=request.model_name,
        model_version=request.model_version,
        endpoint_name=request.endpoint_name,
        endpoint_url=request.endpoint_url,
        replicas=request.replicas,
        resources=request.resources,
        config=request.config,
        health_check_url=request.health_check_url,
    )
    
    return {
        "success": True,
        "deployment_id": deployment.id,
        "endpoint": deployment.endpoint_url,
    }


@router.get("/model-registry/deployments")
async def list_deployments(
    model_name: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List model deployments."""
    registry = get_model_registry()
    await registry.initialize()
    
    deployments = await registry.list_deployments(model_name)
    return {"deployments": [
        {
            "id": d.id,
            "model_name": d.model_name,
            "model_version": d.model_version,
            "endpoint_name": d.endpoint_name,
            "endpoint_url": d.endpoint_url,
            "status": d.status,
            "replicas": d.replicas,
            "created_at": d.created_at.isoformat(),
        }
        for d in deployments
    ]}


@router.get("/model-registry/deployments/{deployment_id}")
async def get_deployment(
    deployment_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get deployment details."""
    registry = get_model_registry()
    await registry.initialize()
    
    deployment = await registry.get_deployment(deployment_id)
    if not deployment:
        raise HTTPException(404, "Deployment not found")
    
    return {
        "id": deployment.id,
        "model_name": deployment.model_name,
        "model_version": deployment.model_version,
        "endpoint_name": deployment.endpoint_name,
        "endpoint_url": deployment.endpoint_url,
        "status": deployment.status,
        "replicas": deployment.replicas,
        "resources": deployment.resources,
        "config": deployment.config,
        "metrics": deployment.metrics,
        "created_at": deployment.created_at.isoformat(),
    }


@router.post("/model-registry/search")
async def search_models(
    query: str = "",
    tags: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Search models by query, tags, and stage."""
    registry = get_model_registry()
    await registry.initialize()
    
    filter_tags = {}
    if tags:
        import json
        filter_tags = json.loads(tags)
    
    stage_enum = ModelStage(stage) if stage else None
    
    models = await registry.search_models(query, filter_tags, stage_enum)
    return {"models": [
        {
            "name": m.name,
            "description": m.description,
            "latest_version": m.latest_version,
            "production_version": m.production_version,
        }
        for m in models
    ]}


# ==================== Inference Service Endpoints ====================

@router.post("/inference/load")
async def load_model(
    request: LoadModelRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Load a model into the inference service."""
    service = get_inference_service()
    await service.initialize()
    
    backend = InferenceBackend(request.backend) if request.backend else None
    instance = await service.load_model(
        model_name=request.model_name,
        version=request.version,
        backend=backend,
        endpoint=request.endpoint,
    )
    
    return {
        "success": True,
        "instance_id": instance.id,
        "model_name": instance.model_name,
        "model_version": instance.model_version,
        "backend": instance.backend.value,
        "endpoint": instance.endpoint,
    }


@router.post("/inference/unload")
async def unload_model(
    model_name: str,
    version: int,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Unload a model from the inference service."""
    service = get_inference_service()
    await service.initialize()
    await service.unload_model(model_name, version)
    return {"success": True}


@router.post("/inference/predict")
async def predict(
    request: InferenceRequestModel,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Run inference on a model."""
    service = get_inference_service()
    await service.initialize()
    
    response = await service.infer(
        model_name=request.model_name,
        inputs=request.inputs,
        version=request.version,
        parameters=request.parameters,
        stream=request.stream,
        priority=request.priority,
        timeout=request.timeout,
    )
    
    return {
        "id": response.id,
        "request_id": response.request_id,
        "model_name": response.model_name,
        "model_version": response.model_version,
        "outputs": response.outputs,
        "status": response.status.value,
        "latency_ms": response.latency_ms,
        "tokens_used": response.tokens_used,
        "error": response.error,
    }


@router.post("/inference/stream")
async def stream_predict(
    request: InferenceRequestModel,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Stream inference results."""
    service = get_inference_service()
    await service.initialize()
    
    from fastapi.responses import StreamingResponse
    import json
    
    async def generate():
        async for chunk in service.stream_infer(
            model_name=request.model_name,
            inputs=request.inputs,
            version=request.version,
            parameters=request.parameters,
            timeout=request.timeout,
        ):
            yield f"data: {json.dumps({
                'id': chunk.id,
                'request_id': chunk.request_id,
                'model_name': chunk.model_name,
                'model_version': chunk.model_version,
                'outputs': chunk.outputs,
                'status': chunk.status.value,
                'latency_ms': chunk.latency_ms,
                'error': chunk.error,
            })}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/inference/batch")
async def batch_predict(
    request: BatchInferenceRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Run batch inference on a model."""
    service = get_inference_service()
    await service.initialize()
    
    results = await service.batch_infer(
        model_name=request.model_name,
        requests=request.requests,
        version=request.version,
    )
    
    return {
        "results": [
            {
                "id": r.id,
                "request_id": r.request_id,
                "model_name": r.model_name,
                "model_version": r.model_version,
                "outputs": r.outputs,
                "status": r.status.value,
                "latency_ms": r.latency_ms,
                "tokens_used": r.tokens_used,
                "error": r.error,
            }
            for r in results
        ],
    }


@router.get("/inference/health")
async def inference_health(
    model_name: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Check inference service health."""
    service = get_inference_service()
    await service.initialize()
    
    health = await service.health_check(model_name)
    return health


@router.get("/inference/models")
async def list_loaded_models(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all loaded models."""
    service = get_inference_service()
    await service.initialize()
    
    models = service.list_loaded_models()
    return {"models": [
        {
            "id": m.id,
            "model_name": m.model_name,
            "model_version": m.model_version,
            "backend": m.backend.value,
            "endpoint": m.endpoint,
            "status": m.status,
            "loaded_at": m.loaded_at.isoformat(),
        }
        for m in models
    ]}


# ==================== Text-to-SQL Endpoints ====================

@router.post("/text-to-sql/generate")
async def generate_sql(
    request: TextToSQLRequestModel,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Generate SQL from natural language."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    req = TextToSQLRequest(
        question=request.question,
        context=request.context,
        schema=request.schema,
        dialect=SQLDialect(request.dialect),
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        include_explanation=request.include_explanation,
        include_lineage=request.include_lineage,
    )
    
    response = await service.generate_sql(req)
    
    return {
        "sql": response.sql,
        "dialect": response.dialect.value,
        "explanation": response.explanation,
        "confidence": response.confidence,
        "tables_used": response.tables_used,
        "columns_used": response.columns_used,
        "lineage": response.lineage,
        "warnings": response.warnings,
        "execution_plan": response.execution_plan,
        "estimated_cost": response.estimated_cost,
    }


@router.post("/text-to-sql/validate")
async def validate_sql(
    request: ValidateSQLRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Validate SQL query."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    result = await service.validate_sql(request.sql, SQLDialect(request.dialect))
    
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "tables_referenced": result.tables_referenced,
        "columns_referenced": result.columns_referenced,
        "estimated_rows": result.estimated_rows,
        "estimated_cost": result.estimated_cost,
        "complexity_score": result.complexity_score,
    }


@router.post("/text-to-sql/explain")
async def explain_query(
    sql: str = Body(...),
    dialect: str = Body("postgresql"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Explain SQL query in natural language."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    explanation = await service.explain_query(sql, SQLDialect(dialect))
    return {"explanation": explanation}


@router.post("/text-to-sql/lineage")
async def get_lineage(
    sql: str = Body(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Get data lineage for query."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    lineage = await service.get_lineage(sql)
    return lineage


@router.post("/text-to-sql/transpile")
async def transpile_sql(
    sql: str = Body(...),
    target_dialect: str = Body(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Transpile SQL to another dialect."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    transpiled = await service.transpile_sql(sql, SQLDialect(target_dialect))
    return {"sql": transpiled, "target_dialect": target_dialect}


@router.post("/text-to-sql/semantic-models")
async def register_semantic_model(
    request: SemanticModelRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Register a semantic model for business metrics."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    tables = [TableSchema(**t) for t in request.tables]
    metrics = [BusinessMetric(**m) for m in request.metrics]
    relationships = request.relationships
    
    model = SemanticModel(
        name=request.name,
        description=request.description,
        tables=tables,
        metrics=metrics,
        relationships=relationships,
    )
    
    service.register_semantic_model(model)
    return {"success": True, "model": model.name}


@router.get("/text-to-sql/semantic-models")
async def list_semantic_models(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all registered semantic models."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    return {"models": service.semantic_layer.list_models()}


@router.get("/text-to-sql/semantic-models/{model_name}/metrics")
async def list_semantic_metrics(
    model_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List available metrics for a semantic model."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    metrics = service.semantic_layer.get_available_metrics(model_name)
    return {"model": model_name, "metrics": metrics}


@router.post("/text-to-sql/semantic-models/{model_name}/metrics/{metric_name}/query")
async def get_metric_query(
    model_name: str,
    metric_name: str,
    request: MetricQueryRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Get executable SQL for a semantic metric."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    time_range = None
    if request.time_range:
        time_range = (
            datetime.fromisoformat(request.time_range[0]),
            datetime.fromisoformat(request.time_range[1]),
        )
    
    sql = service.get_semantic_metric(
        model_name=model_name,
        metric_name=metric_name,
        dimensions=request.dimensions,
        filters=request.filters,
        time_range=time_range,
        limit=request.limit,
    )
    
    return {"sql": sql}


@router.post("/text-to-sql/execute")
async def execute_sql(
    sql: str = Body(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:predict")),
):
    """Execute SQL query and return results."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    results = await service.execute_query(sql)
    return {"results": results, "row_count": len(results)}


@router.get("/text-to-sql/tables")
async def list_tables(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List available tables in the schema."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    return {"tables": service.list_tables()}


@router.get("/text-to-sql/tables/{table_name}")
async def get_table_schema(
    table_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get schema for a specific table."""
    service = get_text_to_sql_service()
    await service.initialize()
    
    table = service.get_table_schema(table_name)
    if not table:
        raise HTTPException(404, "Table not found")
    
    return {
        "name": table.name,
        "columns": [
            {
                "name": c.name,
                "type": c.type,
                "nullable": c.nullable,
                "default": c.default,
                "description": c.description,
                "is_primary_key": c.is_primary_key,
                "is_foreign_key": c.is_foreign_key,
            }
            for c in table.columns
        ],
        "primary_key": table.primary_key,
        "foreign_keys": table.foreign_keys,
    }


# ==================== Proactive Insights Endpoints ====================

@router.post("/proactive/metrics")
async def register_metric(
    request: RegisterMetricRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Register a metric for proactive monitoring."""
    engine = get_proactive_engine()
    
    data_points = [DataPoint(
        timestamp=datetime.fromisoformat(d["timestamp"]),
        value=float(d["value"]),
        metadata=d.get("metadata", {}),
    ) for d in request.data]
    
    engine.register_metric(request.name, data_points, request.frequency, request.thresholds)
    return {"success": True, "metric": request.name, "data_points": len(data_points)}


@router.post("/proactive/metrics/{metric_name}/update")
async def update_metric(
    metric_name: str,
    request: UpdateMetricRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Update a metric with a new data point."""
    engine = get_proactive_engine()
    
    timestamp = datetime.fromisoformat(request.timestamp) if request.timestamp else datetime.utcnow()
    engine.update_metric(metric_name, request.value, timestamp, request.metadata)
    return {"success": True}


@router.get("/proactive/metrics")
async def list_metrics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all registered metrics."""
    engine = get_proactive_engine()
    return {"metrics": engine.list_metrics()}


@router.get("/proactive/insights")
async def get_insights(
    severity: Optional[str] = Query(None),
    metric: Optional[str] = Query(None),
    limit: int = 100,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get generated insights."""
    engine = get_proactive_engine()
    
    sev = InsightSeverity(severity) if severity else None
    insights = engine.get_insights(severity=sev, metric=metric, limit=limit)
    
    return {"insights": [
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
    ]}


@router.get("/proactive/anomalies")
async def get_anomalies(
    metric: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = 100,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get detected anomalies."""
    engine = get_proactive_engine()
    
    sev = InsightSeverity(severity) if severity else None
    anomalies = engine.get_anomalies(metric=metric, severity=sev, limit=limit)
    
    return {"anomalies": [
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
    ]}


@router.get("/proactive/trends")
async def get_trend_changes(
    metric: Optional[str] = Query(None),
    limit: int = 100,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get detected trend changes."""
    engine = get_proactive_engine()
    
    trends = engine.get_trend_changes(metric=metric, limit=limit)
    return {"trend_changes": [
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
    ]}


@router.post("/proactive/alert-rules")
async def create_alert_rule(
    request: AlertRuleRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Create an alert routing rule."""
    engine = get_proactive_engine()
    
    rule = AlertRule(
        id=request.id,
        name=request.name,
        metric_patterns=request.metric_patterns,
        severity_threshold=InsightSeverity(request.severity_threshold),
        channels=[AlertChannel(c) for c in request.channels],
        recipients={AlertChannel(k): v for k, v in request.recipients.items()},
        cooldown_minutes=request.cooldown_minutes,
        enabled=request.enabled,
        metadata=request.metadata,
    )
    
    engine.alert_manager.add_rule(rule)
    return {"success": True, "rule_id": rule.id}


@router.get("/proactive/alert-rules")
async def list_alert_rules(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """List all alert rules."""
    engine = get_proactive_engine()
    return {"rules": [
        {
            "id": r.id,
            "name": r.name,
            "metric_patterns": r.metric_patterns,
            "severity_threshold": r.severity_threshold.value,
            "channels": [c.value for c in r.channels],
            "recipients": {c.value: v for c, v in r.recipients.items()},
            "cooldown_minutes": r.cooldown_minutes,
            "enabled": r.enabled,
        }
        for r in engine.alert_manager.get_rules()
    ]}


@router.delete("/proactive/alert-rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Delete an alert rule."""
    engine = get_proactive_engine()
    engine.alert_manager.remove_rule(rule_id)
    return {"success": True}


@router.post("/proactive/monitoring/start")
async def start_monitoring(
    check_interval: int = 300,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Start continuous monitoring."""
    engine = get_proactive_engine()
    engine.check_interval = check_interval
    await engine.start_monitoring()
    return {"success": True, "message": "Monitoring started"}


@router.post("/proactive/monitoring/stop")
async def stop_monitoring(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Stop continuous monitoring."""
    engine = get_proactive_engine()
    await engine.stop_monitoring()
    return {"success": True, "message": "Monitoring stopped"}


@router.get("/proactive/status")
async def get_proactive_status(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:read")),
):
    """Get proactive insights engine status."""
    engine = get_proactive_engine()
    return engine.get_status()


@router.post("/proactive/insights/{insight_id}/acknowledge")
async def acknowledge_insight(
    insight_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Acknowledge an insight."""
    engine = get_proactive_engine()
    engine.acknowledge_insight(insight_id, user.id)
    return {"success": True}


@router.post("/proactive/anomalies/{anomaly_id}/acknowledge")
async def acknowledge_anomaly(
    anomaly_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ml:write")),
):
    """Acknowledge an anomaly."""
    engine = get_proactive_engine()
    engine.acknowledge_anomaly(anomaly_id, user.id)
    return {"success": True}