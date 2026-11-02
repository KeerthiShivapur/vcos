"""
SLO/Error Budget Definitions and Burn Rate Alerting for VCOS.

Implements Google SRE practices for Service Level Objectives:
- SLI definitions (latency, availability, error rate)
- SLO targets with time windows
- Error budget calculation and tracking
- Multi-window burn rate alerting
- Integration with Prometheus/Alertmanager
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from collections import deque

from prometheus_client import Counter, Gauge, Histogram

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class SLIType(str, Enum):
    """Types of Service Level Indicators."""
    LATENCY = "latency"
    AVAILABILITY = "availability"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    SATURATION = "saturation"
    FRESHNESS = "freshness"
    CORRECTNESS = "correctness"


class SLOTimeWindow(str, Enum):
    """SLO evaluation time windows."""
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    ONE_DAY = "1d"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BurnRateWindow(str, Enum):
    """Burn rate evaluation windows."""
    SHORT = "5m"   # 1 hour window for 5m lookback
    MEDIUM = "1h"  # 6 hour window for 1h lookback
    LONG = "6h"    # 3 day window for 6h lookback
    EXTENDED = "1d"  # 30 day window for 1d lookback


@dataclass
class SLIDefinition:
    """Definition of a Service Level Indicator."""
    name: str
    type: SLIType
    description: str
    query: str  # PromQL query
    good_query: Optional[str] = None  # Query for "good" events
    total_query: Optional[str] = None  # Query for total events
    labels: Dict[str, str] = field(default_factory=dict)

    def get_good_events_query(self) -> str:
        """Get query for good events."""
        return self.good_query or f"sum(rate({self.query}[5m]))"

    def get_total_events_query(self) -> str:
        """Get query for total events."""
        return self.total_query or f"sum(rate({self.query}_total[5m]))"


@dataclass
class SLOTarget:
    """SLO target definition."""
    sli_name: str
    target: float  # e.g., 0.999 for 99.9%
    time_window: SLOTimeWindow
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ErrorBudgetPolicy:
    """Error budget burn rate alerting policy."""
    # Multi-window burn rate alerts (Google SRE style)
    alerts: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.alerts:
            self.alerts = [
                # Short window, high burn rate
                {
                    "window": "5m",
                    "lookback": "1h",
                    "burn_rate_threshold": 14.4,  # 2% budget in 1h = 14.4x normal
                    "severity": "critical",
                    "description": "2% error budget consumed in 1 hour",
                },
                {
                    "window": "5m",
                    "lookback": "1h",
                    "burn_rate_threshold": 6,  # 1% budget in 1h = 6x normal
                    "severity": "warning",
                    "description": "1% error budget consumed in 1 hour",
                },
                # Medium window
                {
                    "window": "30m",
                    "lookback": "6h",
                    "burn_rate_threshold": 6,  # 5% budget in 6h = 6x normal
                    "severity": "critical",
                    "description": "5% error budget consumed in 6 hours",
                },
                {
                    "window": "30m",
                    "lookback": "6h",
                    "burn_rate_threshold": 3,  # 2.5% budget in 6h = 3x normal
                    "severity": "warning",
                    "description": "2.5% error budget consumed in 6 hours",
                },
                # Long window
                {
                    "window": "2h",
                    "lookback": "1d",
                    "burn_rate_threshold": 3,  # 10% budget in 1d = 3x normal
                    "severity": "critical",
                    "description": "10% error budget consumed in 1 day",
                },
                {
                    "window": "2h",
                    "lookback": "1d",
                    "burn_rate_threshold": 1.5,  # 5% budget in 1d = 1.5x normal
                    "severity": "warning",
                    "description": "5% error budget consumed in 1 day",
                },
                # Extended window
                {
                    "window": "6h",
                    "lookback": "3d",
                    "burn_rate_threshold": 2,  # 25% budget in 3d = 2x normal
                    "severity": "critical",
                    "description": "25% error budget consumed in 3 days",
                },
                {
                    "window": "6h",
                    "lookback": "3d",
                    "burn_rate_threshold": 1,  # 12.5% budget in 3d = 1x normal
                    "severity": "warning",
                    "description": "12.5% error budget consumed in 3 days",
                },
            ]


@dataclass
class SLODefinition:
    """Complete SLO definition with SLI, target, and alerting."""
    name: str
    service: str
    sli: SLIDefinition
    target: SLOTarget
    error_budget_policy: ErrorBudgetPolicy = field(default_factory=ErrorBudgetPolicy)
    alert_labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


class SLOCalculator:
    """Calculates SLO compliance and error budget consumption."""

    def __init__(self, prometheus_client=None):
        self.prometheus_client = prometheus_client

    async def calculate_sli(self, sli: SLIDefinition, window: SLOTimeWindow) -> float:
        """Calculate current SLI value."""
        if not self.prometheus_client:
            return 1.0  # Default to perfect if no client

        window_seconds = self._window_to_seconds(window)
        query = f"{sli.get_good_events_query()}[{window_seconds}s] / {sli.get_total_events_query()}[{window_seconds}s]"

        try:
            result = await self.prometheus_client.query(query)
            if result and "data" in result and result["data"]["result"]:
                value = float(result["data"]["result"][0]["value"][1])
                return min(max(value, 0.0), 1.0)
        except Exception as e:
            logger.error(f"Failed to calculate SLI {sli.name}: {e}")

        return 1.0

    async def calculate_error_budget_remaining(self, slo: SLODefinition, window: SLOTimeWindow) -> float:
        """Calculate remaining error budget as percentage."""
        sli_value = await self.calculate_sli(slo.sli, window)
        target = slo.target.target
        if target >= 1.0:
            return 100.0

        # Error budget consumed = (1 - SLI) / (1 - target) * 100%
        consumed = (1.0 - sli_value) / (1.0 - target) * 100
        remaining = max(0.0, 100.0 - consumed)
        return remaining

    async def calculate_burn_rate(
        self,
        slo: SLODefinition,
        window: str,
        lookback: str,
    ) -> float:
        """Calculate current burn rate multiplier."""
        # Burn rate = (error rate in window) / (error rate budget)
        # Error rate budget = (1 - target) / lookback_period

        target = slo.target.target
        error_budget_rate = (1.0 - target) / self._parse_duration(lookback)

        # Current error rate in window
        window_seconds = self._parse_duration(window)
        if not self.prometheus_client:
            return 0.0

        try:
            error_query = f"sum(rate({slo.sli.query}_errors[{window}]))"
            total_query = f"sum(rate({slo.sli.query}_total[{window}]))"
            combined_query = f"{error_query} / {total_query}"

            result = await self.prometheus_client.query(combined_query)
            if result and "data" in result and result["data"]["result"]:
                current_error_rate = float(result["data"]["result"][0]["value"][1])
                if error_budget_rate > 0:
                    return current_error_rate / error_budget_rate
        except Exception as e:
            logger.error(f"Failed to calculate burn rate: {e}")

        return 0.0

    def _window_to_seconds(self, window: SLOTimeWindow) -> int:
        mapping = {
            SLOTimeWindow.ONE_HOUR: 3600,
            SLOTimeWindow.SIX_HOURS: 21600,
            SLOTimeWindow.ONE_DAY: 86400,
            SLOTimeWindow.SEVEN_DAYS: 604800,
            SLOTimeWindow.THIRTY_DAYS: 2592000,
        }
        return mapping.get(window, 3600)

    def _parse_duration(self, duration: str) -> int:
        """Parse duration string like '1h', '6h', '1d' to seconds."""
        unit = duration[-1]
        value = int(duration[:-1])
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return value * multipliers.get(unit, 1)


class SLOManager:
    """Manages SLO definitions, evaluation, and alerting."""

    def __init__(self, calculator: SLOCalculator):
        self.calculator = calculator
        self.slos: Dict[str, SLODefinition] = {}
        self._evaluation_task: Optional[asyncio.Task] = None
        self._running = False

    def register_slo(self, slo: SLODefinition):
        """Register an SLO for monitoring."""
        self.slos[slo.name] = slo
        logger.info(f"Registered SLO: {slo.name} for service {slo.service}")

    async def evaluate_all(self) -> Dict[str, Dict[str, Any]]:
        """Evaluate all registered SLOs."""
        results = {}
        for name, slo in self.slos.items():
            results[name] = await self.evaluate_slo(slo)
        return results

    async def evaluate_slo(self, slo: SLODefinition) -> Dict[str, Any]:
        """Evaluate a single SLO."""
        window = slo.target.time_window
        sli_value = await self.calculator.calculate_sli(slo.sli, window)
        target = slo.target.target
        budget_remaining = await self.calculator.calculate_error_budget_remaining(slo, window)

        # Evaluate burn rate alerts
        alert_results = []
        for alert_config in slo.error_budget_policy.alerts:
            burn_rate = await self.calculator.calculate_burn_rate(
                slo,
                alert_config["window"],
                alert_config["lookback"],
            )

            threshold = alert_config["burn_rate_threshold"]
            firing = burn_rate >= threshold

            alert_results.append({
                "name": f"{slo.name}_{alert_config['description']}",
                "firing": firing,
                "burn_rate": burn_rate,
                "threshold": threshold,
                "severity": alert_config["severity"],
                "description": alert_config["description"],
            })

        return {
            "name": slo.name,
            "service": slo.service,
            "sli_value": sli_value,
            "target": target,
            "budget_remaining_percent": budget_remaining,
            "compliant": sli_value >= target,
            "window": window.value,
            "alerts": alert_results,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def start_evaluation_loop(self, interval: int = 60):
        """Start continuous SLO evaluation loop."""
        self._running = True
        self._evaluation_task = asyncio.create_task(self._evaluation_loop(interval))
        logger.info(f"Started SLO evaluation loop with {interval}s interval")

    async def stop_evaluation_loop(self):
        """Stop the evaluation loop."""
        self._running = False
        if self._evaluation_task:
            self._evaluation_task.cancel()
            try:
                await self._evaluation_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped SLO evaluation loop")

    async def _evaluation_loop(self, interval: int):
        while self._running:
            try:
                await self.evaluate_all()
                # Could push results to Prometheus, Alertmanager, etc.
            except Exception as e:
                logger.error(f"SLO evaluation error: {e}")
            await asyncio.sleep(interval)


# Prometheus metrics for SLO tracking
slo_compliance = Gauge(
    "vcos_slo_compliance",
    "SLO compliance (1 = compliant, 0 = non-compliant)",
    ["slo_name", "service", "window"],
)

slo_budget_remaining = Gauge(
    "vcos_slo_budget_remaining_percent",
    "Error budget remaining percentage",
    ["slo_name", "service", "window"],
)

slo_burn_rate = Gauge(
    "vcos_slo_burn_rate",
    "Current error budget burn rate multiplier",
    ["slo_name", "service", "window", "lookback"],
)

slo_alert_firing = Gauge(
    "vcos_slo_alert_firing",
    "Whether an SLO alert is firing (1 = firing, 0 = not firing)",
    ["slo_name", "alert_name", "severity"],
)


# Default SLO Definitions for VCOS
def create_default_slos() -> List[SLODefinition]:
    """Create standard VCOS SLO definitions."""

    slos = []

    # API Latency SLO
    latency_sli = SLIDefinition(
        name="api_latency",
        type=SLIType.LATENCY,
        description="API request latency at p99",
        query="http_request_duration_seconds_bucket",
        good_query='sum(rate(http_request_duration_seconds_bucket{le="0.5"}[5m]))',
        total_query="sum(rate(http_request_duration_seconds_bucket{le=\"+Inf\"}[5m]))",
    )

    slos.append(SLODefinition(
        name="api_latency_p99",
        service="api",
        sli=latency_sli,
        target=SLOTarget(
            sli_name="api_latency",
            target=0.99,  # 99% of requests < 500ms
            time_window=SLOTimeWindow.SEVEN_DAYS,
            description="99% of API requests complete within 500ms",
        ),
        alert_labels={"team": "platform", "component": "api"},
    ))

    # API Availability SLO
    availability_sli = SLIDefinition(
        name="api_availability",
        type=SLIType.AVAILABILITY,
        description="API request success rate",
        query="http_requests_total",
        good_query='sum(rate(http_requests_total{status!~"5.."}[5m]))',
        total_query="sum(rate(http_requests_total[5m]))",
    )

    slos.append(SLODefinition(
        name="api_availability",
        service="api",
        sli=availability_sli,
        target=SLOTarget(
            sli_name="api_availability",
            target=0.999,  # 99.9% uptime
            time_window=SLOTimeWindow.THIRTY_DAYS,
            description="99.9% of API requests succeed",
        ),
        alert_labels={"team": "platform", "component": "api"},
    ))

    # WebSocket Connection Availability
    ws_availability_sli = SLIDefinition(
        name="ws_availability",
        type=SLIType.AVAILABILITY,
        description="WebSocket connection success rate",
        query="websocket_connections_total",
        good_query="sum(rate(websocket_connections_established_total[5m]))",
        total_query="sum(rate(websocket_connections_attempted_total[5m]))",
    )

    slos.append(SLODefinition(
        name="websocket_availability",
        service="realtime",
        sli=ws_availability_sli,
        target=SLOTarget(
            sli_name="ws_availability",
            target=0.995,
            time_window=SLOTimeWindow.SEVEN_DAYS,
            description="99.5% of WebSocket connections establish successfully",
        ),
        alert_labels={"team": "platform", "component": "realtime"},
    ))

    # Background Job Success Rate
    job_success_sli = SLIDefinition(
        name="job_success_rate",
        type=SLIType.ERROR_RATE,
        description="Background job success rate",
        query="background_jobs_total",
        good_query="sum(rate(background_jobs_total{status=\"success\"}[5m]))",
        total_query="sum(rate(background_jobs_total[5m]))",
    )

    slos.append(SLODefinition(
        name="background_job_success",
        service="workers",
        sli=job_success_sli,
        target=SLOTarget(
            sli_name="job_success_rate",
            target=0.99,  # 99% job success
            time_window=SLOTimeWindow.SEVEN_DAYS,
            description="99% of background jobs complete successfully",
        ),
        alert_labels={"team": "platform", "component": "workers"},
    ))

    # Sync Success Rate
    sync_success_sli = SLIDefinition(
        name="sync_success_rate",
        type=SLIType.ERROR_RATE,
        description="Data sync success rate",
        query="sync_operations_total",
        good_query="sum(rate(sync_operations_total{status=\"success\"}[5m]))",
        total_query="sum(rate(sync_operations_total[5m]))",
    )

    slos.append(SLODefinition(
        name="sync_success",
        service="integrations",
        sli=sync_success_sli,
        target=SLOTarget(
            sli_name="sync_success_rate",
            target=0.999,
            time_window=SLOTimeWindow.SEVEN_DAYS,
            description="99.9% of data sync operations succeed",
        ),
        alert_labels={"team": "platform", "component": "integrations"},
    ))

    return slos


# Global SLO manager instance
_slo_manager: Optional[SLOManager] = None


def get_slo_manager() -> SLOManager:
    """Get or create the global SLO manager."""
    global _slo_manager
    if _slo_manager is None:
        calculator = SLOCalculator()
        _slo_manager = SLOManager(calculator)
        # Register default SLOs
        for slo in create_default_slos():
            _slo_manager.register_slo(slo)
    return _slo_manager


async def init_slo_monitoring(prometheus_client=None):
    """Initialize SLO monitoring with Prometheus client."""
    calculator = SLOCalculator(prometheus_client)
    manager = SLOManager(calculator)

    for slo in create_default_slos():
        manager.register_slo(slo)

    await manager.start_evaluation_loop(interval=60)  # Evaluate every minute
    return manager