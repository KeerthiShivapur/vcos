"""Manufacturing pack definition (Phase 17.3).

Factories, plants and industrial companies. Modules cover production, quality,
maintenance, machines, production planning, inventory, suppliers and safety.
The AI predicts machine failures, production delays and maintenance schedules.
"""

INDUSTRY_PACK = {
    "key": "manufacturing",
    "name": "Manufacturing Pack",
    "icon": "factory",
    "color": "#f59e0b",
    "description": "Factories, plants and industrial companies — production, quality, maintenance, machines, planning, inventory, suppliers and safety.",
    "business_types": ["factory", "plant", "industrial_company", "cpg_manufacturer", "metal_works", "chemical_plant", "electronics_maker", "food_processing"],
    "countries": ["US", "DE", "CN", "JP", "IN", "MX", "BR", "IT", "KR", "VN"],
    "modules": [
        {"key": "factories", "name": "Factories", "category": "operations", "description": "Plant registry, lines, cells and layouts.", "entities": ["factory"], "permissions": []},
        {"key": "machines", "name": "Machines", "category": "operations", "description": "Machine registry, sensors, utilization and health.", "entities": ["machine"], "permissions": []},
        {"key": "production-lines", "name": "Production Lines", "category": "operations", "description": "Line output, bottlenecks, shift performance and yield.", "entities": ["production_line"], "permissions": []},
        {"key": "maintenance", "name": "Maintenance", "category": "operations", "description": "Preventive, predictive and corrective maintenance.", "entities": ["maintenance_job"], "permissions": []},
        {"key": "inventory", "name": "Inventory", "category": "supply", "description": "Raw materials, WIP and finished goods.", "entities": ["inventory_item"], "permissions": []},
        {"key": "quality-control", "name": "Quality Control", "category": "operations", "description": "Inspections, defect tracking, batch QA and non-conformance.", "entities": ["quality_check"], "permissions": []},
        {"key": "suppliers", "name": "Suppliers", "category": "supply", "description": "Supplier registry, contracts, lead times and delivery reliability.", "entities": ["supplier"], "permissions": []},
        {"key": "production-planning", "name": "Production Planning", "category": "analytics", "description": "Capacity planning, scheduling, MRP and demand plans.", "entities": ["production_plan"], "permissions": []},
        {"key": "manufacturing-safety", "name": "Safety", "category": "compliance", "description": "Machine guarding, PPE, permits and incident reporting.", "entities": ["safety_incident"], "permissions": []},
    ],
    "templates": [
        {"key": "quality-inspection", "name": "Quality Inspection Checklist", "kind": "document", "description": "Line-level QC checklist.", "content": {"sections": ["Line", "Batch", "Specification", "Measurements", "Defects", "Disposition", "Inspector"]}},
        {"key": "maintenance-work-order", "name": "Maintenance Work Order", "kind": "document", "description": "Machine maintenance work order.", "content": {"sections": ["Machine", "Work type", "Priority", "Steps", "Parts", "Safety requirements", "Sign-off"]}},
        {"key": "shift-handover", "name": "Shift Handover Log", "kind": "document", "description": "End-of-shift production handover.", "content": {"sections": ["Shift", "Output", "Downtime", "Quality issues", "Machine status", "Open items"]}},
        {"key": "manufacturing-dashboard", "name": "Plant Operations Dashboard", "kind": "dashboard", "description": "OEE, downtime, quality and safety panels.", "content": {"panels": ["OEE", "Line utilization", "Downtime by cause", "First-pass yield", "Maintenance backlog", "Safety incidents"]}},
        {"key": "manufacturing-report", "name": "Weekly Plant Report", "kind": "report", "description": "Weekly production performance report.", "content": {"metrics": ["oee", "downtime_percent", "first_pass_yield", "schedule_attainment", "maintenance_backlog", "inventory_turns"]}},
    ],
    "workflows": [
        {"key": "production-order-execution", "name": "Production Order Execution", "description": "Plan to finished goods.", "steps": [
            {"key": "order-release", "name": "Order Release", "assignee_role": "planner"},
            {"key": "material-pull", "name": "Material Kitting", "assignee_role": "warehouse_lead"},
            {"key": "line-run", "name": "Line Run", "assignee_role": "shift_supervisor"},
            {"key": "quality-check", "name": "Quality Check", "assignee_role": "quality_engineer"},
            {"key": "pack-out", "name": "Pack-Out & Putaway", "assignee_role": "warehouse_lead"},
            {"key": "close-out", "name": "Order Close-Out", "assignee_role": "planner"},
        ]},
        {"key": "breakdown-response", "name": "Machine Breakdown Response", "description": "Alarm to production restart.", "steps": [
            {"key": "alarm", "name": "Breakdown Alarm", "assignee_role": "shift_supervisor"},
            {"key": "triage", "name": "Maintenance Triage", "assignee_role": "maintenance_manager"},
            {"key": "repair", "name": "Repair", "assignee_role": "maintenance_technician"},
            {"key": "test-run", "name": "Test Run", "assignee_role": "production_engineer"},
            {"key": "restart", "name": "Line Restart", "assignee_role": "shift_supervisor"},
        ]},
        {"key": "supplier-approval", "name": "Supplier Approval", "description": "Application to approved supplier.", "steps": [
            {"key": "application", "name": "Supplier Application", "assignee_role": "procurement_lead"},
            {"key": "audit", "name": "Supplier Audit", "assignee_role": "quality_engineer"},
            {"key": "trial", "name": "Trial Lot", "assignee_role": "production_engineer"},
            {"key": "approval", "name": "Approval", "assignee_role": "procurement_director"},
            {"key": "onboard", "name": "Onboarding", "assignee_role": "procurement_lead"},
        ]},
    ],
    "compliance": [
        {"framework": "ISO 9001", "region": "global", "rules": [
            {"key": "iso9001-documentation", "name": "Quality management system documentation", "control": "QMS", "severity": "high", "evidence": ["documents", "audit_log"], "cadence_days": 90},
            {"key": "iso9001-calibration", "name": "Inspection equipment calibration records", "control": "Measurement", "severity": "high", "evidence": ["equipment_records"], "cadence_days": 90},
        ]},
        {"framework": "ISO 14001", "region": "global", "rules": [
            {"key": "iso14001-environment", "name": "Environmental management system", "control": "EMS", "severity": "medium", "evidence": ["documents"], "cadence_days": 180},
        ]},
        {"framework": "OSHA / Safety", "region": "global", "rules": [
            {"key": "safety-permits", "name": "Hot work / confined space permits tracked", "control": "Safety", "severity": "critical", "evidence": ["permits", "incident_report"], "cadence_days": 30},
            {"key": "safety-training", "name": "Machine safety training current", "control": "Safety", "severity": "high", "evidence": ["training"], "cadence_days": 180},
        ]},
    ],
    "ai": {"models": [
        {"key": "manufacturing-assistant", "name": "Manufacturing Operations Assistant", "system_prompt": "You assist plant and operations teams with production, quality, maintenance and planning. Use the organization's machines, lines, inventory, suppliers and quality data. Predictions are advisory and always cite the data behind them.", "terminology": ["OEE", "downtime", "first-pass yield", "schedule attainment", "mean time between failures", "bottleneck", "kanban", "WIP"], "knowledge_scope": {"domains": ["production management", "maintenance", "quality engineering", "supply chain"]}, "guardrails": ["Predictions are advisory, never approvals", "Never recommend unsafe machine operation"], "skills": {"summarize": "Summarize production output, downtime and quality across lines.", "predict": "Predict machine failure risk and maintenance schedules from history.", "assist": "Answer operational questions from plant data."}},
    ]},
    "kpis": [
        {"key": "oee", "name": "Overall Equipment Effectiveness", "unit": "%", "benchmark": 75},
        {"key": "downtime_percent", "name": "Downtime", "unit": "%", "benchmark": 10},
        {"key": "first_pass_yield", "name": "First-Pass Yield", "unit": "%", "benchmark": 95},
        {"key": "schedule_attainment", "name": "Schedule Attainment", "unit": "%", "benchmark": 90},
        {"key": "maintenance_backlog", "name": "Maintenance Backlog", "unit": "jobs", "benchmark": 20},
        {"key": "inventory_turns", "name": "Inventory Turns", "unit": "turns", "benchmark": 8},
    ],
    "navigation": {"label": "Manufacturing", "sections": ["Factories", "Machines", "Production Lines", "Maintenance", "Inventory", "Quality Control", "Suppliers", "Production Planning"]},
}
