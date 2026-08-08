"""Legal pack definition (Phase 17.11).

Law firms and legal departments. Modules cover cases, contracts, evidence,
documents, knowledge, meetings and research. The AI does document
summarization, legal knowledge retrieval and contract comparison.
"""

INDUSTRY_PACK = {
    "key": "legal",
    "name": "Legal Pack",
    "icon": "scale",
    "color": "#6b7280",
    "description": "Law firms and legal departments — cases, contracts, evidence, documents, knowledge, meetings and research.",
    "business_types": ["law_firm", "legal_department", "solo_practice", "corporate_legal", "legal_tech", "notary_office"],
    "countries": ["US", "GB", "IN", "AU", "CA", "DE", "FR", "SG", "AE", "BR"],
    "modules": [
        {"key": "cases", "name": "Cases", "category": "operations", "description": "Matters, parties, deadlines and billing.", "entities": ["case"], "permissions": []},
        {"key": "contracts", "name": "Contracts", "category": "operations", "description": "Contract repository, review, redlines and renewal.", "entities": ["contract"], "permissions": []},
        {"key": "evidence", "name": "Evidence", "category": "operations", "description": "Evidence registry, chain of custody and disclosure.", "entities": ["evidence"], "permissions": []},
        {"key": "legal-documents", "name": "Documents", "category": "knowledge", "description": "Pleadings, opinions, filings and precedents.", "entities": ["document"], "permissions": []},
        {"key": "legal-knowledge", "name": "Knowledge", "category": "knowledge", "description": "Precedents, research memos and practice guides.", "entities": ["knowledge"], "permissions": []},
        {"key": "legal-meetings", "name": "Meetings", "category": "operations", "description": "Client meetings, hearings and depo schedules.", "entities": ["meeting"], "permissions": []},
        {"key": "legal-research", "name": "Research", "category": "research", "description": "Research projects, citations and secondary sources.", "entities": ["research"], "permissions": []},
    ],
    "templates": [
        {"key": "engagement-letter", "name": "Engagement Letter", "kind": "document", "description": "Client engagement letter.", "content": {"sections": ["Client", "Scope", "Fees", "Terms", "Conflicts", "Signatures"]}},
        {"key": "nda", "name": "NDA Template", "kind": "document", "description": "Mutual non-disclosure agreement.", "content": {"sections": ["Parties", "Definition of information", "Obligations", "Exclusions", "Term", "Remedies"]}},
        {"key": "case-brief", "name": "Case Brief", "kind": "document", "description": "Internal case briefing memo.", "content": {"sections": ["Matter", "Facts", "Legal issues", "Analysis", "Risk", "Recommendation"]}},
        {"key": "legal-dashboard", "name": "Firm Dashboard", "kind": "dashboard", "description": "Matters, deadlines, billing and contracts panels.", "content": {"panels": ["Open matters", "Upcoming deadlines", "Billable hours", "Contract review queue", "Client satisfaction", "Utilization"]}},
        {"key": "legal-report", "name": "Practice Report", "kind": "report", "description": "Monthly practice performance report.", "content": {"metrics": ["utilization", "matter_duration", "deadline_compliance", "contract_review_turnaround", "billable_hours", "client_retention"]}},
    ],
    "workflows": [
        {"key": "matter-lifecycle", "name": "Matter Lifecycle", "description": "Intake to closing.", "steps": [
            {"key": "conflict-check", "name": "Conflict Check", "assignee_role": "intake_team"},
            {"key": "intake", "name": "Matter Intake", "assignee_role": "intake_team"},
            {"key": "engagement", "name": "Engagement", "assignee_role": "partner"},
            {"key": "case-management", "name": "Case Management", "assignee_role": "associate"},
            {"key": "billing", "name": "Billing Cycle", "assignee_role": "billing_team"},
            {"key": "closing", "name": "Closing & Archive", "assignee_role": "partner"},
        ]},
        {"key": "contract-review", "name": "Contract Review", "description": "Draft to executed.", "steps": [
            {"key": "receive", "name": "Contract Intake", "assignee_role": "paralegal"},
            {"key": "analysis", "name": "Analysis & Redline", "assignee_role": "associate"},
            {"key": "review", "name": "Partner Review", "assignee_role": "partner"},
            {"key": "negotiation", "name": "Negotiation", "assignee_role": "partner"},
            {"key": "execution", "name": "Execution", "assignee_role": "paralegal"},
            {"key": "archive", "name": "Repository Filing", "assignee_role": "paralegal"},
        ]},
    ],
    "compliance": [
        {"framework": "Professional Conduct", "region": "global", "rules": [
            {"key": "conflicts-current", "name": "Conflict checks maintained", "control": "Conduct", "severity": "critical", "evidence": ["audit_log"], "cadence_days": 30},
            {"key": "privilege-controls", "name": "Privilege safeguards in place", "control": "Conduct", "severity": "high", "evidence": ["security_policy"], "cadence_days": 90},
        ]},
        {"framework": "Client Data Protection", "region": "global", "rules": [
            {"key": "client-data-controls", "name": "Client data access controls", "control": "Privacy", "severity": "high", "evidence": ["audit_log", "security_policy"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "legal-assistant", "name": "Legal Operations Assistant", "system_prompt": "You assist law firms and legal teams with matters, contracts, evidence, research and documents. Use the organization's case, contract and knowledge data. You support lawyers — you are not a substitute for legal advice or professional judgment.", "terminology": ["matter", "privilege", "conflict check", "redline", "precedent", "billable hour", "engagement letter", "chain of custody"], "knowledge_scope": {"domains": ["legal practice", "contract law", "litigation support", "compliance"], "sensitive": ["privileged_material"]}, "guardrails": ["Never disclose privileged or confidential material", "You are not legal advice — route final opinions to qualified counsel"], "skills": {"summarize": "Summarize case status, deadlines and billable work.", "retrieve": "Retrieve relevant precedents and research memos.", "compare": "Compare contract versions and flag differences."}},
    ]},
    "kpis": [
        {"key": "utilization", "name": "Utilization", "unit": "%", "benchmark": 75},
        {"key": "matter_duration", "name": "Matter Duration", "unit": "days", "benchmark": 90},
        {"key": "deadline_compliance", "name": "Deadline Compliance", "unit": "%", "benchmark": 98},
        {"key": "contract_review_turnaround", "name": "Contract Review Turnaround", "unit": "days", "benchmark": 5},
        {"key": "billable_hours", "name": "Billable Hours", "unit": "h", "benchmark": 1500},
        {"key": "client_retention", "name": "Client Retention", "unit": "%", "benchmark": 85},
    ],
    "navigation": {"label": "Legal", "sections": ["Cases", "Contracts", "Evidence", "Documents", "Knowledge", "Meetings", "Research"]},
}
