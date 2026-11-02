"""ML Pipeline for Forecasting and Anomaly Detection."""

import asyncio
import logging
import json
import pickle
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import numpy as np
import pandas as pd

# Optional ML imports
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    Prophet = None

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    IsolationForest = None
    StandardScaler = None

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    FORECASTING = "forecasting"
    ANOMALY_DETECTION = "anomaly_detection"
    CLASSIFICATION = "classification"
    REGRESSION = "regression"


class ForecastFrequency(str, Enum):
    HOURLY = "H"
    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"


@dataclass
class TimeSeriesData:
    """Time series data point."""
    timestamp: datetime
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastResult:
    """Forecast prediction result."""
    timestamp: datetime
    predicted_value: float
    lower_bound: float
    upper_bound: float
    confidence: float


@dataclass
class AnomalyResult:
    """Anomaly detection result."""
    timestamp: datetime
    value: float
    is_anomaly: bool
    anomaly_score: float
    expected_range: Tuple[float, float]


@dataclass
class ModelInfo:
    """Model metadata."""
    model_id: str
    model_type: ModelType
    name: str
    version: str
    created_at: datetime
    updated_at: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_trained: bool = False


class BaseModel:
    """Base class for ML models."""
    
    def __init__(self, model_id: str, name: str, model_type: ModelType):
        self.model_id = model_id
        self.name = name
        self.model_type = model_type
        self.model = None
        self.info = ModelInfo(
            model_id=model_id,
            model_type=model_type,
            name=name,
            version="1.0.0",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.is_trained = False
    
    async def train(self, data: List[TimeSeriesData], **kwargs) -> Dict[str, float]:
        """Train the model."""
        raise NotImplementedError
    
    async def predict(self, horizon: int = 30, **kwargs) -> List[Any]:
        """Make predictions."""
        raise NotImplementedError
    
    def save(self, path: str):
        """Save model to disk."""
        if JOBLIB_AVAILABLE and self.model:
            joblib.dump(self.model, path)
            # Save metadata separately
            meta_path = path.replace('.pkl', '_meta.json')
            with open(meta_path, 'w') as f:
                json.dump({
                    'model_id': self.info.model_id,
                    'model_type': self.info.model_type.value,
                    'name': self.info.name,
                    'version': self.info.version,
                    'created_at': self.info.created_at.isoformat(),
                    'updated_at': self.info.updated_at.isoformat(),
                    'metrics': self.info.metrics,
                    'parameters': self.info.parameters,
                    'is_trained': self.info.is_trained,
                }, f)
    
    @classmethod
    def load(cls, path: str):
        """Load model from disk."""
        if not JOBLIB_AVAILABLE:
            raise RuntimeError("joblib not available")
        
        model = joblib.load(path)
        meta_path = path.replace('.pkl', '_meta.json')
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        
        instance = cls(meta['model_id'], meta['name'], ModelType(meta['model_type']))
        instance.model = model
        instance.info = ModelInfo(
            model_id=meta['model_id'],
            model_type=ModelType(meta['model_type']),
            name=meta['name'],
            version=meta['version'],
            created_at=datetime.fromisoformat(meta['created_at']),
            updated_at=datetime.fromisoformat(meta['updated_at']),
            metrics=meta['metrics'],
            parameters=meta['parameters'],
            is_trained=meta['is_trained'],
        )
        instance.is_trained = meta['is_trained']
        return instance


class ProphetForecaster(BaseModel):
    """Prophet-based time series forecaster with fallback to simple forecasting."""
    
    def __init__(self, model_id: str, name: str = "Prophet Forecaster"):
        super().__init__(model_id, name, ModelType.FORECASTING)
        self.frequency = ForecastFrequency.DAILY
        self.seasonality_mode = "multiplicative"
        self.changepoint_prior_scale = 0.05
        self.use_fallback = False
        self.fallback_model = None
    
    async def train(
        self, 
        data: List[TimeSeriesData], 
        frequency: ForecastFrequency = ForecastFrequency.DAILY,
        **kwargs
    ) -> Dict[str, float]:
        """Train the Prophet model with fallback to simple forecasting."""
        if not PROPHET_AVAILABLE:
            raise RuntimeError("Prophet not installed. Install with: pip install prophet")
        
        if len(data) < 2:
            raise ValueError("Need at least 2 data points for training")
        
        self.frequency = frequency
        
        # Convert to Prophet format
        df = pd.DataFrame([
            {'ds': d.timestamp, 'y': d.value}
            for d in data
        ])
        
        # Try to train Prophet model
        prophet_success = False
        try:
            # Create and fit model
            self.model = Prophet(
                seasonality_mode=self.seasonality_mode,
                changepoint_prior_scale=self.changepoint_prior_scale,
                daily_seasonality=frequency in [ForecastFrequency.HOURLY, ForecastFrequency.DAILY],
                weekly_seasonality=frequency in [ForecastFrequency.DAILY, ForecastFrequency.WEEKLY],
                yearly_seasonality=frequency in [ForecastFrequency.DAILY, ForecastFrequency.WEEKLY, ForecastFrequency.MONTHLY],
            )
            
            # Add custom seasonality if needed
            if frequency == ForecastFrequency.HOURLY:
                self.model.add_seasonality(name='hourly', period=1/24, fourier_order=5)
            
            self.model.fit(df)
            prophet_success = True
        except Exception as e:
            logger.warning(f"Prophet training failed, using fallback: {e}")
            self.use_fallback = True
        
        if not prophet_success:
            # Fallback: Simple linear regression with seasonality
            await self._train_fallback(df)
        
        self.is_trained = True
        self.info.is_trained = True
        self.info.updated_at = datetime.utcnow()
        
        # Calculate training metrics
        if self.use_fallback:
            forecast_values = self._predict_fallback(df)
            mae = np.mean(np.abs(df['y'] - forecast_values))
            mape = np.mean(np.abs((df['y'] - forecast_values) / df['y'])) * 100
        else:
            forecast = self.model.predict(df)
            mae = np.mean(np.abs(df['y'] - forecast['yhat']))
            mape = np.mean(np.abs((df['y'] - forecast['yhat']) / df['y'])) * 100
        
        # Store training data for fallback predictions
        self.training_df = df.copy()
        
        self.info.metrics = {
            'mae': float(mae),
            'mape': float(mape),
            'train_size': len(data),
            'used_fallback': self.use_fallback,
        }
        
        return self.info.metrics
    
    async def _train_fallback(self, df: pd.DataFrame):
        """Train a simple fallback model (linear trend + seasonality)."""
        from sklearn.linear_model import LinearRegression
        
        # Create features: time index, hour, day of week, month
        df = df.copy()
        df['t'] = np.arange(len(df))
        df['hour'] = df['ds'].dt.hour
        df['dow'] = df['ds'].dt.dayofweek
        df['month'] = df['ds'].dt.month
        
        # Create cyclical features for seasonality
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['dow_sin'] = np.sin(2 * np.pi * df['dow'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['dow'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        
        # Features for regression
        feature_cols = ['t', 'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos', 'month_sin', 'month_cos']
        X = df[feature_cols].values
        y = df['y'].values
        
        # Fit linear regression
        self.fallback_model = LinearRegression()
        self.fallback_model.fit(X, y)
        
        # Store feature columns for prediction
        self.fallback_features = feature_cols
        
        logger.info("Fallback linear regression model trained successfully")
    
    def _predict_fallback(self, df: pd.DataFrame) -> np.ndarray:
        """Generate predictions using fallback model."""
        if self.fallback_model is None:
            # Simple moving average as last resort
            window = min(7, len(df))
            return df['y'].rolling(window=window, min_periods=1).mean().values
        
        # Create features
        df = df.copy()
        df['t'] = np.arange(len(df))
        df['hour'] = df['ds'].dt.hour
        df['dow'] = df['ds'].dt.dayofweek
        df['month'] = df['ds'].dt.month
        
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['dow_sin'] = np.sin(2 * np.pi * df['dow'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['dow'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        
        feature_cols = self.fallback_features
        X = df[feature_cols].values
        
        return self.fallback_model.predict(X)
    
    def _make_future_dataframe_fallback(self, horizon: int, include_history: bool) -> pd.DataFrame:
        """Create future dataframe for fallback predictions."""
        if not hasattr(self, 'training_df') or self.training_df is None:
            return pd.DataFrame()
        
        last_date = self.training_df['ds'].max()
        freq = self.frequency.value
        
        # Generate future dates
        future_dates = pd.date_range(
            start=last_date + pd.Timedelta(1, unit=freq),
            periods=horizon,
            freq=freq,
        )
        
        future_df = pd.DataFrame({'ds': future_dates})
        
        if include_history:
            return pd.concat([self.training_df[['ds']], future_df], ignore_index=True)
        
        return future_df
    
    async def predict(
        self, 
        horizon: int = 30,
        include_history: bool = False,
        **kwargs
    ) -> List[ForecastResult]:
        """Generate forecasts."""
        if not self.is_trained:
            raise RuntimeError("Model not trained")
        
        if self.use_fallback:
            # Use fallback prediction
            if not hasattr(self, 'training_df'):
                raise RuntimeError("Fallback model not properly trained")
            
            future_df = self._make_future_dataframe_fallback(horizon, include_history)
            if future_df.empty:
                return []
            
            predictions = self._predict_fallback(future_df)
            
            results = []
            for i, (_, row) in enumerate(future_df.iterrows()):
                pred = predictions[i] if i < len(predictions) else predictions[-1]
                # Simple confidence intervals based on training residuals
                std = 1.0  # Default
                results.append(ForecastResult(
                    timestamp=row['ds'],
                    predicted_value=pred,
                    lower_bound=pred - 1.96 * std,
                    upper_bound=pred + 1.96 * std,
                    confidence=0.8,
                ))
            
            return results
        
        # Use Prophet model
        future = self.model.make_future_dataframe(
            periods=horizon,
            freq=self.frequency.value,
            include_history=include_history,
        )
        
        forecast = self.model.predict(future)
        
        results = []
        for _, row in forecast.tail(horizon if not include_history else len(forecast)).iterrows():
            results.append(ForecastResult(
                timestamp=row['ds'],
                predicted_value=row['yhat'],
                lower_bound=row['yhat_lower'],
                upper_bound=row['yhat_upper'],
                confidence=0.8,
            ))
        
        return results
    
    async def detect_anomalies(
        self,
        data: List[TimeSeriesData],
        threshold: float = 0.05,
    ) -> List[AnomalyResult]:
        """Detect anomalies using prediction intervals."""
        if not self.is_trained:
            raise RuntimeError("Model not trained")
        
        df = pd.DataFrame([
            {'ds': d.timestamp, 'y': d.value}
            for d in data
        ])
        
        if self.use_fallback:
            predictions = self._predict_fallback(df)
            # Use simple threshold-based anomaly detection
            residuals = df['y'].values - predictions
            std = np.std(residuals)
            
            results = []
            for i, (_, actual_row) in enumerate(df.iterrows()):
                pred = predictions[i]
                is_anomaly = abs(actual_row['y'] - pred) > threshold * abs(pred) if pred != 0 else False
                score = abs(actual_row['y'] - pred) / (abs(pred) + 1e-6)
                
                results.append(AnomalyResult(
                    timestamp=actual_row['ds'],
                    value=actual_row['y'],
                    is_anomaly=is_anomaly,
                    anomaly_score=float(min(1.0, score)),
                    expected_range=(pred - 2 * np.std(df['y'].values - predictions), pred + 2 * np.std(df['y'].values - predictions)),
                ))
            
            return results
        
        # Use Prophet model
        forecast = self.model.predict(df)
        
        results = []
        for i, (_, actual_row) in enumerate(df.iterrows()):
            pred_row = forecast.iloc[i]
            
            is_anomaly = (
                actual_row['y'] < pred_row['yhat_lower'] or 
                actual_row['y'] > pred_row['yhat_upper']
            )
            
            if actual_row['y'] < pred_row['yhat_lower']:
                score = (pred_row['yhat_lower'] - actual_row['y']) / abs(pred_row['yhat'])
            elif actual_row['y'] > pred_row['yhat_upper']:
                score = (actual_row['y'] - pred_row['yhat_upper']) / abs(pred_row['yhat'])
            else:
                score = 0.0
            
            results.append(AnomalyResult(
                timestamp=actual_row['ds'],
                value=actual_row['y'],
                is_anomaly=is_anomaly,
                anomaly_score=float(score),
                expected_range=(pred_row['yhat_lower'], pred_row['yhat_upper']),
            ))
        
        return results


class IsolationForestDetector(BaseModel):
    """Isolation Forest anomaly detector."""
    
    def __init__(self, model_id: str, name: str = "Isolation Forest Detector"):
        super().__init__(model_id, name, ModelType.ANOMALY_DETECTION)
        self.contamination = 0.1
        self.n_estimators = 100
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
    
    async def train(
        self,
        data: List[TimeSeriesData],
        contamination: float = 0.1,
        n_estimators: int = 100,
        **kwargs
    ) -> Dict[str, float]:
        """Train the Isolation Forest model."""
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("scikit-learn not installed. Install with: pip install scikit-learn")
        
        if len(data) < 10:
            raise ValueError("Need at least 10 data points for training")
        
        self.contamination = contamination
        self.n_estimators = n_estimators
        
        # Prepare features (use value and time-based features)
        timestamps = np.array([d.timestamp.timestamp() for d in data])
        values = np.array([d.value for d in data])
        
        # Create feature matrix
        # Features: value, hour, day_of_week, month, rolling stats
        features = []
        for i, d in enumerate(data):
            feat = [
                d.value,
                d.timestamp.hour,
                d.timestamp.weekday(),
                d.timestamp.month,
            ]
            # Rolling statistics
            if i >= 5:
                window = values[max(0, i-5):i+1]
                feat.extend([np.mean(window), np.std(window), np.min(window), np.max(window)])
            else:
                feat.extend([d.value, 0, d.value, d.value])
            features.append(feat)
        
        X = np.array(features)
        X = self.scaler.fit_transform(X)
        
        # Train Isolation Forest
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=42,
        )
        self.model.fit(X)
        
        self.is_trained = True
        self.info.is_trained = True
        self.info.updated_at = datetime.utcnow()
        self.info.parameters = {
            'contamination': contamination,
            'n_estimators': n_estimators,
            'n_features': X.shape[1],
        }
        
        # Calculate training anomaly scores
        scores = self.model.decision_function(X)
        predictions = self.model.predict(X)
        
        self.info.metrics = {
            'anomaly_ratio': float(np.mean(predictions == -1)),
            'mean_score': float(np.mean(scores)),
            'train_size': len(data),
        }
        
        return self.info.metrics
    
    async def predict(self, data: List[TimeSeriesData], **kwargs) -> List[AnomalyResult]:
        """Detect anomalies in new data."""
        if not self.is_trained or not self.model:
            raise RuntimeError("Model not trained")
        
        # Prepare features (same as training)
        values = np.array([d.value for d in data])
        features = []
        
        for i, d in enumerate(data):
            feat = [
                d.value,
                d.timestamp.hour,
                d.timestamp.weekday(),
                d.timestamp.month,
            ]
            if i >= 5:
                window = values[max(0, i-5):i+1]
                feat.extend([np.mean(window), np.std(window), np.min(window), np.max(window)])
            else:
                feat.extend([d.value, 0, d.value, d.value])
            features.append(feat)
        
        X = np.array(features)
        X = self.scaler.transform(X)
        
        # Get predictions
        predictions = self.model.predict(X)
        scores = self.model.decision_function(X)
        
        results = []
        for i, d in enumerate(data):
            is_anomaly = predictions[i] == -1
            # Normalize score to 0-1 range
            anomaly_score = float((0.5 - scores[i]) / 1.0)  # Rough normalization
            anomaly_score = max(0, min(1, anomaly_score))
            
            # Expected range based on training data statistics
            expected_range = (
                float(np.mean(values) - 2 * np.std(values)),
                float(np.mean(values) + 2 * np.std(values)),
            )
            
            results.append(AnomalyResult(
                timestamp=d.timestamp,
                value=d.value,
                is_anomaly=is_anomaly,
                anomaly_score=anomaly_score,
                expected_range=expected_range,
            ))
        
        return results


class MLPipeline:
    """Main ML Pipeline orchestrator."""
    
    def __init__(self, models_dir: str = "./ml_models"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
        self.models: Dict[str, BaseModel] = {}
    
    def create_forecaster(self, model_id: str, name: str = "Prophet Forecaster") -> ProphetForecaster:
        """Create a new Prophet forecaster."""
        forecaster = ProphetForecaster(model_id, name)
        self.models[model_id] = forecaster
        return forecaster
    
    def create_anomaly_detector(self, model_id: str, name: str = "Isolation Forest Detector") -> IsolationForestDetector:
        """Create a new anomaly detector."""
        detector = IsolationForestDetector(model_id, name)
        self.models[model_id] = detector
        return detector
    
    def get_model(self, model_id: str) -> Optional[BaseModel]:
        """Get a model by ID."""
        return self.models.get(model_id)
    
    def list_models(self) -> List[ModelInfo]:
        """List all models."""
        return [m.info for m in self.models.values()]
    
    async def train_forecaster(
        self,
        model_id: str,
        data: List[TimeSeriesData],
        frequency: ForecastFrequency = ForecastFrequency.DAILY,
        **kwargs
    ) -> Dict[str, float]:
        """Train a forecaster model."""
        model = self.get_model(model_id)
        if not model or model.model_type != ModelType.FORECASTING:
            raise ValueError(f"Forecaster model {model_id} not found")
        
        return await model.train(data, frequency=frequency, **kwargs)
    
    async def train_anomaly_detector(
        self,
        model_id: str,
        data: List[TimeSeriesData],
        **kwargs
    ) -> Dict[str, float]:
        """Train an anomaly detector model."""
        model = self.get_model(model_id)
        if not model or model.model_type != ModelType.ANOMALY_DETECTION:
            raise ValueError(f"Anomaly detector model {model_id} not found")
        
        return await model.train(data, **kwargs)
    
    async def forecast(
        self,
        model_id: str,
        horizon: int = 30,
        **kwargs
    ) -> List[ForecastResult]:
        """Generate forecasts."""
        model = self.get_model(model_id)
        if not model or model.model_type != ModelType.FORECASTING:
            raise ValueError(f"Forecaster model {model_id} not found")
        
        return await model.predict(horizon=horizon, **kwargs)
    
    async def detect_anomalies(
        self,
        model_id: str,
        data: List[TimeSeriesData],
        **kwargs
    ) -> List[AnomalyResult]:
        """Detect anomalies."""
        model = self.get_model(model_id)
        if not model or model.model_type != ModelType.ANOMALY_DETECTION:
            raise ValueError(f"Anomaly detector model {model_id} not found")
        
        if isinstance(model, ProphetForecaster):
            return await model.detect_anomalies(data, **kwargs)
        elif isinstance(model, IsolationForestDetector):
            return await model.predict(data, **kwargs)
        else:
            raise ValueError(f"Unknown model type for anomaly detection")
    
    def save_model(self, model_id: str):
        """Save a model to disk."""
        model = self.get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        
        path = self.models_dir / f"{model_id}.pkl"
        model.save(str(path))
        logger.info(f"Saved model {model_id} to {path}")
    
    def load_model(self, model_id: str, model_type: ModelType) -> BaseModel:
        """Load a model from disk."""
        path = self.models_dir / f"{model_id}.pkl"
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        
        if model_type == ModelType.FORECASTING:
            model = ProphetForecaster.load(str(path))
        elif model_type == ModelType.ANOMALY_DETECTION:
            model = IsolationForestDetector.load(str(path))
        else:
            raise ValueError(f"Unsupported model type: {model_type}")
        
        self.models[model_id] = model
        return model
    
    def delete_model(self, model_id: str):
        """Delete a model."""
        if model_id in self.models:
            del self.models[model_id]
        
        path = self.models_dir / f"{model_id}.pkl"
        meta_path = path.with_name(f"{model_id}_meta.json")
        if path.exists():
            path.unlink()
        if meta_path.exists():
            meta_path.unlink()
        
        logger.info(f"Deleted model {model_id}")


# Global ML Pipeline instance
ml_pipeline = MLPipeline()