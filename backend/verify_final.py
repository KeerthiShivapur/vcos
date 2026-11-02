# Test all core imports
print('=== Testing All Phase 1 Components ===')
print()

# Core infrastructure
from app.core.structured_logging import get_logger, init_structured_logging, LogLevel, LogFormat
print('[OK] Structured Logging')

from app.core.oncall import get_oncall_manager, init_oncall_manager
print('[OK] On-Call Management')

from app.core.predictive_scaling import (
    PredictiveScaler, CostOptimizer, CapacityPlanner,
    get_predictive_scaler, get_cost_optimizer, get_capacity_planner
)
print('[OK] Predictive Scaling')

from app.infrastructure.geodns_service import get_geodns_service
print('[OK] GeoDNS Service')

from app.infrastructure.edge_cdn_service import get_edge_cdn_service
print('[OK] Edge CDN')

from app.infrastructure.global_traffic_manager import get_global_traffic_manager
print('[OK] Global Traffic Manager')

# Test API routers
from app.api.v1.multiregion import router as multiregion_router
print('Multiregion API: {} routes'.format(len([r for r in __import__('app.api.v1.multiregion', fromlist=['router']).router.routes])))

from app.api.v1.sre import router as sre_router
print('SRE API: {} routes'.format(len([r for r in __import__('app.api.v1.sre', fromlist=['router']).router.routes])))

from app.api.v1.embedded_analytics import router as embedded_router
print('Embedded Analytics API: {} routes'.format(len([r for r in __import__('app.api.v1.embedded_analytics', fromlist=['router']).router.routes])))

print()
print('=== ALL PHASE 1 COMPONENTS VERIFIED ===')