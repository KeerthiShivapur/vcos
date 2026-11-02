"""ML Pipeline API Endpoints - Forecasting and Anomaly Detection."""

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.intelligence.ml_pipeline import (
    MLPipeline,
    MLModel,
    MLPrediction,
    TimeSeriesPoint,
    ForecastResult,
    AnomalyResult,
)
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service


async def get_current_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current organization from user."""
    org = await db.get(Organization, user.organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")
    return org


class RequireMLPermission:
    """Dependency to require a specific ML permission."""
    
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        codes = await permission_service.user_permission_codes(db, user.id, user.organization_id)
        if self.permission not in codes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.permission}",
            )
        return user


def require_ml_permission(permission: str) -> RequireMLPermission:
    return RequireMLPermission(permission)


router = APIRouter(prefix="/ml", tags=["ML Pipeline"])


@router.post("/models/forecast", response_model=dict)
async def train_forecaster(
    name: str,
    data: list[dict],
    algorithm: str = "prophet",
    config: Optional[dict] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:train")),
    db: AsyncSession = Depends(get_db),
):
    """Train a forecasting model."""
    ts_data = [
        TimeSeriesPoint(
            timestamp=datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")),
            value=float(d["value"]),
            metadata=d.get("metadata", {}),
        )
        for d in data
    ]
    
    if len(ts_data) < 2:
        raise HTTPException(400, "Need at least 2 data points")
    
    pipeline = MLPipeline()
    model = await pipeline.train_forecaster(
        db=db,
        organization_id=org.id,
        name=name,
        data=ts_data,
        algorithm=algorithm,
        config=config,
    )
    
    return {
        "id": model.id,
        "name": model.name,
        "model_type": model.model_type,
        "algorithm": model.algorithm,
        "status": model.status,
        "metrics": json.loads(model.metrics) if model.metrics else {},
    }


@router.post("/models/anomaly", response_model=dict)
async def train_anomaly_detector(
    name: str,
    data: list[float],
    algorithm: str = "isolation_forest",
    config: Optional[dict] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:train")),
    db: AsyncSession = Depends(get_db),
):
    """Train an anomaly detection model."""
    if len(data) < 10:
        raise HTTPException(400, "Need at least 10 data points")
    
    pipeline = MLPipeline()
    model = await pipeline.train_anomaly_detector(
        db=db,
        organization_id=org.id,
        name=name,
        data=data,
        algorithm=algorithm,
        config=config,
    )
    
    return {
        "id": model.id,
        "name": model.name,
        "model_type": model.model_type,
        "algorithm": model.algorithm,
        "status": model.status,
        "metrics": json.loads(model.metrics) if model.metrics else {},
    }


@router.get("/models", response_model=list[dict])
async def list_models(
    model_type: Optional[str] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:read")),
    db: AsyncSession = Depends(get_db),
):
    """List ML models."""
    query = select(MLModel).where(MLModel.organization_id == org.id)
    
    if model_type:
        query = query.where(MLModel.model_type == model_type)
    if status:
        query = query.where(MLModel.status == status)
    
    query = query.order_by(MLModel.created_at.desc())
    
    result = await db.execute(query)
    models = result.scalars().all()
    
    return [
        {
            "id": m.id,
            "name": m.name,
            "model_type": m.model_type,
            "algorithm": m.algorithm,
            "version": m.version,
            "status": m.status,
            "metrics": json.loads(m.metrics) if m.metrics else {},
            "created_at": m.created_at,
            "trained_at": m.trained_at,
        }
        for m in models
    ]


@router.get("/models/{model_id}", response_model=dict)
async def get_model(
    model_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get ML model details."""
    model = await db.get(MLModel, model_id)
    if not model or model.organization_id != org.id:
        raise HTTPException(404, "Model not found")
    
    return {
        "id": model.id,
        "name": model.name,
        "model_type": model.model_type,
        "algorithm": model.algorithm,
        "version": model.version,
        "config": json.loads(model.config) if model.config else {},
        "status": model.status,
        "metrics": json.loads(model.metrics) if model.metrics else {},
        "created_at": model.created_at,
        "trained_at": model.trained_at,
    }


@router.delete("/models/{model_id}", response_model=dict)
async def delete_model(
    model_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:train")),
    db: AsyncSession = Depends(get_db),
):
    """Delete an ML model."""
    model = await db.get(MLModel, model_id)
    if not model or model.organization_id != org.id:
        raise HTTPException(404, "Model not found")
    
    await db.delete(model)
    await db.commit()
    
    return {"success": True, "model_id": model_id}


@router.post("/models/{model_id}/forecast", response_model=dict)
async def generate_forecast(
    model_id: str,
    periods: int = 30,
    freq: str = "D",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:predict")),
    db: AsyncSession = Depends(get_db),
):
    """Generate forecast using trained model."""
    pipeline = MLPipeline()
    
    try:
        forecast = await pipeline.forecast(
            db=db,
            organization_id=org.id,
            model_id=model_id,
            periods=periods,
            freq=freq,
        )
        
        return {
            "model_id": model_id,
            "periods": periods,
            "freq": freq,
            "timestamps": [t.isoformat() for t in forecast.timestamps],
            "values": forecast.values,
            "lower_bound": forecast.lower_bound,
            "upper_bound": forecast.upper_bound,
            "model_name": forecast.model_name,
            "metrics": forecast.metrics,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/models/{model_id}/anomaly", response_model=dict)
async def detect_anomalies(
    model_id: str,
    data: list[float],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:predict")),
    db: AsyncSession = Depends(get_db),
):
    """Detect anomalies using trained model."""
    pipeline = MLPipeline()
    
    try:
        result = await pipeline.detect_anomalies(
            db=db,
            organization_id=org.id,
            model_id=model_id,
            data=data,
        )
        
        return {
            "model_id": model_id,
            "data_points": len(data),
            "timestamps": [t.isoformat() for t in result.timestamps],
            "values": result.values,
            "is_anomaly": result.is_anomaly,
            "scores": result.scores,
            "threshold": result.threshold,
            "anomaly_count": sum(result.is_anomaly),
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/predictions", response_model=list[dict])
async def list_predictions(
    model_id: Optional[str] = None,
    prediction_type: Optional[str] = None,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:read")),
    db: AsyncSession = Depends(get_db),
):
    """List ML predictions."""
    query = select(MLPrediction).where(MLPrediction.organization_id == org.id)
    
    if model_id:
        query = query.where(MLPrediction.model_id == model_id)
    if prediction_type:
        query = query.where(MLPrediction.prediction_type == prediction_type)
    
    query = query.order_by(MLPrediction.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    predictions = result.scalars().all()
    
    return [
        {
            "id": p.id,
            "model_id": p.model_id,
            "prediction_type": p.prediction_type,
            "input_data": json.loads(p.input_data) if p.input_data else {},
            "output_data": json.loads(p.output_data) if p.output_data else {},
            "created_at": p.created_at,
        }
        for p in predictions
    ]


@router.post("/quick/forecast", response_model=dict)
async def quick_forecast(
    data: list[dict],
    periods: int = 30,
    freq: str = "D",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:predict")),
):
    """Quick forecast without persisting model (for ad-hoc analysis)."""
    ts_data = [
        TimeSeriesPoint(
            timestamp=datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")),
            value=float(d["value"]),
            metadata=d.get("metadata", {}),
        )
        for d in data
    ]
    
    if len(ts_data) < 2:
        raise HTTPException(400, "Need at least 2 data points")
    
    pipeline = MLPipeline()
    fitted_model = pipeline.forecaster.fit(ts_data)
    forecast = pipeline.forecaster.predict(fitted_model, periods=periods, freq=freq)
    
    return {
        "periods": periods,
        "freq": freq,
        "timestamps": [t.isoformat() for t in forecast.timestamps],
        "values": forecast.values,
        "lower_bound": forecast.lower_bound,
        "upper_bound": forecast.upper_bound,
        "model_name": forecast.model_name,
        "metrics": forecast.metrics,
    }


@router.post("/quick/anomaly", response_model=dict)
async def quick_anomaly(
    data: list[float],
    contamination: float = 0.1,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_ml_permission("ml:predict")),
):
    """Quick anomaly detection without persisting model."""
    if len(data) < 10:
        raise HTTPException(400, "Need at least 10 data points")
    
    pipeline = MLPipeline()
    pipeline.anomaly_detector.contamination = contamination
    fitted_model = pipeline.anomaly_detector.fit(data)
    result = pipeline.anomaly_detector.predict(data)
    
    return {
        "data_points": len(data),
        "timestamps": [t.isoformat() for t in result.timestamps],
        "values": result.values,
        "is_anomaly": result.is_anomaly,
        "scores": result.scores,
        "threshold": result.threshold,
        "anomaly_count": sum(result.is_anomaly),
    }