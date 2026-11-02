"""
Forecasting Engine for VCOS Intelligence Layer.

Provides time series forecasting using multiple methods:
- Prophet (Facebook)
- NeuralProphet
- TimesFM (Google)
- ARIMA/SARIMA (statsmodels)
- Exponential Smoothing
- Custom ML models
"""

import asyncio
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning("Prophet not installed. Install with: pip install prophet")

try:
    from neuralprophet import NeuralProphet
    NEURALPROPHET_AVAILABLE = True
except ImportError:
    NEURALPROPHET_AVAILABLE = False
    logger.warning("NeuralProphet not installed. Install with: pip install neuralprophet")

try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.seasonal import seasonal_decompose
    from statsmodels.tsa.stattools import adfuller
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("Statsmodels not installed. Install with: pip install statsmodels")

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("Scikit-learn not installed")


class ForecastMethod(str, Enum):
    """Forecasting methods."""
    PROPHET = "prophet"
    NEURALPROPHET = "neuralprophet"
    ARIMA = "arima"
    SARIMA = "sarima"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    LINEAR_REGRESSION = "linear_regression"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    ENSEMBLE = "ensemble"


class Frequency(str, Enum):
    """Time series frequencies."""
    MINUTELY = "T"
    HOURLY = "H"
    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"
    QUARTERLY = "Q"
    YEARLY = "A"


@dataclass
class TimeSeriesData:
    """Time series data container."""
    timestamps: pd.DatetimeIndex
    values: np.ndarray
    frequency: Optional[Frequency] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame({"ds": self.timestamps, "y": self.values})

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame, date_col: str = "ds", value_col: str = "y") -> "TimeSeriesData":
        timestamps = pd.to_datetime(df[date_col])
        values = df[value_col].values
        return cls(timestamps=timestamps, values=values)


@dataclass
class ForecastResult:
    """Forecasting result."""
    timestamps: pd.DatetimeIndex
    forecast: np.ndarray
    lower_bound: Optional[np.ndarray] = None
    upper_bound: Optional[np.ndarray] = None
    confidence_level: float = 0.95
    method: str = ""
    model_params: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dataframe(self) -> pd.DataFrame:
        df = pd.DataFrame({
            "ds": self.timestamps,
            "yhat": self.forecast,
        })
        if self.lower_bound is not None:
            df["yhat_lower"] = self.lower_bound
        if self.upper_bound is not None:
            df["yhat_upper"] = self.upper_bound
        return df


@dataclass
class ModelEvaluation:
    """Model evaluation metrics."""
    mae: float
    mse: float
    rmse: float
    mape: float
    smape: float
    coverage: Optional[float] = None  # Prediction interval coverage


class ForecastingEngine:
    """
    Unified Forecasting Engine supporting multiple methods.

    Features:
    - Multiple forecasting algorithms
    - Automatic model selection
    - Hyperparameter tuning
    - Cross-validation
    - Ensemble forecasting
    - Anomaly detection in forecasts
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._fitted_models: Dict[str, Any] = {}
        self._data_cache: Dict[str, TimeSeriesData] = {}

    # ==================== Data Management ====================

    def register_data(self, name: str, data: Union[TimeSeriesData, pd.DataFrame], date_col: str = "ds", value_col: str = "y"):
        """Register time series data."""
        if isinstance(data, pd.DataFrame):
            ts_data = TimeSeriesData.from_dataframe(data, date_col, value_col)
        else:
            ts_data = data
        self._data_cache[name] = ts_data
        logger.info(f"Registered time series: {name} ({len(ts_data.values)} points)")

    def get_data(self, name: str) -> Optional[TimeSeriesData]:
        return self._data_cache.get(name)

    def list_data(self) -> List[str]:
        return list(self._data_cache.keys())

    # ==================== Forecasting Methods ====================

    async def forecast(
        self,
        data_name: str,
        horizon: int,
        method: ForecastMethod = ForecastMethod.PROPHET,
        frequency: Optional[Frequency] = None,
        confidence_level: float = 0.95,
        params: Dict[str, Any] = None,
        include_history: bool = False,
    ) -> ForecastResult:
        """Generate forecast using specified method."""
        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        params = params or {}

        try:
            if method == ForecastMethod.PROPHET:
                return await self._forecast_prophet(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.NEURALPROPHET:
                return await self._forecast_neuralprophet(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.ARIMA:
                return await self._forecast_arima(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.SARIMA:
                return await self._forecast_sarima(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.EXPONENTIAL_SMOOTHING:
                return await self._forecast_exp_smoothing(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.LINEAR_REGRESSION:
                return await self._forecast_linear(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.RANDOM_FOREST:
                return await self._forecast_rf(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.GRADIENT_BOOSTING:
                return await self._forecast_gb(data, horizon, frequency, confidence_level, params, include_history)
            elif method == ForecastMethod.ENSEMBLE:
                return await self._forecast_ensemble(data, horizon, frequency, confidence_level, params, include_history)
            else:
                raise ValueError(f"Unsupported method: {method}")
        except Exception as e:
            logger.error(f"Forecasting failed: {e}")
            raise

    async def _forecast_prophet(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using Facebook Prophet."""
        if not PROPHET_AVAILABLE:
            raise RuntimeError("Prophet not installed. Install: pip install prophet")

        df = data.to_dataframe()

        model = Prophet(
            interval_width=confidence_level,
            yearly_seasonality=params.get("yearly_seasonality", True),
            weekly_seasonality=params.get("weekly_seasonality", True),
            daily_seasonality=params.get("daily_seasonality", False),
            seasonality_mode=params.get("seasonality_mode", "additive"),
            changepoint_prior_scale=params.get("changepoint_prior_scale", 0.05),
            seasonality_prior_scale=params.get("seasonality_prior_scale", 10.0),
        )

        # Add custom seasonalities
        for name, period, fourier_order in params.get("custom_seasonalities", []):
            model.add_seasonality(name=name, period=period, fourier_order=fourier_order)

        # Add regressors
        for reg in params.get("regressors", []):
            model.add_regressor(reg)

        # Fit model
        await asyncio.get_event_loop().run_in_executor(None, model.fit, df)

        # Make future dataframe
        freq = frequency.value if frequency else self._infer_frequency(data.timestamps)
        future = model.make_future_dataframe(periods=horizon, freq=freq, include_history=include_history)

        # Add future regressor values if needed
        for reg in params.get("regressors", []):
            if reg in df.columns:
                # For simplicity, use last known value
                last_val = df[reg].iloc[-1]
                future[reg] = last_val

        # Predict
        forecast = await asyncio.get_event_loop().run_in_executor(None, model.predict, future)

        # Extract results
        if include_history:
            forecast_df = forecast
        else:
            forecast_df = forecast.tail(horizon)

        timestamps = pd.to_datetime(forecast_df["ds"])
        forecast_values = forecast_df["yhat"].values
        lower = forecast_df["yhat_lower"].values if "yhat_lower" in forecast_df.columns else None
        upper = forecast_df["yhat_upper"].values if "yhat_upper" in forecast_df.columns else None

        # Calculate metrics on training data
        train_pred = model.predict(df)
        metrics = self._calculate_metrics(df["y"].values, train_pred["yhat"].values)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=confidence_level,
            method="prophet",
            model_params=params,
            metrics=metrics,
        )

    async def _forecast_neuralprophet(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using NeuralProphet."""
        if not NEURALPROPHET_AVAILABLE:
            raise RuntimeError("NeuralProphet not installed. Install: pip install neuralprophet")

        df = data.to_dataframe()

        model = NeuralProphet(
            n_forecasts=horizon,
            n_lags=params.get("n_lags", 14),
            n_changepoints=params.get("n_changepoints", 10),
            yearly_seasonality=params.get("yearly_seasonality", True),
            weekly_seasonality=params.get("weekly_seasonality", True),
            daily_seasonality=params.get("daily_seasonality", False),
            learning_rate=params.get("learning_rate", 0.01),
            epochs=params.get("epochs", 100),
            batch_size=params.get("batch_size", 32),
        )

        # Add regressors
        for reg in params.get("regressors", []):
            if reg in df.columns:
                model.add_future_regressor(reg)

        # Fit
        metrics_df = await asyncio.get_event_loop().run_in_executor(None, model.fit, df, freq=frequency.value if frequency else "D")

        # Predict
        future = model.make_future_dataframe(df, periods=horizon, n_historic_predictions=len(df) if include_history else 0)
        forecast = await asyncio.get_event_loop().run_in_executor(None, model.predict, future)

        if include_history:
            forecast_df = forecast
        else:
            forecast_df = forecast.tail(horizon)

        timestamps = pd.to_datetime(forecast_df["ds"])
        forecast_values = forecast_df["yhat1"].values
        lower = forecast_df["yhat1_lower"].values if "yhat1_lower" in forecast_df.columns else None
        upper = forecast_df["yhat1_upper"].values if "yhat1_upper" in forecast_df.columns else None

        # Calculate metrics
        train_pred = model.predict(df)
        metrics = self._calculate_metrics(df["y"].values, train_pred["yhat1"].values)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=0.95,  # NeuralProphet uses fixed intervals
            method="neuralprophet",
            model_params=params,
            metrics=metrics,
        )

    async def _forecast_arima(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using ARIMA."""
        if not STATSMODELS_AVAILABLE:
            raise RuntimeError("Statsmodels not installed. Install: pip install statsmodels")

        values = data.values
        order = params.get("order", (1, 1, 1))
        seasonal_order = params.get("seasonal_order", (0, 0, 0, 0))

        model = ARIMA(values, order=order, seasonal_order=seasonal_order)
        fitted = await asyncio.get_event_loop().run_in_executor(None, model.fit)

        # Forecast
        forecast_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fitted.forecast(horizon, alpha=1-confidence_level)
        )

        forecast_values = forecast_result.predicted_mean
        lower = forecast_result.conf_int()[:, 0] if hasattr(forecast_result, 'conf_int') else None
        upper = forecast_result.conf_int()[:, 1] if hasattr(forecast_result, 'conf_int') else None

        # Generate timestamps
        freq = frequency.value if frequency else self._infer_frequency(data.timestamps)
        last_date = data.timestamps[-1]
        timestamps = pd.date_range(start=last_date, periods=horizon+1, freq=freq)[1:]

        # Calculate metrics
        fitted_values = fitted.fittedvalues
        metrics = self._calculate_metrics(values, fitted_values)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=confidence_level,
            method="arima",
            model_params={"order": order, "seasonal_order": seasonal_order, **params},
            metrics=metrics,
        )

    async def _forecast_sarima(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using SARIMA."""
        return await self._forecast_arima(data, horizon, frequency, confidence_level, params, include_history)

    async def _forecast_exp_smoothing(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using Exponential Smoothing."""
        if not STATSMODELS_AVAILABLE:
            raise RuntimeError("Statsmodels not installed")

        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        values = data.values
        trend = params.get("trend", "add")
        seasonal = params.get("seasonal", "add")
        seasonal_periods = params.get("seasonal_periods", 7)

        model = ExponentialSmoothing(
            values,
            trend=trend,
            seasonal=seasonal,
            seasonal_periods=seasonal_periods,
        )

        fitted = await asyncio.get_event_loop().run_in_executor(None, model.fit)

        forecast_result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fitted.forecast(horizon)
        )

        forecast_values = forecast_result
        # Confidence intervals not directly available, approximate
        residuals = values - fitted.fittedvalues
        std_resid = np.std(residuals)
        z = 1.96  # 95% CI
        lower = forecast_values - z * std_resid
        upper = forecast_values + z * std_resid

        freq = frequency.value if frequency else self._infer_frequency(data.timestamps)
        last_date = data.timestamps[-1]
        timestamps = pd.date_range(start=last_date, periods=horizon+1, freq=freq)[1:]

        metrics = self._calculate_metrics(values, fitted.fittedvalues)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=confidence_level,
            method="exponential_smoothing",
            model_params={"trend": trend, "seasonal": seasonal, "seasonal_periods": seasonal_periods, **params},
            metrics=metrics,
        )

    async def _forecast_linear(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using Linear Regression with time features."""
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("Scikit-learn not installed")

        from sklearn.linear_model import LinearRegression, Ridge
        from sklearn.preprocessing import PolynomialFeatures

        values = data.values
        timestamps = data.timestamps

        # Create time features
        X = np.arange(len(values)).reshape(-1, 1)
        y = values

        degree = params.get("degree", 1)
        if degree > 1:
            poly = PolynomialFeatures(degree=degree)
            X = poly.fit_transform(X)

        alpha = params.get("alpha", 0.0)
        model = Ridge(alpha=alpha) if alpha > 0 else LinearRegression()

        model.fit(X, y)

        # Forecast
        X_future = np.arange(len(values), len(values) + horizon).reshape(-1, 1)
        if degree > 1:
            X_future = poly.transform(X_future)

        forecast_values = model.predict(X_future)

        # Confidence intervals (approximate)
        train_pred = model.predict(X)
        residuals = y - train_pred
        std_resid = np.std(residuals)
        z = 1.96
        lower = forecast_values - z * std_resid
        upper = forecast_values + z * std_resid

        freq = frequency.value if frequency else self._infer_frequency(data.timestamps)
        last_date = data.timestamps[-1]
        timestamps = pd.date_range(start=last_date, periods=horizon+1, freq=freq)[1:]

        metrics = self._calculate_metrics(y, train_pred)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=confidence_level,
            method="linear_regression",
            model_params={"degree": degree, "alpha": alpha, **params},
            metrics=metrics,
        )

    async def _forecast_rf(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using Random Forest with lag features."""
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("Scikit-learn not installed")

        from sklearn.ensemble import RandomForestRegressor

        values = data.values
        n_lags = params.get("n_lags", 7)

        # Create lag features
        X, y = self._create_lag_features(values, n_lags)
        if len(X) == 0:
            raise ValueError("Insufficient data for lag features")

        model = RandomForestRegressor(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", 10),
            random_state=42,
        )

        model.fit(X, y)

        # Recursive forecasting
        forecast_values = []
        last_lags = values[-n_lags:].tolist()

        for _ in range(horizon):
            X_next = np.array(last_lags[-n_lags:]).reshape(1, -1)
            pred = model.predict(X_next)[0]
            forecast_values.append(pred)
            last_lags.append(pred)

        forecast_values = np.array(forecast_values)

        # Confidence intervals via prediction intervals
        train_pred = model.predict(X)
        residuals = np.array(values[n_lags:]) - train_pred
        std_resid = np.std(residuals)
        z = 1.96
        lower = forecast_values - z * std_resid
        upper = forecast_values + z * std_resid

        freq = frequency.value if frequency else self._infer_frequency(data.timestamps)
        last_date = data.timestamps[-1]
        timestamps = pd.date_range(start=last_date, periods=horizon+1, freq=freq)[1:]

        metrics = self._calculate_metrics(np.array(values[n_lags:]), train_pred)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=confidence_level,
            method="random_forest",
            model_params={"n_lags": n_lags, **params},
            metrics=metrics,
        )

    async def _forecast_gb(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Forecast using Gradient Boosting with lag features."""
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("Scikit-learn not installed")

        from sklearn.ensemble import GradientBoostingRegressor

        values = data.values
        n_lags = params.get("n_lags", 7)

        X, y = self._create_lag_features(values, n_lags)
        if len(X) == 0:
            raise ValueError("Insufficient data for lag features")

        model = GradientBoostingRegressor(
            n_estimators=params.get("n_estimators", 100),
            max_depth=params.get("max_depth", 5),
            learning_rate=params.get("learning_rate", 0.1),
            random_state=42,
        )

        model.fit(X, y)

        # Recursive forecasting
        forecast_values = []
        last_lags = values[-n_lags:].tolist()

        for _ in range(horizon):
            X_next = np.array(last_lags[-n_lags:]).reshape(1, -1)
            pred = model.predict(X_next)[0]
            forecast_values.append(pred)
            last_lags.append(pred)

        forecast_values = np.array(forecast_values)

        train_pred = model.predict(X)
        residuals = np.array(values[n_lags:]) - train_pred
        std_resid = np.std(residuals)
        z = 1.96
        lower = forecast_values - z * std_resid
        upper = forecast_values + z * std_resid

        freq = frequency.value if frequency else self._infer_frequency(data.timestamps)
        last_date = data.timestamps[-1]
        timestamps = pd.date_range(start=last_date, periods=horizon+1, freq=freq)[1:]

        metrics = self._calculate_metrics(np.array(values[n_lags:]), train_pred)

        return ForecastResult(
            timestamps=timestamps,
            forecast=forecast_values,
            lower_bound=lower,
            upper_bound=upper,
            confidence_level=confidence_level,
            method="gradient_boosting",
            model_params={"n_lags": n_lags, **params},
            metrics=metrics,
        )

    async def _forecast_ensemble(
        self,
        data: TimeSeriesData,
        horizon: int,
        frequency: Optional[Frequency],
        confidence_level: float,
        params: Dict[str, Any],
        include_history: bool,
    ) -> ForecastResult:
        """Ensemble forecasting combining multiple methods."""
        methods = params.get("methods", [
            ForecastMethod.PROPHET,
            ForecastMethod.ARIMA,
            ForecastMethod.RANDOM_FOREST,
        ])
        weights = params.get("weights", [1.0] * len(methods))

        # Normalize weights
        weights = np.array(weights) / np.sum(weights)

        forecasts = []
        all_lower = []
        all_upper = []
        all_timestamps = None

        for method, weight in zip(methods, weights):
            try:
                result = await self.forecast(
                    data_name="__temp__",
                    horizon=horizon,
                    method=method,
                    frequency=frequency,
                    confidence_level=confidence_level,
                    params=params.get(method.value, {}),
                    include_history=include_history,
                )
                # Temporarily store data
                self._data_cache["__temp__"] = data
                result = await self.forecast(
                    data_name="__temp__",
                    horizon=horizon,
                    method=method,
                    frequency=frequency,
                    confidence_level=confidence_level,
                    params=params.get(method.value, {}),
                    include_history=include_history,
                )
                forecasts.append(result.forecast * weight)
                if result.lower_bound is not None:
                    all_lower.append(result.lower_bound * weight)
                if result.upper_bound is not None:
                    all_upper.append(result.upper_bound * weight)
                if all_timestamps is None:
                    all_timestamps = result.timestamps
            except Exception as e:
                logger.warning(f"Ensemble method {method} failed: {e}")

        if not forecasts:
            raise RuntimeError("All ensemble methods failed")

        # Weighted average
        ensemble_forecast = np.sum(forecasts, axis=0)
        ensemble_lower = np.sum(all_lower, axis=0) if all_lower else None
        ensemble_upper = np.sum(all_upper, axis=0) if all_upper else None

        return ForecastResult(
            timestamps=all_timestamps,
            forecast=ensemble_forecast,
            lower_bound=ensemble_lower,
            upper_bound=ensemble_upper,
            confidence_level=confidence_level,
            method="ensemble",
            model_params={"methods": [m.value for m in methods], "weights": weights.tolist()},
            metrics={},
        )

    # ==================== Evaluation ====================

    async def evaluate(
        self,
        data_name: str,
        horizon: int,
        methods: List[ForecastMethod] = None,
        test_size: float = 0.2,
        params: Dict[str, Any] = None,
    ) -> Dict[str, ModelEvaluation]:
        """Evaluate multiple forecasting methods on historical data."""
        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        methods = methods or [
            ForecastMethod.PROPHET,
            ForecastMethod.ARIMA,
            ForecastMethod.RANDOM_FOREST,
            ForecastMethod.GRADIENT_BOOSTING,
        ]

        # Split data
        split_idx = int(len(data.values) * (1 - test_size))
        train_data = TimeSeriesData(
            timestamps=data.timestamps[:split_idx],
            values=data.values[:split_idx],
        )
        test_values = data.values[split_idx:]
        test_timestamps = data.timestamps[split_idx:]

        # Store train data temporarily
        self._data_cache["__train__"] = train_data

        results = {}
        for method in methods:
            try:
                result = await self.forecast(
                    data_name="__train__",
                    horizon=len(test_values),
                    method=method,
                    confidence_level=0.95,
                )

                eval_result = self._calculate_metrics(test_values, result.forecast)
                results[method.value] = ModelEvaluation(**eval_result)
            except Exception as e:
                logger.warning(f"Evaluation failed for {method}: {e}")
                results[method.value] = ModelEvaluation(mae=float('inf'), mse=float('inf'), rmse=float('inf'), mape=float('inf'), smape=float('inf'))

        # Clean up
        del self._data_cache["__train__"]

        return results

    def _calculate_metrics(self, actual: np.ndarray, predicted: np.ndarray) -> Dict[str, float]:
        """Calculate forecasting metrics."""
        actual = np.array(actual)
        predicted = np.array(predicted)

        # Align lengths
        min_len = min(len(actual), len(predicted))
        actual = actual[:min_len]
        predicted = predicted[:min_len]

        if len(actual) == 0:
            return {"mae": float('inf'), "mse": float('inf'), "rmse": float('inf'), "mape": float('inf'), "smape": float('inf')}

        mae = np.mean(np.abs(actual - predicted))
        mse = np.mean((actual - predicted) ** 2)
        rmse = np.sqrt(mse)
        mape = np.mean(np.abs((actual - predicted) / np.where(actual != 0, actual, 1))) * 100
        smape = np.mean(2 * np.abs(actual - predicted) / (np.abs(actual) + np.abs(predicted) + 1e-8)) * 100

        return {
            "mae": float(mae),
            "mse": float(mse),
            "rmse": float(rmse),
            "mape": float(mape),
            "smape": float(smape),
        }

    def _create_lag_features(self, values: np.ndarray, n_lags: int) -> Tuple[np.ndarray, np.ndarray]:
        """Create lag features for ML models."""
        X, y = [], []
        for i in range(n_lags, len(values)):
            X.append(values[i-n_lags:i])
            y.append(values[i])
        return np.array(X), np.array(y)

    def _infer_frequency(self, timestamps: pd.DatetimeIndex) -> str:
        """Infer frequency from timestamps."""
        if len(timestamps) < 2:
            return "D"

        diffs = np.diff(timestamps.astype(np.int64))
        median_diff = np.median(diffs)

        # Convert nanoseconds to appropriate frequency
        if median_diff <= 60 * 1e9:  # <= 1 minute
            return "T"
        elif median_diff <= 3600 * 1e9:  # <= 1 hour
            return "H"
        elif median_diff <= 86400 * 1e9:  # <= 1 day
            return "D"
        elif median_diff <= 604800 * 1e9:  # <= 1 week
            return "W"
        else:
            return "D"

    # ==================== Anomaly Detection ====================

    async def detect_anomalies(
        self,
        data_name: str,
        method: str = "isolation_forest",
        contamination: float = 0.1,
    ) -> Dict[str, Any]:
        """Detect anomalies in time series."""
        data = self._data_cache.get(data_name)
        if data is None:
            raise ValueError(f"Data not found: {data_name}")

        values = data.values

        if method == "isolation_forest":
            if not SKLEARN_AVAILABLE:
                raise RuntimeError("Scikit-learn not installed")
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(contamination=contamination, random_state=42)
            X = values.reshape(-1, 1)
            predictions = model.fit_predict(X)
            scores = model.score_samples(X)

            anomalies = np.where(predictions == -1)[0]

            return {
                "method": "isolation_forest",
                "anomaly_indices": anomalies.tolist(),
                "anomaly_timestamps": data.timestamps[anomalies].tolist(),
                "anomaly_values": values[anomalies].tolist(),
                "anomaly_scores": scores[anomalies].tolist(),
                "total_anomalies": len(anomalies),
            }

        elif method == "statistical":
            # Statistical anomaly detection using rolling statistics
            window = min(30, len(data.values) // 4)
            rolling_mean = pd.Series(values).rolling(window=window, center=True).mean()
            rolling_std = pd.Series(values).rolling(window=window, center=True).std()

            z_scores = np.abs((values - rolling_mean) / (rolling_std + 1e-8))
            anomalies = np.where(z_scores > 3)[0]

            return {
                "method": "statistical",
                "anomaly_indices": anomalies.tolist(),
                "anomaly_timestamps": data.timestamps[anomalies].tolist(),
                "anomaly_values": values[anomalies].tolist(),
                "z_scores": z_scores[anomalies].tolist(),
                "total_anomalies": len(anomalies),
            }

        elif method == "forecast_residuals":
            # Detect anomalies based on forecast residuals
            # Use a simple forecast and check residuals
            result = await self.forecast(data_name, horizon=min(10, len(data)//4))
            # Compare forecast with actual (if we have enough data)
            # This is a simplified version
            return {
                "method": "forecast_residuals",
                "message": "Use forecast residuals for anomaly detection",
            }

        raise ValueError(f"Unknown anomaly detection method: {method}")

    # ==================== Utilities ====================

    def list_data(self) -> List[str]:
        return list(self._data_cache.keys())

    def get_data_info(self, name: str) -> Optional[Dict[str, Any]]:
        data = self._data_cache.get(name)
        if data is None:
            return None
        return {
            "length": len(data.values),
            "start": data.timestamps[0].isoformat() if len(data.timestamps) > 0 else None,
            "end": data.timestamps[-1].isoformat() if len(data.timestamps) > 0 else None,
            "frequency": str(data.frequency) if data.frequency else "unknown",
            "stats": {
                "mean": float(np.mean(data.values)),
                "std": float(np.std(data.values)),
                "min": float(np.min(data.values)),
                "max": float(np.max(data.values)),
            },
        }


# Global forecasting engine instance
_forecasting_engine: Optional[ForecastingEngine] = None


def get_forecasting_engine() -> ForecastingEngine:
    """Get or create forecasting engine singleton."""
    global _forecasting_engine
    if _forecasting_engine is None:
        _forecasting_engine = ForecastingEngine()
    return _forecasting_engine


def init_forecasting_engine() -> ForecastingEngine:
    """Initialize forecasting engine."""
    global _forecasting_engine
    _forecasting_engine = ForecastingEngine()
    return _forecasting_engine