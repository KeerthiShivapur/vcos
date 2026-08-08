"""Digital Twin service package (Phase 18).

The twin service aggregate the entire organization into one living model;
the companion engines derive health, predictions, simulations, forecasts,
recommendations, optimizations, decision history and executive briefs from
the same twin payload so every insight shares one source of truth.
"""

from app.digital_twin.twin_service import DigitalTwinService, digital_twin_service
from app.digital_twin.health_service import HealthService, health_service
from app.digital_twin.prediction_service import PredictionService, prediction_service
from app.digital_twin.simulation_service import SimulationService, simulation_service
from app.digital_twin.forecasting_service import ForecastingService, forecasting_service
from app.digital_twin.recommendation_service import RecommendationService, recommendation_service
from app.digital_twin.optimization_service import OptimizationService, optimization_service
from app.digital_twin.decision_service import DecisionService, decision_service
from app.digital_twin.executive_service import ExecutiveService, executive_service
from app.digital_twin.ai_service import TwinAIService, twin_ai_service

__all__ = [
    "DigitalTwinService",
    "digital_twin_service",
    "HealthService",
    "health_service",
    "PredictionService",
    "prediction_service",
    "SimulationService",
    "simulation_service",
    "ForecastingService",
    "forecasting_service",
    "RecommendationService",
    "recommendation_service",
    "OptimizationService",
    "optimization_service",
    "DecisionService",
    "decision_service",
    "ExecutiveService",
    "executive_service",
    "TwinAIService",
    "twin_ai_service",
]
