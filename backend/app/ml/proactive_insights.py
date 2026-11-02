"""
Proactive Insights & Anomaly Detection Engine for VCOS Intelligence Layer.

Provides automated business monitoring:
- Anomaly detection (statistical, ML-based, forecast residuals)
- Trend analysis & change point detection
- Automated insight generation
- Alert management with routing
- Business KPI monitoring
- Root cause analysis suggestions
"""

import asyncio
import logging
import warnings
from collections import defaultdict
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

try:
    from scipy import stats
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("SciPy not installed. Install: pip install scipy")

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("Scikit-learn not installed")

try:
    from ruptures import Pelt, Binseg, Dynp
    RUPTURES_AVAILABLE = True
except ImportError:
    RUPTURES_AVAILABLE = False
    logger.warning("ruptures not installed. Install: pip install ruptures")


class InsightType(str, Enum):
    """Types of insights."""
    ANOMALY = "anomaly"
    TREND_CHANGE = "trend_change"
    SEASONALITY_SHIFT = "seasonality_shift"
    CORRELATION_BREAK = "correlation_break"
    THRESHOLD_BREACH = "threshold_breach"
    FORECAST_DEVIATION = "forecast_deviation"
    PATTERN_DISCOVERY = "pattern_discovery"
    CAUSAL_HYPOTHESIS = "causal_hypothesis"


class InsightSeverity(str, Enum):
    """Insight severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyMethod(str, Enum):
    """Anomaly detection methods."""
    ISOLATION_FOREST = "isolation_forest"
    LOCAL_OUTLIER_FACTOR = "local_outlier_factor"
    DBSCAN = "dbscan"
    STATISTICAL_ZSCORE = "statistical_zscore"
    FORECAST_RESIDUALS = "forecast_residuals"
    ENSEMBLE = "ensemble"


class AlertChannel(str, Enum):
    """Alert delivery channels."""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    PUSH = "push"
    IN_APP = "in_app"


@dataclass
class DataPoint:
    """Single data point for monitoring."""
    timestamp: datetime
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeSeriesMetric:
    """Business metric time series."""
    name: str
    data: List[DataPoint]
    frequency: str = "1h"  # pandas frequency string
    baseline_stats: Dict[str, float] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)  # warning, critical
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    """Detected anomaly."""
    id: str
    metric_name: str
    timestamp: datetime
    value: float
    expected_range: Tuple[float, float]
    severity: InsightSeverity
    method: AnomalyMethod
    score: float  # anomaly score (0-1)
    explanation: str
    context: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


@dataclass
class TrendChange:
    """Detected trend change."""
    id: str
    metric_name: str
    change_point: datetime
    direction: str  # increasing, decreasing, flat
    magnitude: float
    confidence: float
    before_trend: float
    after_trend: float
    method: str
    explanation: str


@dataclass
class Insight:
    """Generated business insight."""
    id: str
    type: InsightType
    title: str
    description: str
    severity: InsightSeverity
    metrics_affected: List[str]
    detected_at: datetime
    data_points: List[Dict[str, Any]] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)
    related_anomalies: List[str] = field(default_factory=list)
    related_trend_changes: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class Alert:
    """Alert for notification."""
    id: str
    insight_id: str
    channel: AlertChannel
    recipient: str
    subject: str
    message: str
    severity: InsightSeverity
    sent: bool = False
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class AlertRule:
    """Alert routing rule."""
    id: str
    name: str
    metric_patterns: List[str]  # regex patterns
    severity_threshold: InsightSeverity
    channels: List[AlertChannel]
    recipients: Dict[AlertChannel, List[str]]
    cooldown_minutes: int = 60
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class AnomalyDetector:
    """Multi-method anomaly detection."""

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._scalers: Dict[str, StandardScaler] = {}

    async def detect(
        self,
        metric: TimeSeriesMetric,
        method: AnomalyMethod = AnomalyMethod.ENSEMBLE,
        contamination: float = 0.05,
    ) -> List[Anomaly]:
        """Detect anomalies in metric data."""
        if len(metric.data) < 10:
            return []

        values = np.array([d.value for d in metric.data])
        timestamps = [d.timestamp for d in metric.data]

        anomalies = []

        if method == AnomalyMethod.ISOLATION_FOREST:
            anomalies.extend(await self._isolation_forest(metric, contamination))
        elif method == AnomalyMethod.LOCAL_OUTLIER_FACTOR:
            anomalies.extend(await self._lof(metric, contamination))
        elif method == AnomalyMethod.DBSCAN:
            anomalies.extend(await self._dbscan(metric))
        elif method == AnomalyMethod.STATISTICAL_ZSCORE:
            anomalies.extend(await self._statistical_zscore(metric))
        elif method == AnomalyMethod.FORECAST_RESIDUALS:
            anomalies.extend(await self._forecast_residuals(metric))
        elif method == AnomalyMethod.ENSEMBLE:
            # Run all methods and combine
            all_anomalies = []
            for m in [AnomalyMethod.ISOLATION_FOREST, AnomalyMethod.STATISTICAL_ZSCORE, AnomalyMethod.FORECAST_RESIDUALS]:
                try:
                    all_anomalies.extend(await self.detect(metric, m, contamination))
                except Exception as e:
                    logger.warning(f"Ensemble method {m} failed: {e}")

            # Deduplicate and score by consensus
            anomalies = self._ensemble_score(all_anomalies)
        else:
            anomalies.extend(await self._statistical_zscore(metric))

        return anomalies

    async def _isolation_forest(self, metric: TimeSeriesMetric, contamination: float) -> List[Anomaly]:
        """Isolation Forest anomaly detection."""
        if not SKLEARN_AVAILABLE:
            return []

        values = np.array([d.value for d in metric.data]).reshape(-1, 1)
        timestamps = [d.timestamp for d in metric.data]

        model = IsolationForest(contamination=contamination, random_state=42)
        predictions = model.fit_predict(values)
        scores = model.score_samples(values)

        anomalies = []
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:
                severity = InsightSeverity.WARNING if score > -0.5 else InsightSeverity.CRITICAL
                anomalies.append(Anomaly(
                    id=f"iso_{metric.name}_{i}",
                    metric_name=metric.name,
                    timestamp=timestamps[i],
                    value=values[i][0],
                    expected_range=self._get_expected_range(values),
                    severity=severity,
                    method=AnomalyMethod.ISOLATION_FOREST,
                    score=float(1 - (score + 0.5) * 2),  # Normalize to 0-1
                    explanation=f"Isolation Forest detected anomaly with score {score:.3f}",
                    context={"isolation_score": float(score)},
                ))

        return anomalies

    async def _lof(self, metric: TimeSeriesMetric, contamination: float) -> List[Anomaly]:
        """Local Outlier Factor anomaly detection."""
        if not SKLEARN_AVAILABLE:
            return []

        values = np.array([d.value for d in metric.data]).reshape(-1, 1)
        timestamps = [d.timestamp for d in metric.data]

        n_neighbors = min(20, len(values) - 1)
        model = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination, novelty=False)
        predictions = model.fit_predict(values)
        scores = -model.negative_outlier_factor_

        anomalies = []
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:
                severity = InsightSeverity.WARNING if score > -1.5 else InsightSeverity.CRITICAL
                anomalies.append(Anomaly(
                    id=f"lof_{metric.name}_{i}",
                    metric_name=metric.name,
                    timestamp=timestamps[i],
                    value=values[i][0],
                    expected_range=self._get_expected_range(values),
                    severity=severity,
                    method=AnomalyMethod.LOCAL_OUTLIER_FACTOR,
                    score=float(min(1.0, abs(score) / 2)),
                    explanation=f"Local Outlier Factor detected anomaly with score {score:.3f}",
                    context={"lof_score": float(score)},
                ))

        return anomalies

    async def _dbscan(self, metric: TimeSeriesMetric) -> List[Anomaly]:
        """DBSCAN anomaly detection."""
        if not SKLEARN_AVAILABLE:
            return []

        values = np.array([d.value for d in metric.data]).reshape(-1, 1)
        timestamps = [d.timestamp for d in metric.data]

        # Scale values
        scaler = StandardScaler()
        values_scaled = scaler.fit_transform(values)

        eps = 0.5
        min_samples = max(3, len(values) // 10)
        model = DBSCAN(eps=eps, min_samples=min_samples)
        clusters = model.fit_predict(values_scaled)

        anomalies = []
        for i, cluster in enumerate(clusters):
            if cluster == -1:  # Noise point
                anomalies.append(Anomaly(
                    id=f"dbscan_{metric.name}_{i}",
                    metric_name=metric.name,
                    timestamp=timestamps[i],
                    value=values[i][0],
                    expected_range=self._get_expected_range(values),
                    severity=InsightSeverity.WARNING,
                    method=AnomalyMethod.DBSCAN,
                    score=0.7,
                    explanation="DBSCAN identified as noise point (not belonging to any cluster)",
                    context={"cluster": int(clusters[i])},
                ))

        return anomalies

    async def _statistical_zscore(self, metric: TimeSeriesMetric) -> List[Anomaly]:
        """Statistical Z-score anomaly detection."""
        values = np.array([d.value for d in metric.data])
        timestamps = [d.timestamp for d in metric.data]

        # Rolling statistics for time-series aware detection
        window = min(30, max(10, len(values) // 4))
        rolling_mean = pd.Series(values).rolling(window=window, center=True, min_periods=3).mean()
        rolling_std = pd.Series(values).rolling(window=window, center=True, min_periods=3).std()

        z_scores = np.abs((values - rolling_mean) / (rolling_std + 1e-8))
        threshold = 3.0

        anomalies = []
        for i, z in enumerate(z_scores):
            if not np.isnan(z) and z > threshold:
                severity = InsightSeverity.CRITICAL if z > 4.0 else InsightSeverity.WARNING
                anomalies.append(Anomaly(
                    id=f"zscore_{metric.name}_{i}",
                    metric_name=metric.name,
                    timestamp=timestamps[i],
                    value=values[i],
                    expected_range=(
                        float(rolling_mean.iloc[i] - 3 * rolling_std.iloc[i]) if not np.isnan(rolling_mean.iloc[i]) else float(np.min(values)),
                        float(rolling_mean.iloc[i] + 3 * rolling_std.iloc[i]) if not np.isnan(rolling_mean.iloc[i]) else float(np.max(values)),
                    ),
                    severity=InsightSeverity.CRITICAL if z > 4.0 else InsightSeverity.WARNING,
                    method=AnomalyMethod.STATISTICAL_ZSCORE,
                    score=float(min(1.0, z / 5.0)),
                    explanation=f"Z-score {z:.2f} exceeds threshold of {threshold}",
                    context={"z_score": float(z), "rolling_mean": float(rolling_mean.iloc[i]) if not np.isnan(rolling_mean.iloc[i]) else None, "rolling_std": float(rolling_std.iloc[i]) if not np.isnan(rolling_std.iloc[i]) else None},
                ))

        return anomalies

    async def _forecast_residuals(self, metric: TimeSeriesMetric) -> List[Anomaly]:
        """Anomaly detection using forecast residuals."""
        # Simple implementation using rolling forecast
        # In production, would use the ForecastingEngine
        values = np.array([d.value for d in metric.data])
        timestamps = [d.timestamp for d in metric.data]

        if len(values) < 20:
            return []

        # Simple rolling forecast
        window = min(10, len(values) // 3)
        residuals = []

        for i in range(window, len(values)):
            train = values[i-window:i]
            # Simple exponential smoothing forecast
            alpha = 0.3
            forecast = train[0]
            for val in train[1:]:
                forecast = alpha * val + (1 - alpha) * forecast

            actual = values[i]
            residual = abs(actual - forecast)
            residuals.append((i, actual, forecast, residual))

        if not residuals:
            return []

        residual_values = np.array([r[3] for r in residuals])
        threshold = np.percentile(residual_values, 95)

        anomalies = []
        for idx, actual, forecast, residual in residuals:
            if residual > threshold:
                severity = InsightSeverity.CRITICAL if residual > 2 * threshold else InsightSeverity.WARNING
                anomalies.append(Anomaly(
                    id=f"forecast_{metric.name}_{idx}",
                    metric_name=metric.name,
                    timestamp=timestamps[idx],
                    value=actual,
                    expected_range=(float(forecast - threshold), float(forecast + threshold)),
                    severity=severity,
                    method=AnomalyMethod.FORECAST_RESIDUALS,
                    score=float(min(1.0, residual / (threshold + 1e-8))),
                    explanation=f"Forecast residual {residual:.3f} exceeds 95th percentile threshold {threshold:.3f}",
                    context={"forecast": float(forecast), "residual": float(residual), "threshold": float(threshold)},
                ))

        return anomalies

    def _get_expected_range(self, values: np.ndarray) -> Tuple[float, float]:
        """Get expected range (mean ± 2 std)."""
        mean = float(np.mean(values))
        std = float(np.std(values))
        return (mean - 2 * std, mean + 2 * std)

    def _ensemble_score(self, all_anomalies: List[Anomaly]) -> List[Anomaly]:
        """Combine anomalies from multiple methods using consensus."""
        # Group by metric and timestamp
        grouped = defaultdict(list)
        for anomaly in all_anomalies:
            key = (anomaly.metric_name, anomaly.timestamp.isoformat())
            grouped[key].append(anomaly)

        ensemble_anomalies = []
        for key, anomalies in grouped.items():
            if len(anomalies) >= 2:  # Consensus: detected by 2+ methods
                # Average scores, take highest severity
                avg_score = np.mean([a.score for a in anomalies])
                max_severity = max(anomalies, key=lambda a: a.severity.value).severity

                ensemble_anomalies.append(Anomaly(
                    id=f"ensemble_{anomalies[0].metric_name}_{anomalies[0].timestamp.isoformat()}",
                    metric_name=anomalies[0].metric_name,
                    timestamp=anomalies[0].timestamp,
                    value=anomalies[0].value,
                    expected_range=anomalies[0].expected_range,
                    severity=max_severity,
                    method=AnomalyMethod.ENSEMBLE,
                    score=avg_score,
                    explanation=f"Ensemble detection: {len(anomalies)} methods agreed",
                    context={"methods": [a.method.value for a in anomalies], "individual_scores": [a.score for a in anomalies]},
                ))
            elif len(anomalies) == 1:
                # Single method, keep but lower confidence
                a = anomalies[0]
                a.score *= 0.7
                ensemble_anomalies.append(a)

        return ensemble_anomalies


class TrendDetector:
    """Trend change detection using change point analysis."""

    def __init__(self):
        self._models: Dict[str, Any] = {}

    async def detect(
        self,
        metric: TimeSeriesMetric,
        method: str = "ruptures",
        min_segment_length: int = 10,
    ) -> List[TrendChange]:
        """Detect trend changes in metric data."""
        if len(metric.data) < 20:
            return []

        values = np.array([d.value for d in metric.data])
        timestamps = [d.timestamp for d in metric.data]

        changes = []

        if method == "ruptures" and RUPTURES_AVAILABLE:
            changes.extend(await self._ruptures_detection(metric, min_segment_length))
        elif method == "rolling":
            changes.extend(await self._rolling_detection(metric))
        elif method == "cusum":
            changes.extend(await self._cusum_detection(metric))
        else:
            changes.extend(await self._rolling_detection(metric))

        return changes

    async def _ruptures_detection(
        self,
        metric: TimeSeriesMetric,
        min_segment_length: int,
    ) -> List[TrendChange]:
        """Change point detection using ruptures library."""
        if not RUPTURES_AVAILABLE:
            return []

        values = np.array([d.value for d in metric.data])

        try:
            # PELT algorithm for change point detection
            model = "rbf"  # or "linear", "rbf", "normal"
            algo = Pelt(model=model, min_size=min_segment_length, jump=5).fit(values)
            change_points = algo.predict(pen=10)  # penalty parameter

            # Remove last point (always equals length)
            change_points = [cp for cp in change_points if cp < len(metric.data)]

            changes = []
            for cp in change_points:
                if cp >= len(metric.data) or cp == 0:
                    continue

                before = metric.data[max(0, cp-10):cp]
                after = metric.data[cp:cp+10]

                if len(before) < 3 or len(after) < 3:
                    continue

                before_vals = np.array([d.value for d in before])
                after_vals = np.array([d.value for d in after])

                before_trend = np.polyfit(range(len(before_vals)), before_vals, 1)[0] if len(before_vals) > 1 else 0
                after_trend = np.polyfit(range(len(after_vals)), after_vals, 1)[0] if len(after_vals) > 1 else 0

                direction = "increasing" if after_trend > before_trend else "decreasing" if after_trend < before_trend else "flat"
                magnitude = abs(after_trend - before_trend)

                changes.append(TrendChange(
                    id=f"rupture_{metric.name}_{cp}",
                    metric_name=metric.name,
                    change_point=metric.data[cp].timestamp,
                    direction=direction,
                    magnitude=float(magnitude),
                    confidence=0.8,
                    before_trend=float(before_trend),
                    after_trend=float(after_trend),
                    method="ruptures_pelt",
                    explanation=f"Change point detected at index {cp}: trend changed from {before_trend:.4f} to {after_trend:.4f}",
                ))

            return changes
        except Exception as e:
            logger.warning(f"Ruptures detection failed: {e}")
            return []

    async def _rolling_detection(self, metric: TimeSeriesMetric) -> List[TrendChange]:
        """Rolling linear regression trend detection."""
        values = np.array([d.value for d in metric.data])
        timestamps = [d.timestamp for d in metric.data]

        window = min(20, max(10, len(values) // 5))
        trends = []

        for i in range(window, len(values)):
            window_data = values[i-window:i]
            x = np.arange(window)
            coeff = np.polyfit(x, window_data, 1)
            trends.append((i, coeff[0]))

        if not trends:
            return []

        # Find significant trend changes
        trend_values = np.array([t[1] for t in trends])
        trend_changes = np.diff(trend_values)

        # Significant change threshold
        threshold = np.std(trend_changes) * 2
        change_indices = np.where(np.abs(trend_changes) > threshold)[0]

        changes = []
        for idx in change_indices:
            actual_idx = idx + window
            if actual_idx >= len(timestamps):
                continue

            before_trend = trend_values[idx]
            after_trend = trend_values[idx + 1] if idx + 1 < len(trend_values) else before_trend

            direction = "increasing" if after_trend > before_trend else "decreasing" if after_trend < before_trend else "flat"
            magnitude = abs(after_trend - before_trend)

            changes.append(TrendChange(
                id=f"rolling_{metric.name}_{actual_idx}",
                metric_name=metric.name,
                change_point=timestamps[actual_idx],
                direction=direction,
                magnitude=float(magnitude),
                confidence=0.7,
                before_trend=float(before_trend),
                after_trend=float(after_trend),
                method="rolling_regression",
                explanation=f"Rolling trend changed from {before_trend:.4f} to {after_trend:.4f} at index {actual_idx}",
            ))

        return changes

    async def _cusum_detection(self, metric: TimeSeriesMetric) -> List[TrendChange]:
        """CUSUM change point detection."""
        values = np.array([d.value for d in metric.data])
        timestamps = [d.timestamp for d in metric.data]

        # CUSUM parameters
        threshold = 5.0 * np.std(values)
        drift = 0.5 * np.std(values)

        cusum_pos = 0
        cusum_neg = 0
        changes = []

        for i, val in enumerate(values):
            if i == 0:
                continue

            diff = val - values[i-1]
            cusum_pos = max(0, cusum_pos + diff - drift)
            cusum_neg = min(0, cusum_neg + diff + drift)

            if cusum_pos > threshold or cusum_neg < -threshold:
                direction = "increasing" if cusum_pos > threshold else "decreasing"
                magnitude = abs(cusum_pos) if cusum_pos > threshold else abs(cusum_neg)

                changes.append(TrendChange(
                    id=f"cusum_{metric.name}_{i}",
                    metric_name=metric.name,
                    change_point=timestamps[i],
                    direction=direction,
                    magnitude=float(magnitude),
                    confidence=0.75,
                    before_trend=0,
                    after_trend=float(magnitude),
                    method="cusum",
                    explanation=f"CUSUM detected change at index {i}: {direction} shift of {magnitude:.4f}",
                ))

                # Reset
                cusum_pos = 0
                cusum_neg = 0

        return changes


class InsightGenerator:
    """Automated business insight generation."""

    def __init__(self):
        self.anomaly_detector = AnomalyDetector()
        self.trend_detector = TrendDetector()

    async def generate_insights(
        self,
        metrics: Dict[str, TimeSeriesMetric],
        forecast_engine=None,
    ) -> List[Insight]:
        """Generate insights from metrics."""
        insights = []

        for name, metric in metrics.items():
            # Anomaly-based insights
            anomalies = await self.anomaly_detector.detect(metric)
            if anomalies:
                insights.extend(await self._anomaly_insights(metric, anomalies))

            # Trend-based insights
            trends = await self.trend_detector.detect(metric)
            if trends:
                insights.extend(await self._trend_insights(metric, trends))

            # Forecast deviation insights
            if forecast_engine:
                forecast_insights = await self._forecast_insights(metric, forecast_engine)
                insights.extend(forecast_insights)

            # Correlation insights (cross-metric)
            corr_insights = await self._correlation_insights(name, metric, metrics)
            insights.extend(corr_insights)

        # Sort by severity and confidence
        insights.sort(key=lambda i: (i.severity.value, -i.confidence), reverse=True)

        return insights

    async def _anomaly_insights(self, metric: TimeSeriesMetric, anomalies: List[Anomaly]) -> List[Insight]:
        """Generate insights from anomalies."""
        insights = []

        # Group anomalies by time proximity
        if not anomalies:
            return []

        # Critical anomalies
        critical = [a for a in anomalies if a.severity == InsightSeverity.CRITICAL]
        if critical:
            insights.append(Insight(
                id=f"insight_critical_anomaly_{metric.name}_{datetime.utcnow().timestamp()}",
                type=InsightType.ANOMALY,
                title=f"Critical Anomalies Detected in {metric.name}",
                description=f"Detected {len(critical)} critical anomalies in {metric.name}. "
                           f"Values significantly deviate from expected range.",
                severity=InsightSeverity.CRITICAL,
                metrics_affected=[metric.name],
                detected_at=datetime.utcnow(),
                data_points=[{"timestamp": a.timestamp.isoformat(), "value": a.value, "severity": a.severity.value} for a in critical[:5]],
                suggested_actions=[
                    "Investigate root cause immediately",
                    "Check upstream data sources",
                    "Verify data pipeline health",
                    "Review recent deployments or changes",
                ],
                related_anomalies=[a.id for a in critical],
                confidence=0.9,
            ))

        # Warning anomalies
        warnings = [a for a in anomalies if a.severity == InsightSeverity.WARNING]
        if len(warnings) >= 3:
            insights.append(Insight(
                id=f"insight_warning_anomalies_{metric.name}_{datetime.utcnow().timestamp()}",
                type=InsightType.ANOMALY,
                title=f"Multiple Anomalies in {metric.name}",
                description=f"Detected {len(warnings)} warning-level anomalies. "
                           f"May indicate emerging issue.",
                severity=InsightSeverity.WARNING,
                metrics_affected=[metric.name],
                detected_at=datetime.utcnow(),
                data_points=[{"timestamp": a.timestamp.isoformat(), "value": a.value} for a in warnings[:5]],
                suggested_actions=[
                    "Monitor trend closely",
                    "Check for pattern in anomaly timing",
                    "Review related metrics",
                ],
                related_anomalies=[a.id for a in warnings],
                confidence=0.75,
            ))

        return insights

    async def _trend_insights(self, metric: TimeSeriesMetric, trends: List[TrendChange]) -> List[Insight]:
        """Generate insights from trend changes."""
        insights = []

        for trend in trends:
            if trend.direction == "decreasing" and trend.magnitude > 0.1:
                insights.append(Insight(
                    id=f"insight_declining_trend_{metric.name}_{trend.id}",
                    type=InsightType.TREND_CHANGE,
                    title=f"Declining Trend in {metric.name}",
                    description=f"Significant downward trend detected. "
                               f"Rate: {trend.after_trend:.4f} (was {trend.before_trend:.4f})",
                    severity=InsightSeverity.WARNING,
                    metrics_affected=[metric.name],
                    detected_at=datetime.utcnow(),
                    data_points=[{"change_point": trend.change_point.isoformat(), "magnitude": trend.magnitude}],
                    suggested_actions=[
                        "Investigate cause of decline",
                        "Check for seasonal patterns",
                        "Review recent changes affecting this metric",
                    ],
                    related_trend_changes=[trend.id],
                    confidence=trend.confidence,
                ))
            elif trend.direction == "increasing" and trend.magnitude > 0.1:
                insights.append(Insight(
                    id=f"insight_increasing_trend_{metric.name}_{trend.id}",
                    type=InsightType.TREND_CHANGE,
                    title=f"Increasing Trend in {metric.name}",
                    description=f"Significant upward trend detected. "
                               f"Rate: {trend.after_trend:.4f} (was {trend.before_trend:.4f})",
                    severity=InsightSeverity.INFO,
                    metrics_affected=[metric.name],
                    detected_at=datetime.utcnow(),
                    data_points=[{"change_point": trend.change_point.isoformat(), "magnitude": trend.magnitude}],
                    suggested_actions=[
                        "Validate if growth is expected",
                        "Check for capacity planning needs",
                        "Monitor for saturation",
                    ],
                    related_trend_changes=[trend.id],
                    confidence=trend.confidence,
                ))

        return insights

    async def _forecast_insights(self, metric: TimeSeriesMetric, forecast_engine) -> List[Insight]:
        """Generate insights from forecast deviations."""
        # This would use the ForecastingEngine to compare actuals vs forecasts
        # Simplified implementation
        return []

    async def _correlation_insights(
        self,
        metric_name: str,
        metric: TimeSeriesMetric,
        all_metrics: Dict[str, TimeSeriesMetric],
    ) -> List[Insight]:
        """Generate insights from cross-metric correlations."""
        insights = []

        metric_values = np.array([d.value for d in metric.data])

        for other_name, other_metric in all_metrics.items():
            if other_name == metric_name:
                continue

            if len(other_metric.data) != len(metric.data):
                continue

            other_values = np.array([d.value for d in other_metric.data])

            # Calculate correlation
            corr = np.corrcoef(metric_values, other_values)[0, 1]

            if abs(corr) > 0.8:
                insights.append(Insight(
                    id=f"insight_correlation_{metric_name}_{other_name}_{datetime.utcnow().timestamp()}",
                    type=InsightType.PATTERN_DISCOVERY,
                    title=f"Strong Correlation: {metric_name} ↔ {other_name}",
                    description=f"Correlation coefficient: {corr:.3f}. "
                               f"These metrics move {'together' if corr > 0 else 'inversely'}.",
                    severity=InsightSeverity.INFO,
                    metrics_affected=[metric_name, other_name],
                    detected_at=datetime.utcnow(),
                    data_points=[{"correlation": float(corr)}],
                    suggested_actions=[
                        "Investigate causal relationship",
                        "Consider combined monitoring",
                        "Review if one metric can proxy the other",
                    ],
                    confidence=min(abs(corr), 0.95),
                ))

        return insights


class AlertManager:
    """Alert routing and delivery."""

    def __init__(self):
        self._rules: List[AlertRule] = []
        self._sent_alerts: Dict[str, datetime] = {}  # for cooldown

    def add_rule(self, rule: AlertRule):
        self._rules.append(rule)

    def remove_rule(self, rule_id: str):
        self._rules = [r for r in self._rules if r.id != rule_id]

    def get_rules(self) -> List[AlertRule]:
        return self._rules

    async def process_insight(self, insight: Insight) -> List[Alert]:
        """Process insight and generate alerts based on rules."""
        alerts = []

        for rule in self._rules:
            if not rule.enabled:
                continue

            # Check if insight matches rule
            if not self._matches_rule(insight, rule):
                continue

            # Check severity threshold
            if not self._meets_severity(insight.severity, rule.severity_threshold):
                continue

            # Check cooldown
            cooldown_key = f"{rule.id}_{insight.id}"
            if cooldown_key in self._sent_alerts:
                last_sent = self._sent_alerts[cooldown_key]
                if datetime.utcnow() - last_sent < timedelta(minutes=rule.cooldown_minutes):
                    continue

            # Create alerts for each channel
            for channel in rule.channels:
                recipients = rule.recipients.get(channel, [])
                for recipient in recipients:
                    alert = Alert(
                        id=f"alert_{insight.id}_{channel.value}_{recipient}",
                        insight_id=insight.id,
                        channel=channel,
                        recipient=recipient,
                        subject=f"[{insight.severity.value.upper()}] {insight.title}",
                        message=self._format_alert_message(insight, channel),
                        severity=insight.severity,
                    )
                    alerts.append(alert)

            # Update cooldown
            self._sent_alerts[cooldown_key] = datetime.utcnow()

        return alerts

    def _matches_rule(self, insight: Insight, rule: AlertRule) -> bool:
        """Check if insight matches alert rule."""
        import re
        for pattern in rule.metric_patterns:
            for metric in insight.metrics_affected:
                if re.search(pattern, metric):
                    return True
        return len(rule.metric_patterns) == 0  # No patterns = match all

    def _meets_severity(self, insight_severity: InsightSeverity, threshold: InsightSeverity) -> bool:
        severity_order = {
            InsightSeverity.INFO: 0,
            InsightSeverity.WARNING: 1,
            InsightSeverity.CRITICAL: 2,
        }
        return severity_order[insight_severity] >= severity_order[threshold]

    def _format_alert_message(self, insight: Insight, channel: AlertChannel) -> str:
        """Format alert message for channel."""
        if channel == AlertChannel.SLACK:
            return f"*{insight.title}*\n{insight.description}\n\n*Severity:* {insight.severity.value}\n*Metrics:* {', '.join(insight.metrics_affected)}"
        elif channel == AlertChannel.EMAIL:
            return f"""
{insight.title}

{insight.description}

Severity: {insight.severity.value}
Metrics Affected: {', '.join(insight.metrics_affected)}
Detected At: {insight.detected_at.isoformat()}

Suggested Actions:
{chr(10).join(f'• {action}' for action in insight.suggested_actions)}
"""
        else:
            return f"{insight.title}: {insight.description}"

    async def send_alert(self, alert: Alert) -> bool:
        """Send alert via configured channel."""
        # This would integrate with actual notification services
        # For now, just mark as sent
        try:
            if alert.channel == AlertChannel.EMAIL:
                await self._send_email(alert)
            elif alert.channel == AlertChannel.SLACK:
                await self._send_slack(alert)
            elif alert.channel == AlertChannel.WEBHOOK:
                await self._send_webhook(alert)
            elif alert.channel == AlertChannel.PUSH:
                await self._send_push(alert)
            elif alert.channel == AlertChannel.IN_APP:
                await self._send_in_app(alert)

            alert.sent = True
            alert.sent_at = datetime.utcnow()
            return True
        except Exception as e:
            alert.error = str(e)
            alert.retry_count += 1
            logger.error(f"Failed to send alert {alert.id}: {e}")
            return False

    async def _send_email(self, alert: Alert):
        # Integrate with email service
        logger.info(f"Would send email to {alert.recipient}: {alert.subject}")

    async def _send_slack(self, alert: Alert):
        # Integrate with Slack
        logger.info(f"Would send Slack to {alert.recipient}: {alert.message}")

    async def _send_webhook(self, alert: Alert):
        # Integrate with webhook
        logger.info(f"Would send webhook to {alert.recipient}")

    async def _send_push(self, alert: Alert):
        # Integrate with push notifications
        logger.info(f"Would send push to {alert.recipient}")

    async def _send_in_app(self, alert: Alert):
        # Store in-app notification
        logger.info(f"Would send in-app to {alert.recipient}")


class ProactiveInsightsEngine:
    """
    Main Proactive Insights Engine.

    Orchestrates:
    - Anomaly detection across metrics
    - Trend change detection
    - Automated insight generation
    - Alert routing & delivery
    - Continuous monitoring
    """

    def __init__(
        self,
        forecast_engine=None,
        check_interval: int = 300,  # 5 minutes
    ):
        self.anomaly_detector = AnomalyDetector()
        self.trend_detector = TrendDetector()
        self.insight_generator = InsightGenerator()
        self.alert_manager = AlertManager()
        self.forecast_engine = forecast_engine
        self.check_interval = check_interval

        self._metrics: Dict[str, TimeSeriesMetric] = {}
        self._insights: List[Insight] = []
        self._anomalies: List[Anomaly] = []
        self._trend_changes: List[TrendChange] = []
        self._alerts: List[Alert] = []
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False

    # ==================== Metric Management ====================

    def register_metric(
        self,
        name: str,
        data: List[DataPoint],
        frequency: str = "1h",
        thresholds: Dict[str, float] = None,
    ):
        """Register a metric for monitoring."""
        metric = TimeSeriesMetric(
            name=name,
            data=data,
            frequency=frequency,
            thresholds=thresholds or {},
        )
        # Calculate baseline stats
        values = np.array([d.value for d in data])
        metric.baseline_stats = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "median": float(np.median(values)),
        }
        self._metrics[name] = metric
        logger.info(f"Registered metric for monitoring: {name} ({len(data)} points)")

    def update_metric(self, name: str, value: float, timestamp: datetime = None, metadata: Dict[str, Any] = None):
        """Add new data point to metric."""
        if name not in self._metrics:
            self.register_metric(name, [DataPoint(timestamp=timestamp or datetime.utcnow(), value=value, metadata=metadata or {})])
            return

        metric = self._metrics[name]
        metric.data.append(DataPoint(
            timestamp=timestamp or datetime.utcnow(),
            value=value,
            metadata=metadata or {},
        ))

        # Keep only recent data (configurable window)
        max_points = 10000
        if len(metric.data) > max_points:
            metric.data = metric.data[-max_points:]

    def get_metric(self, name: str) -> Optional[TimeSeriesMetric]:
        return self._metrics.get(name)

    def list_metrics(self) -> List[str]:
        return list(self._metrics.keys())

    # ==================== Monitoring ====================

    async def start_monitoring(self):
        """Start continuous monitoring."""
        if self._running:
            return

        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Proactive insights monitoring started")

    async def stop_monitoring(self):
        """Stop continuous monitoring."""
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Proactive insights monitoring stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_all_metrics()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(60)  # Back off on error

    async def _check_all_metrics(self):
        """Check all registered metrics for anomalies and trends."""
        for name, metric in self._metrics.items():
            if len(metric.data) < 10:
                continue

            try:
                # Detect anomalies
                anomalies = await self.anomaly_detector.detect(metric)
                if anomalies:
                    self._anomalies.extend(anomalies)
                    # Process alerts
                    for anomaly in anomalies:
                        insight = await self._create_anomaly_insight(metric, anomaly)
                        if insight:
                            self._insights.append(insight)
                            alerts = await self.alert_manager.process_insight(insight)
                            for alert in alerts:
                                await self.alert_manager.send_alert(alert)

                # Detect trends
                trends = await self.trend_detector.detect(metric)
                if trends:
                    self._trend_changes.extend(trends)
                    for trend in trends:
                        insight = await self._create_trend_insight(metric, trend)
                        if insight:
                            self._insights.append(insight)

            except Exception as e:
                logger.error(f"Error checking metric {name}: {e}")

        # Generate cross-metric insights periodically
        if len(self._metrics) > 1:
            insights = await self.insight_generator.generate_insights(self._metrics, self.forecast_engine)
            for insight in insights:
                # Deduplicate
                if not any(i.id == insight.id for i in self._insights):
                    self._insights.append(insight)
                    alerts = await self.alert_manager.process_insight(insight)
                    for alert in alerts:
                        await self.alert_manager.send_alert(alert)

    async def _create_anomaly_insight(self, metric: TimeSeriesMetric, anomaly: Anomaly) -> Optional[Insight]:
        """Create insight from anomaly."""
        if anomaly.severity == InsightSeverity.CRITICAL:
            return Insight(
                id=f"insight_anomaly_{anomaly.id}",
                type=InsightType.ANOMALY,
                title=f"Critical Anomaly: {metric.name}",
                description=f"Value {anomaly.value:.3f} at {anomaly.timestamp.isoformat()} "
                           f"is outside expected range {anomaly.expected_range}.",
                severity=InsightSeverity.CRITICAL,
                metrics_affected=[metric.name],
                detected_at=datetime.utcnow(),
                data_points=[{"timestamp": anomaly.timestamp.isoformat(), "value": anomaly.value}],
                suggested_actions=["Investigate immediately", "Check data pipeline", "Verify upstream systems"],
                related_anomalies=[anomaly.id],
                confidence=anomaly.score,
            )
        return None

    async def _create_trend_insight(self, metric: TimeSeriesMetric, trend: TrendChange) -> Optional[Insight]:
        """Create insight from trend change."""
        return Insight(
            id=f"insight_trend_{trend.id}",
            type=InsightType.TREND_CHANGE,
            title=f"Trend Change: {metric.name}",
            description=f"Trend changed from {trend.before_trend:.4f} to {trend.after_trend:.4f} "
                       f"({trend.direction}) at {trend.change_point.isoformat()}",
            severity=InsightSeverity.WARNING if trend.direction == "decreasing" else InsightSeverity.INFO,
            metrics_affected=[metric.name],
            detected_at=datetime.utcnow(),
            data_points=[{"change_point": trend.change_point.isoformat(), "magnitude": trend.magnitude}],
            suggested_actions=["Investigate cause", "Check for seasonal patterns", "Review recent changes"],
            related_trend_changes=[trend.id],
            confidence=trend.confidence,
        )

    # ==================== Queries ====================

    def get_insights(
        self,
        severity: Optional[InsightSeverity] = None,
        metric: Optional[str] = None,
        limit: int = 100,
    ) -> List[Insight]:
        """Get recent insights."""
        insights = self._insights
        if severity:
            insights = [i for i in insights if i.severity == severity]
        if metric:
            insights = [i for i in insights if metric in i.metrics_affected]
        return sorted(insights, key=lambda i: i.detected_at, reverse=True)[:limit]

    def get_anomalies(
        self,
        metric: Optional[str] = None,
        severity: Optional[InsightSeverity] = None,
        limit: int = 100,
    ) -> List[Anomaly]:
        """Get recent anomalies."""
        anomalies = self._anomalies
        if metric:
            anomalies = [a for a in anomalies if a.metric_name == metric]
        if severity:
            anomalies = [a for a in anomalies if a.severity == severity]
        return sorted(anomalies, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_trend_changes(
        self,
        metric: Optional[str] = None,
        limit: int = 100,
    ) -> List[TrendChange]:
        """Get recent trend changes."""
        trends = self._trend_changes
        if metric:
            trends = [t for t in trends if t.metric_name == metric]
        return sorted(trends, key=lambda t: t.change_point, reverse=True)[:limit]

    def get_alerts(self, limit: int = 100) -> List[Alert]:
        return sorted(self._alerts, key=lambda a: a.sent_at or datetime.min, reverse=True)[:limit]

    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        return {
            "running": self._running,
            "metrics_monitored": len(self._metrics),
            "total_insights": len(self._insights),
            "total_anomalies": len(self._anomalies),
            "total_trend_changes": len(self._trend_changes),
            "total_alerts": len(self._alerts),
            "unacknowledged_insights": len([i for i in self._insights if not i.acknowledged]),
            "unacknowledged_anomalies": len([a for a in self._anomalies if not a.acknowledged]),
        }

    def acknowledge_insight(self, insight_id: str, user_id: str):
        for insight in self._insights:
            if insight.id == insight_id:
                insight.acknowledged = True
                break

    def acknowledge_anomaly(self, anomaly_id: str, user_id: str):
        for anomaly in self._anomalies:
            if anomaly.id == anomaly_id:
                anomaly.acknowledged = True
                anomaly.acknowledged_by = user_id
                anomaly.acknowledged_at = datetime.utcnow()
                break


# Global proactive insights engine instance
_proactive_engine: Optional[ProactiveInsightsEngine] = None


def get_proactive_engine() -> ProactiveInsightsEngine:
    """Get or create proactive insights engine singleton."""
    global _proactive_engine
    if _proactive_engine is None:
        _proactive_engine = ProactiveInsightsEngine()
    return _proactive_engine


def init_proactive_engine(
    forecast_engine=None,
    check_interval: int = 300,
) -> ProactiveInsightsEngine:
    """Initialize proactive insights engine."""
    global _proactive_engine
    _proactive_engine = ProactiveInsightsEngine(forecast_engine=forecast_engine, check_interval=check_interval)
    return _proactive_engine