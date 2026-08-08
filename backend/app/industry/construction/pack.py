"""Construction pack definition (Phase 17.8).

Construction companies, infrastructure and real estate developers. Modules
cover sites, projects, equipment, workers, safety, vendors, budgets, project
timeline and documents. The AI does project monitoring, risk detection and
resource planning.
"""

INDUSTRY_PACK = {
    "key": "construction",
    "name": "Construction Pack",
    "icon": "hard-hat",
    "color": "#f97316",
    "description": "Construction companies, infrastructure and real estate — sites, buildings, equipment, contractors, safety, inspections, budgets, project timelines and documents.",
    "business_types": ["construction_company", "infrastructure", "real_estate_developer", "civil_contractor", "interior_fitout", "engineering_construction"],
    "countries": ["US", "AE", "IN", "GB", "DE", "SA", "BR", "AU", "SG", "TR"],
    "modules": [
        {"key": "sites", "name": "Sites", "category": "operations", "description": "Site registry, access, logistics and handover.", "entities": ["site"], "permissions": []},
        {"key": "buildings", "name": "Buildings", "category": "operations", "description": "Structure registry, floors and asset handover.", "entities": ["building"], "permissions": []},
        {"key": "equipment", "name": "Equipment", "category": "operations", "description": "Cranes, excavators, generators — registry and utilization.", "entities": ["equipment"], "permissions": []},
        {"key": "contractors", "name": "Contractors", "category": "operations", "description": "Contractor registry, contracts, credentials and performance.", "entities": ["contractor"], "permissions": []},
        {"key": "safety", "name": "Safety", "category": "compliance", "description": "Hazards, PPE, permits, incidents and near misses.", "entities": ["safety_incident"], "permissions": []},
        {"key": "inspections", "name": "Inspections", "category": "compliance", "description": "Inspection checklists, findings and sign-offs.", "entities": ["inspection"], "permissions": []},
        {"key": "construction-budgets", "name": "Budgets", "category": "finance", "description": "Project budgets, cost control and change orders.", "entities": ["budget"], "permissions": []},
        {"key": "project-timeline", "name": "Project Timeline", "category": "operations", "description": "Phases, milestones, delays and critical paths.", "entities": ["milestone"], "permissions": []},
        {"key": "construction-documents", "name": "Documents", "category": "knowledge", "description": "Drawings, BOQs, RFIs and as-builts.", "entities": ["document"], "permissions": []},
    ],
    "templates": [
        {"key": "safety-inspection", "name": "Site Safety Inspection", "kind": "document", "description": "Safety inspection checklist.", "content": {"sections": ["Site", "PPE compliance", "Hazards", "Permits", "Equipment condition", "Findings", "Corrective actions"]}},
        {"key": "rfi-form", "name": "RFI Form", "kind": "document", "description": "Request for information.", "content": {"sections": ["Project", "Subject", "Question", "Attachments", "Response", "Closure"]}},
        {"key": "snag-list", "name": "Snag List", "kind": "document", "description": "Defect and snag register.", "content": {"sections": ["Location", "Description", "Severity", "Responsible", "Deadline", "Verified"]}},
        {"key": "construction-dashboard", "name": "Project Dashboard", "kind": "dashboard", "description": "Schedule, cost, safety and quality panels.", "content": {"panels": ["Schedule progress", "Budget utilization", "Safety incidents", "Open findings", "Equipment utilization", "Milestones"]}},
        {"key": "construction-report", "name": "Weekly Site Report", "kind": "report", "description": "Weekly construction progress report.", "content": {"metrics": ["schedule_index", "budget_utilization", "safety_incidents", "finding_closure_rate", "equipment_utilization", "milestones_at_risk"]}},
    ],
    "workflows": [
        {"key": "tender-to-completion", "name": "Tender to Completion", "description": "The standard construction flow.", "steps": [
            {"key": "tender", "name": "Tender", "assignee_role": "bidding_engineer"},
            {"key": "approval", "name": "Approval", "assignee_role": "director"},
            {"key": "planning", "name": "Planning", "assignee_role": "planning_engineer"},
            {"key": "execution", "name": "Execution", "assignee_role": "site_manager"},
            {"key": "inspection", "name": "Inspection", "assignee_role": "quality_engineer"},
            {"key": "completion", "name": "Completion & Handover", "assignee_role": "project_manager"},
        ]},
        {"key": "change-order", "name": "Change Order", "description": "Request to approval.", "steps": [
            {"key": "request", "name": "Change Request", "assignee_role": "site_manager"},
            {"key": "costing", "name": "Costing", "assignee_role": "quantity_surveyor"},
            {"key": "client-review", "name": "Client Review", "assignee_role": "project_manager"},
            {"key": "approval", "name": "Approval", "assignee_role": "director"},
            {"key": "implement", "name": "Implementation", "assignee_role": "site_manager"},
        ]},
        {"key": "incident-investigation", "name": "Safety Incident Investigation", "description": "Incident to prevention.", "steps": [
            {"key": "report", "name": "Incident Report", "assignee_role": "site_manager"},
            {"key": "secure", "name": "Scene Security", "assignee_role": "safety_officer"},
            {"key": "investigate", "name": "Investigation", "assignee_role": "safety_officer"},
            {"key": "root-cause", "name": "Root Cause Analysis", "assignee_role": "safety_lead"},
            {"key": "actions", "name": "Corrective Actions", "assignee_role": "site_manager"},
            {"key": "close", "name": "Closure", "assignee_role": "safety_lead"},
        ]},
    ],
    "compliance": [
        {"framework": "Construction Safety", "region": "global", "rules": [
            {"key": "permit-to-work", "name": "High-risk permits valid", "control": "Site Safety", "severity": "critical", "evidence": ["permits", "inspection"], "cadence_days": 30},
            {"key": "safety-training", "name": "Workforce safety training current", "control": "Site Safety", "severity": "high", "evidence": ["training"], "cadence_days": 90},
        ]},
        {"framework": "Building Codes", "region": "global", "rules": [
            {"key": "inspections-current", "name": "Statutory inspections current", "control": "Codes", "severity": "high", "evidence": ["inspection"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "construction-assistant", "name": "Construction Operations Assistant", "system_prompt": "You assist construction teams with sites, schedules, budgets, safety and quality. Use the organization's site, project, equipment and inspection data. Risk flags are advisory inputs to the project team.", "terminology": ["schedule index", "BOQ", "RFI", "snag", "change order", "critical path", "handover", "earned value"], "knowledge_scope": {"domains": ["construction management", "site safety", "quantity surveying", "contracts"]}, "guardrails": ["Never override safety holds", "Risk predictions are advisory"], "skills": {"summarize": "Summarize site progress, cost and safety posture.", "predict": "Flag schedule delay and safety risks from project data.", "assist": "Answer operational questions from site records."}},
    ]},
    "kpis": [
        {"key": "schedule_index", "name": "Schedule Index", "unit": "index", "benchmark": 1.0},
        {"key": "budget_utilization", "name": "Budget Utilization", "unit": "%", "benchmark": 95},
        {"key": "safety_incidents", "name": "Safety Incidents", "unit": "count", "benchmark": 2},
        {"key": "finding_closure_rate", "name": "Finding Closure Rate", "unit": "%", "benchmark": 90},
        {"key": "equipment_utilization", "name": "Equipment Utilization", "unit": "%", "benchmark": 80},
        {"key": "milestones_at_risk", "name": "Milestones at Risk", "unit": "count", "benchmark": 1},
    ],
    "navigation": {"label": "Construction", "sections": ["Sites", "Buildings", "Equipment", "Contractors", "Safety", "Inspections", "Budgets", "Project Timeline", "Documents"]},
}
