"""Government pack definition (Phase 17.7).

Departments, municipalities and public services. Modules cover citizens,
departments, projects, budgets, policies, documents, public programs,
compliance, approvals, records and security. The AI assists with policy
search, administrative assistance and knowledge management.
"""

INDUSTRY_PACK = {
    "key": "government",
    "name": "Government Pack",
    "icon": "building-2",
    "color": "#64748b",
    "description": "Departments, municipalities and public services — citizens, public programs, projects, budgets, policies, documents, compliance, records, approvals and security.",
    "business_types": ["government_department", "municipality", "public_service", "agency", "regulator", "state_enterprise"],
    "countries": ["US", "GB", "IN", "DE", "FR", "CA", "AU", "SG", "AE", "BR"],
    "modules": [
        {"key": "citizens", "name": "Citizens", "category": "service", "description": "Citizen registry, service requests and entitlements.", "entities": ["citizen"], "permissions": []},
        {"key": "departments", "name": "Departments", "category": "operations", "description": "Department structure, mandates and service catalogs.", "entities": ["department"], "permissions": []},
        {"key": "public-services", "name": "Public Services", "category": "service", "description": "Service delivery, SLAs and citizen feedback.", "entities": ["public_service"], "permissions": []},
        {"key": "projects", "name": "Public Projects", "category": "operations", "description": "Infrastructure and program delivery projects.", "entities": ["project"], "permissions": []},
        {"key": "public-budgets", "name": "Budgets", "category": "finance", "description": "Budget planning, allocation and expenditure tracking.", "entities": ["budget"], "permissions": []},
        {"key": "policies", "name": "Policies", "category": "knowledge", "description": "Policy library, versions and review cycles.", "entities": ["policy"], "permissions": []},
        {"key": "public-documents", "name": "Documents", "category": "knowledge", "description": "Gazettes, circulars, forms and public records.", "entities": ["document"], "permissions": []},
        {"key": "public-compliance", "name": "Compliance", "category": "compliance", "description": "National regulations, FOI, procurement rules and audits.", "entities": ["compliance_control"], "permissions": []},
        {"key": "records", "name": "Records", "category": "knowledge", "description": "Official records, retention schedules and archives.", "entities": ["record"], "permissions": []},
        {"key": "public-security", "name": "Security", "category": "compliance", "description": "Clearances, access controls and classified handling.", "entities": ["security_control"], "permissions": []},
    ],
    "templates": [
        {"key": "service-request", "name": "Citizen Service Request", "kind": "document", "description": "Standard service request form.", "content": {"sections": ["Citizen", "Service", "Details", "Supporting documents", "Priority", "Consent"]}},
        {"key": "policy-draft", "name": "Policy Draft", "kind": "document", "description": "Policy drafting template.", "content": {"sections": ["Policy title", "Purpose", "Scope", "Definitions", "Provisions", "Implementation", "Review"]}},
        {"key": "budget-request", "name": "Budget Request", "kind": "document", "description": "Budget allocation request.", "content": {"sections": ["Department", "Program", "Amount", "Justification", "Outcomes", "Prior year comparison"]}},
        {"key": "government-dashboard", "name": "Department Dashboard", "kind": "dashboard", "description": "Service delivery, projects, budgets and compliance panels.", "content": {"panels": ["Service SLA", "Citizen requests", "Project delivery", "Budget utilization", "Compliance posture", "Policy reviews due"]}},
        {"key": "government-report", "name": "Public Service Report", "kind": "report", "description": "Periodic department performance report.", "content": {"metrics": ["service_sla_met", "citizen_satisfaction", "project_on_time", "budget_utilization", "compliance_score", "policy_reviews_due"]}},
    ],
    "workflows": [
        {"key": "citizen-service-request", "name": "Citizen Service Request", "description": "Request to resolution.", "steps": [
            {"key": "intake", "name": "Request Intake", "assignee_role": "service_desk"},
            {"key": "verification", "name": "Citizen Verification", "assignee_role": "records_officer"},
            {"key": "processing", "name": "Case Processing", "assignee_role": "case_officer"},
            {"key": "approval", "name": "Approval", "assignee_role": "department_head"},
            {"key": "delivery", "name": "Service Delivery", "assignee_role": "service_desk"},
            {"key": "feedback", "name": "Citizen Feedback", "assignee_role": "quality_officer"},
        ]},
        {"key": "procurement-cycle", "name": "Public Procurement", "description": "Tender to contract.", "steps": [
            {"key": "requirement", "name": "Requirement Definition", "assignee_role": "procurement_officer"},
            {"key": "tender", "name": "Tender Publication", "assignee_role": "procurement_office"},
            {"key": "evaluation", "name": "Bid Evaluation", "assignee_role": "evaluation_committee"},
            {"key": "award", "name": "Award Decision", "assignee_role": "accountable_officer"},
            {"key": "contract", "name": "Contract Signing", "assignee_role": "legal_lead"},
        ]},
        {"key": "policy-approval", "name": "Policy Approval", "description": "Draft to enactment.", "steps": [
            {"key": "draft", "name": "Policy Draft", "assignee_role": "policy_officer"},
            {"key": "consultation", "name": "Public Consultation", "assignee_role": "policy_officer"},
            {"key": "legal-review", "name": "Legal Review", "assignee_role": "legal_lead"},
            {"key": "approval", "name": "Ministerial Approval", "assignee_role": "department_head"},
            {"key": "enact", "name": "Enactment & Publication", "assignee_role": "records_officer"},
        ]},
    ],
    "compliance": [
        {"framework": "National Regulations", "region": "global", "rules": [
            {"key": "statutory-reporting", "name": "Statutory reports filed on time", "control": "Public Administration", "severity": "critical", "evidence": ["documents", "calendar"], "cadence_days": 30},
            {"key": "procurement-rules", "name": "Procurement rules adherence", "control": "Fiscal Integrity", "severity": "high", "evidence": ["audit_log", "contracts"], "cadence_days": 90},
        ]},
        {"framework": "Freedom of Information", "region": "global", "rules": [
            {"key": "foi-response-sla", "name": "FOI responses within statutory window", "control": "Transparency", "severity": "high", "evidence": ["tickets"], "cadence_days": 30},
        ]},
        {"framework": "Data Protection", "region": "global", "rules": [
            {"key": "citizen-data-controls", "name": "Citizen data access controls", "control": "Privacy", "severity": "critical", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "government-assistant", "name": "Public Service Assistant", "system_prompt": "You assist government departments with citizen services, public projects, budgets, policies and compliance. Use the organization's citizen, service, project and policy data. All answers respect confidentiality and public interest.", "terminology": ["service SLA", "gazette", "FOI", "procurement", "accountable officer", "public record", "mandate"], "knowledge_scope": {"domains": ["public administration", "policy", "procurement", "records management"], "sensitive": ["citizen_data", "classified"]}, "guardrails": ["Never disclose classified or citizen-identifying data", "Distinguish policy guidance from legal advice"], "skills": {"summarize": "Summarize service delivery, projects and budget status.", "retrieve": "Search and summarize policies and public records.", "assist": "Answer administrative questions from public service records."}},
    ]},
    "kpis": [
        {"key": "service_sla_met", "name": "Service SLA Met", "unit": "%", "benchmark": 90},
        {"key": "citizen_satisfaction", "name": "Citizen Satisfaction", "unit": "%", "benchmark": 80},
        {"key": "project_on_time", "name": "Projects On Time", "unit": "%", "benchmark": 80},
        {"key": "budget_utilization", "name": "Budget Utilization", "unit": "%", "benchmark": 85},
        {"key": "compliance_score", "name": "Compliance Score", "unit": "%", "benchmark": 90},
        {"key": "policy_reviews_due", "name": "Policy Reviews Due", "unit": "count", "benchmark": 3},
    ],
    "navigation": {"label": "Government", "sections": ["Citizens", "Departments", "Public Services", "Projects", "Budgets", "Policies", "Documents", "Compliance", "Records", "Security"]},
}
