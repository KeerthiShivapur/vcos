"""Logistics pack definition (Phase 17.9).

Shipping, transport, supply chain and warehousing. Modules cover fleet,
warehouses, drivers, deliveries, routes, suppliers and customers. The AI does
route optimization, delivery forecasting and fleet utilization.
"""

INDUSTRY_PACK = {
    "key": "logistics",
    "name": "Logistics Pack",
    "icon": "truck",
    "color": "#3b82f6",
    "description": "Shipping, transport, supply chain and warehousing — fleet, drivers, deliveries, routes, warehouses, suppliers and customers.",
    "business_types": ["freight", "courier", "third_party_logistics", "warehouse", "fleet_operator", "supply_chain", "last_mile"],
    "countries": ["US", "IN", "NL", "DE", "GB", "SG", "AE", "BR", "MX", "CN"],
    "modules": [
        {"key": "fleet", "name": "Fleet", "category": "operations", "description": "Vehicles, trailers, telematics and lifecycle.", "entities": ["vehicle"], "permissions": []},
        {"key": "warehouses", "name": "Warehouses", "category": "operations", "description": "Warehouse network, capacity and throughput.", "entities": ["warehouse"], "permissions": []},
        {"key": "drivers", "name": "Drivers", "category": "people", "description": "Driver registry, licenses, hours and performance.", "entities": ["driver"], "permissions": []},
        {"key": "deliveries", "name": "Deliveries", "category": "operations", "description": "Consignments, tracking, POD and exceptions.", "entities": ["delivery"], "permissions": []},
        {"key": "routes", "name": "Routes", "category": "analytics", "description": "Route planning, optimization and utilization.", "entities": ["route"], "permissions": []},
        {"key": "suppliers", "name": "Suppliers", "category": "supply", "description": "Carrier and vendor contracts.", "entities": ["supplier"], "permissions": []},
        {"key": "customers", "name": "Customers", "category": "crm", "description": "Shipper accounts, contracts and SLAs.", "entities": ["customer"], "permissions": []},
    ],
    "templates": [
        {"key": "dispatch-sheet", "name": "Dispatch Sheet", "kind": "document", "description": "Daily dispatch and load plan.", "content": {"sections": ["Date", "Vehicle", "Driver", "Stops", "Load", "Checklist", "Sign-off"]}},
        {"key": "pod-form", "name": "Proof of Delivery", "kind": "document", "description": "Delivery confirmation form.", "content": {"sections": ["Consignment", "Recipient", "Condition", "Damages", "Signature", "Photo"]}},
        {"key": "warehouse-receipt", "name": "Goods Receipt", "kind": "document", "description": "Inbound goods receipt.", "content": {"sections": ["PO", "Carrier", "Items", "Condition", "Putaway", "Discrepancies"]}},
        {"key": "logistics-dashboard", "name": "Network Dashboard", "kind": "dashboard", "description": "Deliveries, fleet, routes and warehouse panels.", "content": {"panels": ["On-time delivery", "Fleet utilization", "Route efficiency", "Warehouse throughput", "Exceptions", "Fuel cost"]}},
        {"key": "logistics-report", "name": "Weekly Operations Report", "kind": "report", "description": "Weekly network performance report.", "content": {"metrics": ["on_time_delivery", "fleet_utilization", "route_efficiency", "delivery_cost_per_shipment", "exception_rate", "warehouse_throughput"]}},
    ],
    "workflows": [
        {"key": "shipment-lifecycle", "name": "Shipment Lifecycle", "description": "Booking to POD.", "steps": [
            {"key": "booking", "name": "Shipment Booking", "assignee_role": "customer_service"},
            {"key": "pickup", "name": "Pickup", "assignee_role": "driver"},
            {"key": "hub", "name": "Hub Processing", "assignee_role": "hub_manager"},
            {"key": "line-haul", "name": "Line-Haul", "assignee_role": "fleet_manager"},
            {"key": "delivery", "name": "Delivery", "assignee_role": "driver"},
            {"key": "pod", "name": "Proof of Delivery", "assignee_role": "customer_service"},
        ]},
        {"key": "route-optimization", "name": "Route Optimization", "description": "Demand to optimized routes.", "steps": [
            {"key": "demand", "name": "Demand Aggregation", "assignee_role": "planner"},
            {"key": "constraints", "name": "Constraint Check", "assignee_role": "planner"},
            {"key": "optimize", "name": "Route Optimization", "assignee_role": "optimization_engine"},
            {"key": "review", "name": "Planner Review", "assignee_role": "planner"},
            {"key": "publish", "name": "Dispatch Publish", "assignee_role": "dispatch_lead"},
        ]},
        {"key": "exception-handling", "name": "Delivery Exception Handling", "description": "Exception to resolution.", "steps": [
            {"key": "detect", "name": "Exception Detection", "assignee_role": "tracking_system"},
            {"key": "assess", "name": "Impact Assessment", "assignee_role": "customer_service"},
            {"key": "notify", "name": "Customer Notification", "assignee_role": "customer_service"},
            {"key": "resolve", "name": "Resolution", "assignee_role": "hub_manager"},
            {"key": "close", "name": "Claim & Close", "assignee_role": "customer_service"},
        ]},
    ],
    "compliance": [
        {"framework": "Transport Safety", "region": "global", "rules": [
            {"key": "driver-hours", "name": "Driver hours within legal limits", "control": "Transport Safety", "severity": "critical", "evidence": ["telematics", "driver_records"], "cadence_days": 30},
            {"key": "vehicle-inspections", "name": "Vehicle inspections current", "control": "Transport Safety", "severity": "high", "evidence": ["inspection"], "cadence_days": 90},
        ]},
        {"framework": "Customs & Trade", "region": "global", "rules": [
            {"key": "customs-compliance", "name": "Customs documentation compliance", "control": "Trade", "severity": "high", "evidence": ["documents"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "logistics-assistant", "name": "Logistics Operations Assistant", "system_prompt": "You assist logistics teams with fleet, drivers, deliveries, routes and warehousing. Use the organization's shipment, vehicle, driver and route data. Optimization suggestions are advisory.", "terminology": ["on-time delivery", "POD", "line-haul", "exception", "fleet utilization", "deadhead", "dock throughput"], "knowledge_scope": {"domains": ["transportation", "warehousing", "route optimization", "trade compliance"]}, "guardrails": ["Never recommend exceeding driver hours limits", "Route suggestions respect safety constraints"], "skills": {"summarize": "Summarize delivery performance and fleet utilization.", "forecast": "Forecast delivery demand and capacity needs.", "assist": "Answer operational questions from network data."}},
    ]},
    "kpis": [
        {"key": "on_time_delivery", "name": "On-Time Delivery", "unit": "%", "benchmark": 95},
        {"key": "fleet_utilization", "name": "Fleet Utilization", "unit": "%", "benchmark": 85},
        {"key": "route_efficiency", "name": "Route Efficiency", "unit": "index", "benchmark": 90},
        {"key": "delivery_cost_per_shipment", "name": "Cost per Shipment", "unit": "$", "benchmark": 8},
        {"key": "exception_rate", "name": "Exception Rate", "unit": "%", "benchmark": 3},
        {"key": "warehouse_throughput", "name": "Warehouse Throughput", "unit": "units/h", "benchmark": 200},
    ],
    "navigation": {"label": "Logistics", "sections": ["Fleet", "Warehouses", "Drivers", "Deliveries", "Routes", "Suppliers", "Customers"]},
}
