"""ML Pipeline - Forecasting and Anomaly Detection.

Provides time series forecasting (Prophet/NeuralProphet) and 
anomaly detection (Isolation Forest) for business metrics.
"""

import json
import logging
import pickle
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import Base
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

logger = logging.getLogger(__name__)


@dataclass
class TimeSeriesPoint:
    """Single time series data point."""
    timestamp: datetime
    value: float
    metadata: dict = None


@dataclass
class ForecastResult:
    """Forecast prediction result."""
    timestamps: list[datetime]
    values: list[float]
    lower_bound: list[float]
    upper_bound: list[float]
    model_name: str
    metrics: dict


@dataclass
class AnomalyResult:
    """Anomaly detection result."""
    timestamps: list[datetime]
    values: list[float]
    is_anomaly: list[bool]
    scores: list[float]
    threshold: float


class MLModel(Base):
    """Stored ML model metadata."""
    __tablename__ = "ml_models"
    
    id = Column(PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(PG_UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(120), nullable=False)
    model_type = Column(String(40), nullable=False)  # forecasting, anomaly
    algorithm = Column(String(40), nullable=False)  # prophet, isolation_forest, etc.
    version = Column(Integer, default=1)
    config = Column(Text)  # JSON config
    metrics = Column(Text)  # JSON metrics
    model_data = Column(Text)  # Pickled model (base64)
    status = Column(String(24), default="training")  # training, ready, failed
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    trained_at = Column(DateTime(timezone=True))
    
    __table_args__ = (
        # Index defined in canonical model (app.models.ml_models)
        {"extend_existing": True},
    )


class MLPrediction(Base):
    """Stored predictions for audit/history."""
    __tablename__ = "ml_predictions"
    
    id = Column(PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id = Column(PG_UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False)
    model_id = Column(PG_UUID(as_uuid=False), ForeignKey("ml_models.id"), index=True, nullable=False)
    prediction_type = Column(String(40), nullable=False)  # forecast, anomaly
    input_data = Column(Text)  # JSON input
    output_data = Column(Text)  # JSON output
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    __table_args__ = (
        {"extend_existing": True},
    )


class Forecaster:
    """Time series forecaster using Prophet (with fallback)."""
    
    def __init__(self):
        self.settings = get_settings()
        self._prophet = None
        self._use_prophet = False
        self._init_prophet()
    
    def _init_prophet(self):
        """Try to import Prophet, fallback to linear regression."""
        try:
            from prophet import Prophet
            self._prophet = Prophet
            self._use_prophet = True
            logger.info("Prophet available for forecasting")
        except ImportError:
            logger.warning("Prophet not available, using linear regression fallback")
            self._use_prophet = False
    
    def fit(self, data: list[TimeSeriesPoint], **kwargs) -> Any:
        """Fit forecasting model."""
        if len(data) < 2:
            raise ValueError("Need at least 2 data points")
        
        df = pd.DataFrame([
            {"ds": p.timestamp, "y": p.value} 
            for p in data
        ])
        
        if self._use_prophet:
            model = self._prophet(
                yearly_seasonality=kwargs.get("yearly_seasonality", "auto"),
                weekly_seasonality=kwargs.get("weekly_seasonality", "auto"),
                daily_seasonality=kwargs.get("daily_seasonality", "auto"),
                seasonality_mode=kwargs.get("seasonality_mode", "additive"),
                changepoint_prior_scale=kwargs.get("changepoint_prior_scale", 0.05),
            )
            model.fit(df)
            return model
        else:
            # Linear regression fallback
            from sklearn.linear_model import LinearRegression
            X = np.arange(len(df)).reshape(-1, 1)
            y = df["y"].values
            model = LinearRegression()
            model.fit(X, y)
            return {"model": model, "df": df}
    
    def predict(
        self, 
        model: Any, 
        periods: int = 30, 
        freq: str = "D",
        **kwargs
    ) -> ForecastResult:
        """Generate forecast."""
        if self._use_prophet and hasattr(model, "make_future_dataframe"):
            future = model.make_future_dataframe(periods=periods, freq=freq)
            forecast = model.predict(future)
            
            # Get only future predictions
            future_forecast = forecast.tail(periods)
            
            return ForecastResult(
                timestamps=future_forecast["ds"].tolist(),
                values=future_forecast["yhat"].tolist(),
                lower_bound=future_forecast["yhat_lower"].tolist(),
                upper_bound=future_forecast["yhat_upper"].tolist(),
                model_name="prophet",
                metrics={},
            )
        else:
            # Linear regression fallback
            lr_model = model["model"]
            df = model["df"]
            last_idx = len(df) - 1
            
            future_X = np.arange(last_idx + 1, last_idx + 1 + periods).reshape(-1, 1)
            predictions = lr_model.predict(future_X)
            
            # Generate timestamps
            last_date = df["ds"].iloc[-1]
            if freq == "D":
                timestamps = [last_date + timedelta(days=i) for i in range(1, periods + 1)]
            elif freq == "W":
                timestamps = [last_date + timedelta(weeks=i) for i in range(1, periods + 1)]
            elif freq == "M":
                timestamps = [last_date + timedelta(days=30*i) for i in range(1, periods + 1)]
            else:
                timestamps = [last_date + timedelta(days=i) for i in range(1, periods + 1)]
            
            # Simple confidence intervals (residual std)
            residuals = df["y"].values - lr_model.predict(np.arange(len(df)).reshape(-1, 1))
            std = np.std(residuals)
            
            return ForecastResult(
                timestamps=timestamps,
                values=predictions.tolist(),
                lower_bound=(predictions - 1.96 * std).tolist(),
                upper_bound=(predictions + 1.96 * std).tolist(),
                model_name="linear_regression",
                metrics={"r2": lr_model.score(np.arange(len(df)).reshape(-1, 1), df["y"].values)},
            )


class AnomalyDetector:
    """Anomaly detector using Isolation Forest."""
    
    def __init__(self, contamination: float = 0.1):
        self.contamination = contamination
        self._model = None
    
    def fit(self, data: list[float]) -> Any:
        """Fit anomaly detection model."""
        from sklearn.ensemble import IsolationForest
        
        if len(data) < 10:
            raise ValueError("Need at least 10 data points for anomaly detection")
        
        X = np.array(data).reshape(-1, 1)
        
        self._model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
        self._model.fit(X)
        return self._model
    
    def predict(self, data: list[float]) -> AnomalyResult:
        """Detect anomalies."""
        if self._model is None:
            self.fit(data)
        
        X = np.array(data).reshape(-1, 1)
        scores = self._model.decision_function(X)
        predictions = self._model.predict(X)
        
        # Isolation Forest: -1 = anomaly, 1 = normal
        is_anomaly = predictions == -1
        
        # Normalize scores to 0-1 (higher = more anomalous)
        min_score, max_score = scores.min(), scores.max()
        if max_score > min_score:
            normalized_scores = 1 - (scores - min_score) / (max_score - min_score)
        else:
            normalized_scores = np.zeros_like(scores)
        
        # Generate timestamps
        timestamps = [datetime.utcnow() - timedelta(days=len(data)-i) for i in range(len(data))]
        
        return AnomalyResult(
            timestamps=timestamps,
            values=data,
            is_anomaly=is_anomaly.tolist(),
            scores=normalized_scores.tolist(),
            threshold=self.contamination,
        )


class MLPipeline:
    """Unified ML pipeline for forecasting and anomaly detection."""
    
    def __init__(self):
        self.settings = get_settings()
        self.forecaster = Forecaster()
        self.anomaly_detector = AnomalyDetector()
    
    async def train_forecaster(
        self,
        db: AsyncSession,
        organization_id: str,
        name: str,
        data: list[TimeSeriesPoint],
        algorithm: str = "prophet",
        config: Optional[dict] = None,
    ) -> MLModel:
        """Train and store a forecasting model."""
        model = MLModel(
            organization_id=organization_id,
            name=name,
            model_type="forecasting",
            algorithm=algorithm,
            config=json.dumps(config or {}),
            status="training",
        )
        db.add(model)
        await db.flush()
        
        try:
            fitted_model = self.forecaster.fit(data, **(config or {}))
            
            # Serialize model
            import base64
            model_bytes = pickle.dumps(fitted_model)
            model_data = base64.b64encode(model_bytes).decode()
            
            # Generate sample forecast for metrics
            forecast = self.forecaster.predict(fitted_model, periods=10)
            
            model.model_data = model_data
            model.metrics = json.dumps({
                "training_points": len(data),
                "forecast_periods": 10,
                "model_name": forecast.model_name,
                **forecast.metrics,
            })
            model.status = "ready"
            model.trained_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(model)
            
            logger.info(f"Trained forecasting model {model.id}: {name}")
            return model
            
        except Exception as e:
            model.status = "failed"
            model.metrics = json.dumps({"error": str(e)})
            await db.commit()
            logger.error(f"Forecasting model training failed: {e}")
            raise
    
    async def train_anomaly_detector(
        self,
        db: AsyncSession,
        organization_id: str,
        name: str,
        data: list[float],
        algorithm: str = "isolation_forest",
        config: Optional[dict] = None,
    ) -> MLModel:
        """Train and store an anomaly detection model."""
        model = MLModel(
            organization_id=organization_id,
            name=name,
            model_type="anomaly",
            algorithm=algorithm,
            config=json.dumps(config or {}),
            status="training",
        )
        db.add(model)
        await db.flush()
        
        try:
            fitted_model = self.anomaly_detector.fit(data)
            
            import base64
            model_bytes = pickle.dumps(fitted_model)
            model_data = base64.b64encode(model_bytes).decode()
            
            # Test on training data
            result = self.anomaly_detector.predict(data)
            anomaly_count = sum(result.is_anomaly)
            
            model.model_data = model_data
            model.metrics = json.dumps({
                "training_points": len(data),
                "anomalies_detected": anomaly_count,
                "contamination": self.anomaly_detector.contamination,
            })
            model.status = "ready"
            model.trained_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(model)
            
            logger.info(f"Trained anomaly model {model.id}: {name}")
            return model
            
        except Exception as e:
            model.status = "failed"
            model.metrics = json.dumps({"error": str(e)})
            await db.commit()
            logger.error(f"Anomaly model training failed: {e}")
            raise
    
    def load_model(self, model: MLModel) -> Any:
        """Load a stored model."""
        import base64
        model_bytes = base64.b64decode(model.model_data)
        return pickle.loads(model_bytes)
    
    async def forecast(
        self,
        db: AsyncSession,
        organization_id: str,
        model_id: str,
        periods: int = 30,
        freq: str = "D",
    ) -> ForecastResult:
        """Generate forecast using stored model."""
        model = await db.get(MLModel, model_id)
        if not model or model.organization_id != organization_id:
            raise ValueError("Model not found")
        
        if model.model_type != "forecasting":
            raise ValueError("Model is not a forecasting model")
        
        fitted_model = self.load_model(model)
        config = json.loads(model.config) if model.config else {}
        
        forecast = self.forecaster.predict(fitted_model, periods=periods, freq=freq, **config)
        
        # Store prediction
        prediction = MLPrediction(
            organization_id=organization_id,
            model_id=model_id,
            prediction_type="forecast",
            input_data=json.dumps({"periods": periods, "freq": freq}),
            output_data=json.dumps({
                "timestamps": [t.isoformat() for t in forecast.timestamps],
                "values": forecast.values,
                "lower_bound": forecast.lower_bound,
                "upper_bound": forecast.upper_bound,
            }),
        )
        db.add(prediction)
        await db.commit()
        
        return forecast
    
    async def detect_anomalies(
        self,
        db: AsyncSession,
        organization_id: str,
        model_id: str,
        data: list[float],
    ) -> AnomalyResult:
        """Detect anomalies using stored model."""
        model = await db.get(MLModel, model_id)
        if not model or model.organization_id != organization_id:
            raise ValueError("Model not found")
        
        if model.model_type != "anomaly":
            raise ValueError("Model is not an anomaly detection model")
        
        fitted_model = self.load_model(model)
        self.anomaly_detector._model = fitted_model
        
        result = self.anomaly_detector.predict(data)
        
        # Store prediction
        prediction = MLPrediction(
            organization_id=organization_id,
            model_id=model_id,
            prediction_type="anomaly",
            input_data=json.dumps({"data_points": len(data)}),
            output_data=json.dumps({
                "timestamps": [t.isoformat() for t in result.timestamps],
                "values": result.values,
                "is_anomaly": result.is_anomaly,
                "scores": result.scores,
            }),
        )
        db.add(prediction)
        await db.commit()
        
        return result


ml_pipeline = MLPipeline()