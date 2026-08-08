"""Banking & finance pack definition (Phase 17.6).

Banks, insurance, investment and financial institutions. Modules cover
customers, branches, internal approvals, compliance, risk, training,
knowledge and audit. The AI assists with compliance, operational risk
monitoring and document intelligence.
"""

INDUSTRY_PACK = {
    "key": "finance",
    "name": "Banking & Finance Pack",
    "icon": "landmark",
    "color": "#10b981",
    "description": "Banks, insurance, investment and financial advisors — customers, branches, internal approvals, compliance, risk, training, knowledge and audit.",
    "business_types": ["bank", "insurance", "investment_firm", "financial_advisory", "fintech", "microfinance", "asset_management", "insurance_broker"],
    "countries": ["US", "GB", "SG", "CH", "DE", "IN", "AE", "JP", "BR", "ZA"],
    "modules": [
        {"key": "customers", "name": "Customers", "category": "crm", "description": "Customer/account registry, KYC records and relationship teams.", "entities": ["customer"], "permissions": []},
        {"key": "branches", "name": "Branches", "category": "operations", "description": "Branch network, performance and staffing.", "entities": ["branch"], "permissions": []},
        {"key": "internal-approvals", "name": "Internal Approvals", "category": "operations", "description": "Credit, mandate and policy approval chains.", "entities": ["approval"], "permissions": []},
        {"key": "finance-compliance", "name": "Compliance", "category": "compliance", "description": "KYC/AML, banking standards, licensing and reporting.", "entities": ["compliance_control"], "permissions": []},
        {"key": "operational-risk", "name": "Risk", "category": "analytics", "description": "Operational risk register, limits and loss events.", "entities": ["risk"], "permissions": []},
        {"key": "training", "name": "Training", "category": "people", "description": "Mandatory certifications, CPD and competence tracking.", "entities": ["training"], "permissions": []},
        {"key": "knowledge", "name": "Knowledge", "category": "knowledge", "description": "Policies, procedures, product manuals and circulars.", "entities": ["knowledge"], "permissions": []},
        {"key": "audit", "name": "Audit", "category": "compliance", "description": "Internal audit findings, remediation and tracking.", "entities": ["audit_finding"], "permissions": []},
    ],
    "templates": [
        {"key": "kyc-checklist", "name": "KYC Checklist", "kind": "document", "description": "Customer due diligence checklist.", "content": {"sections": ["Customer", "Identity documents", "PEP screening", "Source of funds", "Risk rating", "Verification", "Sign-off"]}},
        {"key": "credit-memo", "name": "Credit Memo", "kind": "document", "description": "Credit approval memorandum.", "content": {"sections": ["Borrower", "Facility", "Purpose", "Financials", "Collateral", "Risk assessment", "Recommendation"]}},
        {"key": "risk-report", "name": "Operational Risk Report", "kind": "document", "description": "Periodic risk report template.", "content": {"sections": ["Risk register", "Loss events", "Key indicators", "Limit breaches", "Mitigation", "Escalations"]}},
        {"key": "finance-dashboard", "name": "Institution Dashboard", "kind": "dashboard", "description": "Portfolio, risk, compliance and approvals panels.", "content": {"panels": ["Portfolio growth", "NPL ratio", "Approval turnaround", "Compliance posture", "Open audit findings", "KYC backlog"]}},
        {"key": "finance-report", "name": "Board Risk Report", "kind": "report", "description": "Monthly board-level risk pack.", "content": {"metrics": ["npl_ratio", "approval_turnaround", "compliance_score", "kyc_backlog", "open_audit_findings", "operational_loss"]}},
    ],
    "workflows": [
        {"key": "credit-approval", "name": "Credit Approval", "description": "Application to disbursement.", "steps": [
            {"key": "application", "name": "Credit Application", "assignee_role": "relationship_manager"},
            {"key": "kyc", "name": "KYC & Due Diligence", "assignee_role": "compliance_officer"},
            {"key": "underwriting", "name": "Underwriting", "assignee_role": "credit_analyst"},
            {"key": "approval", "name": "Credit Committee Approval", "assignee_role": "credit_committee"},
            {"key": "documentation", "name": "Documentation", "assignee_role": "legal_lead"},
            {"key": "disbursement", "name": "Disbursement", "assignee_role": "operations_lead"},
        ]},
        {"key": "suspicious-activity", "name": "Suspicious Activity Review", "description": "Alert to filing decision.", "steps": [
            {"key": "alert", "name": "Alert Generation", "assignee_role": "monitoring_system"},
            {"key": "investigate", "name": "Investigation", "assignee_role": "aml_analyst"},
            {"key": "review", "name": "Second Review", "assignee_role": "aml_manager"},
            {"key": "decision", "name": "File / No-File Decision", "assignee_role": "mlro"},
            {"key": "record", "name": "Record & Close", "assignee_role": "aml_analyst"},
        ]},
        {"key": "audit-finding-remediation", "name": "Audit Finding Remediation", "description": "Finding to closure.", "steps": [
            {"key": "raise", "name": "Finding Raised", "assignee_role": "auditor"},
            {"key": "acknowledge", "name": "Management Response", "assignee_role": "process_owner"},
            {"key": "plan", "name": "Remediation Plan", "assignee_role": "process_owner"},
            {"key": "implement", "name": "Implementation", "assignee_role": "process_owner"},
            {"key": "verify", "name": "Verification", "assignee_role": "auditor"},
            {"key": "close", "name": "Closure", "assignee_role": "audit_lead"},
        ]},
    ],
    "compliance": [
        {"framework": "KYC/AML", "region": "global", "rules": [
            {"key": "kyc-current", "name": "Customer due diligence current", "control": "AML", "severity": "critical", "evidence": ["kyc_records", "audit_log"], "cadence_days": 30},
            {"key": "suspicious-activity-reporting", "name": "SAR process operational", "control": "AML", "severity": "critical", "evidence": ["incident_report"], "cadence_days": 30},
        ]},
        {"framework": "Basel / Banking Standards", "region": "global", "rules": [
            {"key": "capital-reporting", "name": "Capital adequacy reporting", "control": "Basel III", "severity": "critical", "evidence": ["finance_reports"], "cadence_days": 30},
        ]},
        {"framework": "Licensing", "region": "global", "rules": [
            {"key": "licenses-current", "name": "Banking licenses current", "control": "Regulatory", "severity": "critical", "evidence": ["licenses", "calendar"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "finance-assistant", "name": "Financial Operations Assistant", "system_prompt": "You assist banks, insurers and investment firms with customer operations, internal approvals, compliance, risk and audit. Use the organization's customer, risk, compliance and approval data. You never make final approval decisions — you support human decision-makers.", "terminology": ["KYC", "AML", "NPL ratio", "PEP screening", "credit memo", "mandate", "operational risk", "audit finding"], "knowledge_scope": {"domains": ["banking operations", "risk management", "regulatory compliance", "internal audit"], "sensitive": ["financial_data"]}, "guardrails": ["Never approve or reject financial products on your own", "Treat customer financial data as confidential", "Flag anything resembling money laundering for human review"], "skills": {"summarize": "Summarize portfolio, risk and compliance posture.", "assist": "Answer operational questions from institution records.", "retrieve": "Retrieve policy, procedure and product knowledge."}},
    ]},
    "kpis": [
        {"key": "npl_ratio", "name": "NPL Ratio", "unit": "%", "benchmark": 3},
        {"key": "approval_turnaround", "name": "Approval Turnaround", "unit": "days", "benchmark": 5},
        {"key": "compliance_score", "name": "Compliance Score", "unit": "%", "benchmark": 92},
        {"key": "kyc_backlog", "name": "KYC Backlog", "unit": "count", "benchmark": 20},
        {"key": "open_audit_findings", "name": "Open Audit Findings", "unit": "count", "benchmark": 10},
        {"key": "operational_loss", "name": "Operational Loss", "unit": "$", "benchmark": 5000},
    ],
    "navigation": {"label": "Banking & Finance", "sections": ["Customers", "Branches", "Internal Approvals", "Compliance", "Risk", "Training", "Knowledge", "Audit"]},
}
