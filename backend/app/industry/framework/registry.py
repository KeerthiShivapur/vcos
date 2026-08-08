"""Industry pack registry (Phase 17.1 / 17.2).

One registry for every supported industry. Twelve industries ship full pack
definitions in their own package (healthcare, manufacturing, education,
retail, finance, government, construction, logistics, hospitality, legal,
research, media); the remaining verticals are data-driven packs defined here
(agriculture, energy, telecommunications, nonprofit, software). All packs
share the same shape so the framework engines treat them identically — no
core code ever changes for an industry.

Pack shape (see app/industry/healthcare/pack.py for a full example):
    key, name, icon, color, description, business_types, countries,
    modules[{key,name,category,description,entities,permissions}],
    templates[{key,name,kind,description,content,tags}],
    workflows[{key,name,description,steps[{key,name,assignee_role}]}],
    compliance[{framework, region, rules[{key,name,control,severity,evidence,cadence_days}]}],
    ai{models[{key,name,system_prompt,terminology,knowledge_scope,guardrails,skills}]},
    kpis[{key,name,unit,benchmark}], navigation{label,icon,sections}
"""

from typing import Any, Optional

from app.industry.education.pack import INDUSTRY_PACK as EDUCATION_PACK
from app.industry.finance.pack import INDUSTRY_PACK as FINANCE_PACK
from app.industry.government.pack import INDUSTRY_PACK as GOVERNMENT_PACK
from app.industry.healthcare.pack import INDUSTRY_PACK as HEALTHCARE_PACK
from app.industry.legal.pack import INDUSTRY_PACK as LEGAL_PACK
from app.industry.construction.pack import INDUSTRY_PACK as CONSTRUCTION_PACK
from app.industry.hospitality.pack import INDUSTRY_PACK as HOSPITALITY_PACK
from app.industry.logistics.pack import INDUSTRY_PACK as LOGISTICS_PACK
from app.industry.manufacturing.pack import INDUSTRY_PACK as MANUFACTURING_PACK
from app.industry.media.pack import INDUSTRY_PACK as MEDIA_PACK
from app.industry.research.pack import INDUSTRY_PACK as RESEARCH_PACK
from app.industry.retail.pack import INDUSTRY_PACK as RETAIL_PACK

# ---------------------------------------------------------------------------
# Data-driven packs (same shape, no dedicated package)
# ---------------------------------------------------------------------------

AGRICULTURE_PACK: dict[str, Any] = {
    "key": "agriculture",
    "name": "Agriculture Pack",
    "icon": "sprout",
    "color": "#65a30d",
    "description": "Farms, growers, agribusiness and supply chains — crop planning, livestock, equipment, harvest logistics and market pricing.",
    "business_types": ["farm", "plantation", "livestock", "agribusiness", "cooperative", "food_processing"],
    "countries": ["US", "BR", "IN", "CN", "AR", "AU", "NG", "FR", "NL", "TH"],
    "modules": [
        {"key": "farms", "name": "Farms & Fields", "category": "operations", "description": "Land parcels, plots, crop cycles and field activity."},
        {"key": "crops", "name": "Crop Management", "category": "operations", "description": "Planting schedules, varieties, irrigation and harvest tracking."},
        {"key": "livestock", "name": "Livestock", "category": "operations", "description": "Herd registry, feeding, health records and breeding."},
        {"key": "farm-equipment", "name": "Equipment", "category": "operations", "description": "Tractors, harvesters and implements with maintenance schedules."},
        {"key": "suppliers", "name": "Input Suppliers", "category": "supply", "description": "Seed, fertilizer and feed suppliers with contracts."},
        {"key": "harvest-logistics", "name": "Harvest Logistics", "category": "supply", "description": "Yield forecasts, transportation and market delivery."},
        {"key": "market-pricing", "name": "Market Pricing", "category": "analytics", "description": "Commodity prices, margin analysis and price alerts."},
        {"key": "agri-compliance", "name": "Agri Compliance", "category": "compliance", "description": "Pesticide records, certifications and export compliance."},
    ],
    "templates": [
        {"key": "field-work-order", "name": "Field Work Order", "kind": "document", "description": "Standard work order for field operations.", "content": {"sections": ["Field", "Crop", "Operation", "Crew", "Machinery", "Materials", "Sign-off"]}},
        {"key": "crop-plan", "name": "Crop Plan", "kind": "document", "description": "Seasonal crop planning template.", "content": {"sections": ["Season", "Crop mix", "Seed variety", "Planting window", "Irrigation plan", "Fertilizer plan", "Harvest estimate"]}},
        {"key": "agri-dashboard", "name": "Farm Operations Dashboard", "kind": "dashboard", "description": "Yield, equipment uptime and pricing panels.", "content": {"panels": ["Yield per hectare", "Equipment uptime", "Crop status mix", "Commodity price trend", "Harvest forecast"]}},
        {"key": "agri-report", "name": "Season Report", "kind": "report", "description": "End-of-season performance report.", "content": {"metrics": ["yield_per_hectare", "harvest_on_time_rate", "equipment_uptime", "input_cost_per_acre", "market_price_index"]}},
    ],
    "workflows": [
        {"key": "planting-campaign", "name": "Planting Campaign", "description": "Field prep to planting sign-off.", "steps": [
            {"key": "field-prep", "name": "Field Preparation", "assignee_role": "farm_manager"},
            {"key": "seed-procurement", "name": "Seed & Input Procurement", "assignee_role": "supply_lead"},
            {"key": "planting", "name": "Planting Execution", "assignee_role": "farm_manager"},
            {"key": "irrigation-setup", "name": "Irrigation Setup", "assignee_role": "field_lead"},
            {"key": "inspection", "name": "Stand Inspection", "assignee_role": "agronomist"},
            {"key": "campaign-review", "name": "Campaign Review", "assignee_role": "operations_director"},
        ]},
        {"key": "harvest-dispatch", "name": "Harvest Dispatch", "description": "Yield forecast to market delivery.", "steps": [
            {"key": "yield-estimate", "name": "Yield Estimate", "assignee_role": "agronomist"},
            {"key": "buyer-matching", "name": "Buyer Matching", "assignee_role": "sales_lead"},
            {"key": "logistics-booking", "name": "Logistics Booking", "assignee_role": "logistics_lead"},
            {"key": "dispatch", "name": "Dispatch", "assignee_role": "field_lead"},
            {"key": "delivery-confirmation", "name": "Delivery Confirmation", "assignee_role": "sales_lead"},
        ]},
    ],
    "compliance": [
        {"framework": "GlobalG.A.P.", "region": "global", "rules": [
            {"key": "ggap-traceability", "name": "Produce traceability records", "control": "Food Safety", "severity": "high", "evidence": ["audit_log", "crop_cycle_records"], "cadence_days": 90},
            {"key": "ggap-pesticide", "name": "Pesticide application records", "control": "Residue Control", "severity": "high", "evidence": ["application_logs"], "cadence_days": 30},
        ]},
        {"framework": "Organic Certification", "region": "global", "rules": [
            {"key": "organic-inputs", "name": "Certified inputs only", "control": "Organic Standards", "severity": "high", "evidence": ["supplier_records"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "agri-assistant", "name": "Agri Operations Assistant", "system_prompt": "You assist farm operations teams with agronomy, logistics and market intelligence. Use the organization's farms, crop cycles, equipment and pricing data.", "terminology": ["crop cycle", "yield per hectare", "harvest window", "input cost", "commodity price", "farm-to-market"], "knowledge_scope": {"domains": ["agronomy", "farm logistics", "commodity markets", "food safety"]}, "guardrails": ["Do not provide chemical dosage advice beyond labeled instructions", "Cite seasonal data when forecasting yields"], "skills": {"summarize": "Summarize today's farm operations across fields, crews and equipment.", "forecast": "Forecast harvest readiness from crop stage and weather risk.", "assist": "Answer operational questions using field, equipment and supplier records."}},
    ]},
    "kpis": [
        {"key": "yield_per_hectare", "name": "Yield per Hectare", "unit": "t/ha", "benchmark": 4.5},
        {"key": "harvest_on_time_rate", "name": "Harvest On-Time Rate", "unit": "%", "benchmark": 85},
        {"key": "equipment_uptime", "name": "Equipment Uptime", "unit": "%", "benchmark": 90},
        {"key": "input_cost_per_acre", "name": "Input Cost per Acre", "unit": "$", "benchmark": 180},
        {"key": "market_price_index", "name": "Market Price Index", "unit": "index", "benchmark": 100},
    ],
    "navigation": {"label": "Agriculture", "sections": ["Farms & Fields", "Crops", "Livestock", "Equipment", "Harvest Logistics", "Market Pricing"]},
}

ENERGY_PACK: dict[str, Any] = {
    "key": "energy",
    "name": "Energy & Utilities Pack",
    "icon": "zap",
    "color": "#eab308",
    "description": "Power plants, grids, utilities and renewable operators — assets, generation, grid health, maintenance, safety and regulatory compliance.",
    "business_types": ["utility", "generator", "renewable_operator", "grid_operator", "energy_trader", "oil_gas"],
    "countries": ["US", "DE", "SA", "AE", "IN", "BR", "FR", "NO", "AU", "CA"],
    "modules": [
        {"key": "energy-assets", "name": "Energy Assets", "category": "operations", "description": "Plants, turbines, panels, substations and asset lifecycle."},
        {"key": "generation", "name": "Generation", "category": "operations", "description": "Output monitoring, fuel mix and capacity planning."},
        {"key": "grid-health", "name": "Grid Health", "category": "operations", "description": "Grid status, load, outages and restoration."},
        {"key": "maintenance", "name": "Maintenance", "category": "operations", "description": "Preventive and corrective maintenance on critical assets."},
        {"key": "safety", "name": "Safety", "category": "compliance", "description": "Permit-to-work, incident reporting and drills."},
        {"key": "energy-compliance", "name": "Regulatory Compliance", "category": "compliance", "description": "Grid codes, emissions reporting and licensing."},
        {"key": "energy-trading", "name": "Energy Trading", "category": "analytics", "description": "Price exposure, hedging and counterparty risk."},
    ],
    "templates": [
        {"key": "permit-to-work", "name": "Permit to Work", "kind": "document", "description": "Safe work permit for energized assets.", "content": {"sections": ["Asset", "Work scope", "Isolation points", "PPE", "Authorizations", "Validity window"]}},
        {"key": "outage-plan", "name": "Outage Plan", "kind": "document", "description": "Planned outage coordination template.", "content": {"sections": ["Asset", "Outage window", "Load impact", "Crews", "Spare parts", "Restoration criteria"]}},
        {"key": "energy-dashboard", "name": "Fleet Generation Dashboard", "kind": "dashboard", "description": "Generation, uptime, emissions and outage panels.", "content": {"panels": ["Generation output", "Asset uptime", "Emissions", "Open outages", "Fuel mix"]}},
        {"key": "energy-report", "name": "Monthly Ops Report", "kind": "report", "description": "Monthly generation and reliability report.", "content": {"metrics": ["capacity_factor", "asset_uptime", "forced_outage_rate", "emissions_index", "grid_availability"]}},
    ],
    "workflows": [
        {"key": "outage-restoration", "name": "Outage Restoration", "description": "Detect outage to grid restoration.", "steps": [
            {"key": "detect", "name": "Outage Detection", "assignee_role": "grid_operator"},
            {"key": "assess", "name": "Impact Assessment", "assignee_role": "grid_operator"},
            {"key": "dispatch", "name": "Field Dispatch", "assignee_role": "operations_director"},
            {"key": "repair", "name": "Repair & Isolate", "assignee_role": "field_engineer"},
            {"key": "restore", "name": "Restoration", "assignee_role": "grid_operator"},
            {"key": "postmortem", "name": "Post-Mortem Review", "assignee_role": "reliability_lead"},
        ]},
        {"key": "permit-approval", "name": "Permit to Work Approval", "description": "Permit request to authorized execution.", "steps": [
            {"key": "request", "name": "Permit Request", "assignee_role": "field_engineer"},
            {"key": "isolation-check", "name": "Isolation Verification", "assignee_role": "safety_officer"},
            {"key": "approval", "name": "Authorized Approval", "assignee_role": "authorized_manager"},
            {"key": "execution", "name": "Work Execution", "assignee_role": "field_engineer"},
            {"key": "closure", "name": "Permit Closure", "assignee_role": "safety_officer"},
        ]},
    ],
    "compliance": [
        {"framework": "Grid Codes", "region": "global", "rules": [
            {"key": "grid-connectivity", "name": "Grid connection compliance", "control": "Grid Code", "severity": "high", "evidence": ["audit_log", "certifications"], "cadence_days": 180},
        ]},
        {"framework": "Emissions Reporting", "region": "global", "rules": [
            {"key": "emissions-report", "name": "Emissions data reporting", "control": "Environmental", "severity": "high", "evidence": ["monitoring_metrics"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "energy-assistant", "name": "Energy Operations Assistant", "system_prompt": "You assist utilities and energy operators with generation, grid health, maintenance and regulatory operations.", "terminology": ["capacity factor", "forced outage rate", "permit to work", "grid code", "load shedding", "spinning reserve"], "knowledge_scope": {"domains": ["power systems", "asset reliability", "grid operations", "energy regulation"]}, "guardrails": ["Never authorize energized work without a valid permit", "Flag safety-critical readings to a human operator"], "skills": {"summarize": "Summarize fleet generation, outages and maintenance status.", "forecast": "Forecast load and generation capacity for the week.", "assist": "Answer operational questions from asset, grid and permit records."}},
    ]},
    "kpis": [
        {"key": "capacity_factor", "name": "Capacity Factor", "unit": "%", "benchmark": 75},
        {"key": "asset_uptime", "name": "Asset Uptime", "unit": "%", "benchmark": 95},
        {"key": "forced_outage_rate", "name": "Forced Outage Rate", "unit": "%", "benchmark": 5},
        {"key": "emissions_index", "name": "Emissions Index", "unit": "index", "benchmark": 100},
        {"key": "grid_availability", "name": "Grid Availability", "unit": "%", "benchmark": 99.5},
    ],
    "navigation": {"label": "Energy & Utilities", "sections": ["Energy Assets", "Generation", "Grid Health", "Maintenance", "Safety", "Regulatory Compliance"]},
}

TELECOMMUNICATIONS_PACK: dict[str, Any] = {
    "key": "telecommunications",
    "name": "Telecommunications Pack",
    "icon": "radio",
    "color": "#0ea5e9",
    "description": "Telcos, ISPs, network operators and tower companies — network assets, service quality, field operations, customer service and compliance.",
    "business_types": ["mobile_operator", "isp", "network_operator", "tower_company", "cable_operator"],
    "countries": ["US", "IN", "GB", "BR", "ZA", "ID", "MX", "JP", "NG", "SE"],
    "modules": [
        {"key": "network-assets", "name": "Network Assets", "category": "operations", "description": "Sites, towers, cells, fiber and backhaul inventory."},
        {"key": "network-health", "name": "Network Health", "category": "operations", "description": "Uptime, capacity, congestion and alarm status."},
        {"key": "field-operations", "name": "Field Operations", "category": "operations", "description": "Site visits, repairs and installation tickets."},
        {"key": "service-quality", "name": "Service Quality", "category": "analytics", "description": "QoS metrics, SLAs and customer-impacting degradations."},
        {"key": "telecom-compliance", "name": "Telecom Compliance", "category": "compliance", "description": "Licensing, spectrum, tower safety and data protection."},
        {"key": "customer-service", "name": "Customer Service", "category": "service", "description": "Ticketing, installs, moves and churn management."},
    ],
    "templates": [
        {"key": "site-audit", "name": "Site Audit Checklist", "kind": "document", "description": "Tower/cell site safety and integrity checklist.", "content": {"sections": ["Site ID", "Structure integrity", "Earthing", "Power", "Safety signage", "Lease compliance", "Photos"]}},
        {"key": "outage-brief", "name": "Customer Outage Brief", "kind": "document", "description": "Outage communication template.", "content": {"sections": ["Affected region", "Impact scope", "Estimated resolution", "Updates", "Compensation"]}},
        {"key": "telecom-dashboard", "name": "Network Operations Dashboard", "kind": "dashboard", "description": "Uptime, alarms, field tickets and QoS panels.", "content": {"panels": ["Network availability", "Open alarms", "Field tickets", "Congestion ratio", "SLA breaches"]}},
        {"key": "telecom-report", "name": "Weekly Network Report", "kind": "report", "description": "Weekly reliability and quality report.", "content": {"metrics": ["network_availability", "alarm_resolution_time", "qos_index", "sla_breach_rate", "field_ticket_backlog"]}},
    ],
    "workflows": [
        {"key": "major-outage-response", "name": "Major Outage Response", "description": "Alarm to service restoration.", "steps": [
            {"key": "alarm", "name": "Alarm Confirmation", "assignee_role": "noc_operator"},
            {"key": "escalate", "name": "Escalation", "assignee_role": "noc_lead"},
            {"key": "dispatch", "name": "Field Dispatch", "assignee_role": "operations_manager"},
            {"key": "repair", "name": "Repair & Restore", "assignee_role": "field_engineer"},
            {"key": "verify", "name": "Service Verification", "assignee_role": "noc_operator"},
            {"key": "postmortem", "name": "Post-Mortem", "assignee_role": "reliability_lead"},
        ]},
        {"key": "site-install", "name": "New Site Install", "description": "Site acquisition to go-live.", "steps": [
            {"key": "survey", "name": "Site Survey", "assignee_role": "planning_engineer"},
            {"key": "lease", "name": "Lease & Permits", "assignee_role": "legal_lead"},
            {"key": "construction", "name": "Construction", "assignee_role": "project_manager"},
            {"key": "integration", "name": "Network Integration", "assignee_role": "integration_engineer"},
            {"key": "acceptance", "name": "Acceptance Test", "assignee_role": "qa_engineer"},
            {"key": "launch", "name": "Commercial Launch", "assignee_role": "operations_manager"},
        ]},
    ],
    "compliance": [
        {"framework": "Spectrum Licensing", "region": "global", "rules": [
            {"key": "spectrum-renewal", "name": "Spectrum license renewals tracked", "control": "Licensing", "severity": "critical", "evidence": ["licenses", "calendar"], "cadence_days": 90},
        ]},
        {"framework": "Telecom Data Protection", "region": "global", "rules": [
            {"key": "subscriber-privacy", "name": "Subscriber data protection controls", "control": "Privacy", "severity": "high", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "telecom-assistant", "name": "Telecom Operations Assistant", "system_prompt": "You assist network operators with network health, field operations, service quality and regulatory compliance.", "terminology": ["network availability", "cell congestion", "backhaul", "SLA", "alarm storm", "site lease"], "knowledge_scope": {"domains": ["telecom networks", "field operations", "QoS engineering", "spectrum regulation"]}, "guardrails": ["Distinguish confirmed outages from alarms requiring confirmation", "Never promise customer compensation without policy check"], "skills": {"summarize": "Summarize current network health and open field tickets.", "forecast": "Forecast congestion risk from traffic trends.", "assist": "Answer operational questions from network, ticket and site records."}},
    ]},
    "kpis": [
        {"key": "network_availability", "name": "Network Availability", "unit": "%", "benchmark": 99.5},
        {"key": "alarm_resolution_time", "name": "Alarm Resolution Time", "unit": "h", "benchmark": 4},
        {"key": "qos_index", "name": "QoS Index", "unit": "index", "benchmark": 90},
        {"key": "sla_breach_rate", "name": "SLA Breach Rate", "unit": "%", "benchmark": 2},
        {"key": "field_ticket_backlog", "name": "Field Ticket Backlog", "unit": "count", "benchmark": 50},
    ],
    "navigation": {"label": "Telecommunications", "sections": ["Network Assets", "Network Health", "Field Operations", "Service Quality", "Telecom Compliance"]},
}

NONPROFIT_PACK: dict[str, Any] = {
    "key": "nonprofit",
    "name": "Nonprofit & NGO Pack",
    "icon": "heart",
    "color": "#f43f5e",
    "description": "NGOs, foundations, charities and social enterprises — programs, beneficiaries, fundraising, grants, volunteers, impact reporting and governance.",
    "business_types": ["ngo", "foundation", "charity", "social_enterprise", "relief_agency", "think_tank"],
    "countries": ["US", "GB", "KE", "IN", "BR", "DE", "CA", "AU", "NG", "PH"],
    "modules": [
        {"key": "programs", "name": "Programs", "category": "operations", "description": "Program lifecycle, activities and milestones."},
        {"key": "beneficiaries", "name": "Beneficiaries", "category": "operations", "description": "Beneficiary registry, eligibility and support plans."},
        {"key": "fundraising", "name": "Fundraising", "category": "finance", "description": "Campaigns, donors, pledges and recurring giving."},
        {"key": "grants", "name": "Grants", "category": "finance", "description": "Grant applications, reporting and compliance."},
        {"key": "volunteers", "name": "Volunteers", "category": "people", "description": "Volunteer onboarding, shifts and recognition."},
        {"key": "impact-reporting", "name": "Impact Reporting", "category": "analytics", "description": "Outcome metrics, stories and donor reports."},
        {"key": "ngo-governance", "name": "Governance", "category": "compliance", "description": "Board records, policies and statutory filings."},
    ],
    "templates": [
        {"key": "donor-report", "name": "Donor Impact Report", "kind": "document", "description": "Quarterly impact narrative for donors.", "content": {"sections": ["Program summary", "Beneficiaries reached", "Outcomes", "Stories", "Financial summary", "Next steps"]}},
        {"key": "grant-application", "name": "Grant Application", "kind": "document", "description": "Structured grant application template.", "content": {"sections": ["Organization", "Problem statement", "Intervention", "Budget", "M&E plan", "Sustainability"]}},
        {"key": "ngo-dashboard", "name": "Mission Dashboard", "kind": "dashboard", "description": "Programs, funding, volunteers and impact panels.", "content": {"panels": ["Active programs", "Funds raised", "Beneficiaries served", "Volunteer hours", "Grant pipeline"]}},
        {"key": "ngo-report", "name": "Board Pack", "kind": "report", "description": "Monthly board reporting pack.", "content": {"metrics": ["funds_raised", "beneficiaries_served", "volunteer_hours", "grant_conversion_rate", "overhead_ratio"]}},
    ],
    "workflows": [
        {"key": "grant-lifecycle", "name": "Grant Lifecycle", "description": "Application to final report.", "steps": [
            {"key": "identify", "name": "Grant Identification", "assignee_role": "fundraising_lead"},
            {"key": "proposal", "name": "Proposal Drafting", "assignee_role": "program_director"},
            {"key": "approval", "name": "Internal Approval", "assignee_role": "executive_director"},
            {"key": "submission", "name": "Submission", "assignee_role": "fundraising_lead"},
            {"key": "award", "name": "Award & Contract", "assignee_role": "finance_lead"},
            {"key": "interim-report", "name": "Interim Reporting", "assignee_role": "program_director"},
            {"key": "final-report", "name": "Final Report & Close", "assignee_role": "program_director"},
        ]},
        {"key": "volunteer-onboarding", "name": "Volunteer Onboarding", "description": "Application to first shift.", "steps": [
            {"key": "apply", "name": "Volunteer Application", "assignee_role": "volunteer_coordinator"},
            {"key": "screen", "name": "Screening", "assignee_role": "volunteer_coordinator"},
            {"key": "orientation", "name": "Orientation", "assignee_role": "volunteer_coordinator"},
            {"key": "signup", "name": "Shift Sign-Up", "assignee_role": "volunteer_coordinator"},
            {"key": "first-shift", "name": "First Shift", "assignee_role": "program_manager"},
        ]},
    ],
    "compliance": [
        {"framework": "NGO Governance", "region": "global", "rules": [
            {"key": "board-meetings", "name": "Board meetings documented", "control": "Governance", "severity": "high", "evidence": ["audit_log", "meetings"], "cadence_days": 90},
            {"key": "statutory-filings", "name": "Statutory filings on schedule", "control": "Governance", "severity": "critical", "evidence": ["documents"], "cadence_days": 30},
        ]},
        {"framework": "Donor Data Protection", "region": "global", "rules": [
            {"key": "donor-privacy", "name": "Donor data handling controls", "control": "Privacy", "severity": "high", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "ngo-assistant", "name": "NGO Operations Assistant", "system_prompt": "You assist nonprofit teams with programs, fundraising, grants, volunteers, governance and impact reporting.", "terminology": ["beneficiary", "grant pipeline", "overhead ratio", "impact metric", "donor stewardship", "M&E"], "knowledge_scope": {"domains": ["nonprofit management", "fundraising", "grant compliance", "impact measurement"]}, "guardrails": ["Respect beneficiary data privacy", "Never overstate impact metrics beyond recorded outcomes"], "skills": {"summarize": "Summarize program, funding and volunteer status.", "forecast": "Forecast fundraising and grant pipeline health.", "assist": "Answer operational questions from program and donor records."}},
    ]},
    "kpis": [
        {"key": "funds_raised", "name": "Funds Raised", "unit": "$", "benchmark": 100000},
        {"key": "beneficiaries_served", "name": "Beneficiaries Served", "unit": "count", "benchmark": 1000},
        {"key": "volunteer_hours", "name": "Volunteer Hours", "unit": "h", "benchmark": 500},
        {"key": "grant_conversion_rate", "name": "Grant Conversion Rate", "unit": "%", "benchmark": 30},
        {"key": "overhead_ratio", "name": "Overhead Ratio", "unit": "%", "benchmark": 15},
    ],
    "navigation": {"label": "Nonprofit & NGO", "sections": ["Programs", "Beneficiaries", "Fundraising", "Grants", "Volunteers", "Impact Reporting"]},
}

SOFTWARE_PACK: dict[str, Any] = {
    "key": "software",
    "name": "Software & Technology Pack",
    "icon": "code",
    "color": "#6366f1",
    "description": "Software companies, startups, agencies and platforms — product, engineering, delivery, support, subscriptions and developer operations.",
    "business_types": ["saas", "startup", "software_company", "agency", "platform", "devops_shop"],
    "countries": ["US", "IN", "GB", "DE", "IL", "SG", "BR", "CA", "AU", "UA"],
    "modules": [
        {"key": "product", "name": "Product", "category": "operations", "description": "Product strategy, backlogs, releases and roadmaps."},
        {"key": "engineering", "name": "Engineering", "category": "operations", "description": "Squads, sprints, code quality and incident response."},
        {"key": "delivery", "name": "Delivery", "category": "operations", "description": "Professional services, deployments and release trains."},
        {"key": "support", "name": "Support", "category": "service", "description": "Tiered support, SLAs and escalation."},
        {"key": "subscriptions", "name": "Subscriptions", "category": "finance", "description": "Plans, billing, churn and revenue analytics."},
        {"key": "devops", "name": "DevOps", "category": "operations", "description": "Environments, CI/CD and infrastructure health."},
    ],
    "templates": [
        {"key": "incident-postmortem", "name": "Incident Post-Mortem", "kind": "document", "description": "Blameless incident review template.", "content": {"sections": ["Incident", "Impact", "Timeline", "Root cause", "Contributing factors", "Action items", "Follow-ups"]}},
        {"key": "sprint-review", "name": "Sprint Review Deck", "kind": "document", "description": "Sprint demo and metrics deck.", "content": {"sections": ["Sprint goals", "Shipped", "Metrics", "Demo", "Retro notes"]}},
        {"key": "tech-dashboard", "name": "Engineering Dashboard", "kind": "dashboard", "description": "Delivery, incidents, quality and uptime panels.", "content": {"panels": ["Deployment frequency", "Change failure rate", "Incident count", "Sprint velocity", "Support backlog"]}},
        {"key": "tech-report", "name": "Weekly Engineering Report", "kind": "report", "description": "Weekly engineering and product report.", "content": {"metrics": ["deployment_frequency", "change_failure_rate", "sprint_velocity", "support_sla_met", "incident_count"]}},
    ],
    "workflows": [
        {"key": "incident-response", "name": "Incident Response", "description": "Alert to post-mortem.", "steps": [
            {"key": "alert", "name": "Alert Triage", "assignee_role": "oncall_engineer"},
            {"key": "severity", "name": "Severity Assignment", "assignee_role": "incident_commander"},
            {"key": "mitigation", "name": "Mitigation", "assignee_role": "oncall_engineer"},
            {"key": "resolution", "name": "Resolution & Monitoring", "assignee_role": "incident_commander"},
            {"key": "postmortem", "name": "Post-Mortem", "assignee_role": "engineering_lead"},
        ]},
        {"key": "release-train", "name": "Release Train", "description": "Cut to production.", "steps": [
            {"key": "cut", "name": "Release Cut", "assignee_role": "release_engineer"},
            {"key": "qa", "name": "QA Sign-off", "assignee_role": "qa_lead"},
            {"key": "staging", "name": "Staging Validation", "assignee_role": "devops_engineer"},
            {"key": "deploy", "name": "Production Deploy", "assignee_role": "release_engineer"},
            {"key": "observe", "name": "Post-Deploy Monitoring", "assignee_role": "oncall_engineer"},
        ]},
    ],
    "compliance": [
        {"framework": "SOC 2", "region": "global", "rules": [
            {"key": "soc2-availability", "name": "Availability controls evidenced", "control": "A1", "severity": "high", "evidence": ["audit_log", "monitoring"], "cadence_days": 90},
        ]},
        {"framework": "ISO 27001", "region": "global", "rules": [
            {"key": "iso27001-assets", "name": "Asset inventory maintained", "control": "A.8", "severity": "medium", "evidence": ["assets"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "tech-assistant", "name": "Engineering Operations Assistant", "system_prompt": "You assist software teams with product, engineering, delivery, support and subscription operations.", "terminology": ["sprint velocity", "change failure rate", "incident severity", "churn", "release train", "SLI/SLO"], "knowledge_scope": {"domains": ["software delivery", "incident management", "SaaS business", "SRE"]}, "guardrails": ["Never imply incident severity without classification", "Separate speculation from measured metrics"], "skills": {"summarize": "Summarize delivery, incidents and support health.", "forecast": "Forecast sprint completion and churn risk.", "assist": "Answer operational questions from engineering and support records."}},
    ]},
    "kpis": [
        {"key": "deployment_frequency", "name": "Deployment Frequency", "unit": "/week", "benchmark": 10},
        {"key": "change_failure_rate", "name": "Change Failure Rate", "unit": "%", "benchmark": 10},
        {"key": "sprint_velocity", "name": "Sprint Velocity", "unit": "points", "benchmark": 80},
        {"key": "support_sla_met", "name": "Support SLA Met", "unit": "%", "benchmark": 95},
        {"key": "incident_count", "name": "Incidents", "unit": "count", "benchmark": 5},
    ],
    "navigation": {"label": "Software & Tech", "sections": ["Product", "Engineering", "Delivery", "Support", "Subscriptions", "DevOps"]},
}

_DATA_PACKS: dict[str, dict[str, Any]] = {
    AGRICULTURE_PACK["key"]: AGRICULTURE_PACK,
    ENERGY_PACK["key"]: ENERGY_PACK,
    TELECOMMUNICATIONS_PACK["key"]: TELECOMMUNICATIONS_PACK,
    NONPROFIT_PACK["key"]: NONPROFIT_PACK,
    SOFTWARE_PACK["key"]: SOFTWARE_PACK,
}

ALL_PACKS: dict[str, dict[str, Any]] = {
    HEALTHCARE_PACK["key"]: HEALTHCARE_PACK,
    MANUFACTURING_PACK["key"]: MANUFACTURING_PACK,
    EDUCATION_PACK["key"]: EDUCATION_PACK,
    RETAIL_PACK["key"]: RETAIL_PACK,
    FINANCE_PACK["key"]: FINANCE_PACK,
    GOVERNMENT_PACK["key"]: GOVERNMENT_PACK,
    CONSTRUCTION_PACK["key"]: CONSTRUCTION_PACK,
    LOGISTICS_PACK["key"]: LOGISTICS_PACK,
    HOSPITALITY_PACK["key"]: HOSPITALITY_PACK,
    LEGAL_PACK["key"]: LEGAL_PACK,
    RESEARCH_PACK["key"]: RESEARCH_PACK,
    MEDIA_PACK["key"]: MEDIA_PACK,
    **_DATA_PACKS,
}


def pack(key: str) -> Optional[dict[str, Any]]:
    return ALL_PACKS.get(key)


def get_pack(key: str) -> Optional[dict[str, Any]]:
    return ALL_PACKS.get(key)


def get_industry(key: str) -> dict[str, Any]:
    definition = get_pack(key)
    if definition is None:
        raise ValueError(f"unknown industry pack: {key}")
    return definition


def list_industry_keys() -> list[str]:
    return sorted(ALL_PACKS.keys())


def all_industries() -> list[dict[str, Any]]:
    return [ALL_PACKS[key] for key in list_industry_keys()]


def pack_business_types(key: str) -> list[str]:
    return get_pack(key).get("business_types", [])


def pack_modules(key: str) -> list[dict[str, Any]]:
    return get_pack(key).get("modules", [])


def pack_templates(key: str, kind: Optional[str] = None) -> list[dict[str, Any]]:
    items = get_pack(key).get("templates", [])
    if kind:
        items = [item for item in items if item.get("kind") == kind]
    return items


def pack_workflows(key: str) -> list[dict[str, Any]]:
    return get_pack(key).get("workflows", [])


def pack_workflow(key: str, template_key: str) -> dict[str, Any]:
    for item in pack_workflows(key):
        if item.get("key") == template_key:
            return item
    raise ValueError(f"unknown industry workflow template: {key}/{template_key}")


def pack_compliance(key: str) -> list[dict[str, Any]]:
    return get_pack(key).get("compliance", [])


def pack_ai_models(key: str) -> list[dict[str, Any]]:
    return get_pack(key).get("ai", {}).get("models", [])


def pack_kpis(key: str) -> list[dict[str, Any]]:
    return get_pack(key).get("kpis", [])


def pack_navigation(key: str) -> dict[str, Any]:
    return get_pack(key).get("navigation", {})
