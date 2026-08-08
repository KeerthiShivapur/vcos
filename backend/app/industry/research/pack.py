"""Research & innovation pack definition (Phase 17.12).

Universities, research labs and R&D teams. Modules cover research projects,
publications, experiments, funding, collaboration, patents and knowledge.
The AI does research discovery, literature summaries and collaboration
recommendations.
"""

INDUSTRY_PACK = {
    "key": "research",
    "name": "Research & Innovation Pack",
    "icon": "flask-conical",
    "color": "#22c55e",
    "description": "Research labs, R&D teams and institutes — projects, publications, experiments, funding, collaboration, patents and knowledge.",
    "business_types": ["research_lab", "rd_team", "research_institute", "university_research", "biotech", "think_tank"],
    "countries": ["US", "GB", "DE", "CH", "SG", "IN", "JP", "CA", "AU", "FR"],
    "modules": [
        {"key": "research-projects", "name": "Research Projects", "category": "research", "description": "Project registry, proposals, timelines and outcomes.", "entities": ["research_project"], "permissions": []},
        {"key": "publications", "name": "Publications", "category": "research", "description": "Papers, citations, venues and preprint tracking.", "entities": ["publication"], "permissions": []},
        {"key": "experiments", "name": "Experiments", "category": "research", "description": "Experiment registry, protocols, results and reproducibility.", "entities": ["experiment"], "permissions": []},
        {"key": "research-funding", "name": "Funding", "category": "finance", "description": "Grants, budgets, milestones and reporting.", "entities": ["grant"], "permissions": []},
        {"key": "researchers", "name": "Researchers", "category": "people", "description": "Researcher profiles, expertise and contribution tracking.", "entities": ["researcher"], "permissions": []},
        {"key": "research-knowledge", "name": "Knowledge", "category": "knowledge", "description": "Lab notebooks, datasets, protocols and literature.", "entities": ["knowledge"], "permissions": []},
        {"key": "research-collaboration", "name": "Collaboration", "category": "operations", "description": "Partnerships, consortia and joint projects.", "entities": ["collaboration"], "permissions": []},
        {"key": "patents", "name": "Patents", "category": "research", "description": "Disclosures, filings, inventors and status.", "entities": ["patent"], "permissions": []},
    ],
    "templates": [
        {"key": "proposal", "name": "Research Proposal", "kind": "document", "description": "Grant/funding proposal.", "content": {"sections": ["Title", "Problem", "Objectives", "Methodology", "Timeline", "Budget", "Impact"]}},
        {"key": "experiment-protocol", "name": "Experiment Protocol", "kind": "document", "description": "Experiment protocol template.", "content": {"sections": ["Hypothesis", "Materials", "Procedure", "Controls", "Data collection", "Analysis plan", "Ethics"]}},
        {"key": "publication-draft", "name": "Publication Draft", "kind": "document", "description": "Paper draft structure.", "content": {"sections": ["Title", "Abstract", "Introduction", "Methods", "Results", "Discussion", "References"]}},
        {"key": "research-dashboard", "name": "Research Dashboard", "kind": "dashboard", "description": "Projects, publications, funding and experiments panels.", "content": {"panels": ["Active projects", "Publications", "Grant pipeline", "Experiments", "Citations", "Collaboration"]}},
        {"key": "research-report", "name": "Quarterly Research Report", "kind": "report", "description": "Quarterly research output report.", "content": {"metrics": ["active_projects", "publications", "citations", "grant_utilization", "experiment_success_rate", "collaborations"]}},
    ],
    "workflows": [
        {"key": "proposal-to-award", "name": "Proposal to Award", "description": "Idea to funded project.", "steps": [
            {"key": "idea", "name": "Research Idea", "assignee_role": "principal_investigator"},
            {"key": "proposal", "name": "Proposal Development", "assignee_role": "research_office"},
            {"key": "internal-review", "name": "Internal Review", "assignee_role": "department_head"},
            {"key": "submission", "name": "Submission", "assignee_role": "research_office"},
            {"key": "award", "name": "Award & Contract", "assignee_role": "grants_office"},
            {"key": "kickoff", "name": "Project Kickoff", "assignee_role": "principal_investigator"},
        ]},
        {"key": "experiment-lifecycle", "name": "Experiment Lifecycle", "description": "Protocol to results.", "steps": [
            {"key": "design", "name": "Experimental Design", "assignee_role": "principal_investigator"},
            {"key": "ethics", "name": "Ethics Approval", "assignee_role": "ethics_board"},
            {"key": "setup", "name": "Setup & Calibration", "assignee_role": "lab_manager"},
            {"key": "run", "name": "Execution", "assignee_role": "researcher"},
            {"key": "analysis", "name": "Data Analysis", "assignee_role": "data_scientist"},
            {"key": "publish", "name": "Results Publication", "assignee_role": "principal_investigator"},
        ]},
    ],
    "compliance": [
        {"framework": "Research Integrity", "region": "global", "rules": [
            {"key": "ethics-approvals", "name": "Ethics approvals current", "control": "Integrity", "severity": "critical", "evidence": ["approvals", "documents"], "cadence_days": 90},
            {"key": "data-management", "name": "Research data management plan", "control": "Integrity", "severity": "high", "evidence": ["data_map"], "cadence_days": 90},
        ]},
        {"framework": "Grant Compliance", "region": "global", "rules": [
            {"key": "grant-reporting", "name": "Grant milestone reporting on time", "control": "Funding", "severity": "high", "evidence": ["reports"], "cadence_days": 30},
        ]},
    ],
    "ai": {"models": [
        {"key": "research-assistant", "name": "Research Operations Assistant", "system_prompt": "You assist research teams with projects, publications, experiments, funding and collaboration. Use the organization's project, publication and experiment data. Literature and discovery results are suggestions, not endorsements.", "terminology": ["preprint", "citation", "protocol", "grant pipeline", "peer review", "data provenance", "impact factor"], "knowledge_scope": {"domains": ["research management", "publication", "grant administration", "scientific integrity"]}, "guardrails": ["Never fabricate citations or results", "Ethics and integrity constraints always win"], "skills": {"summarize": "Summarize research output, funding and experiment health.", "discover": "Surface related publications and collaborators.", "assist": "Answer administrative questions from research records."}},
    ]},
    "kpis": [
        {"key": "active_projects", "name": "Active Projects", "unit": "count", "benchmark": 25},
        {"key": "publications", "name": "Publications", "unit": "count", "benchmark": 20},
        {"key": "citations", "name": "Citations", "unit": "count", "benchmark": 100},
        {"key": "grant_utilization", "name": "Grant Utilization", "unit": "%", "benchmark": 90},
        {"key": "experiment_success_rate", "name": "Experiment Success Rate", "unit": "%", "benchmark": 70},
        {"key": "collaborations", "name": "Collaborations", "unit": "count", "benchmark": 8},
    ],
    "navigation": {"label": "Research & Innovation", "sections": ["Research Projects", "Publications", "Experiments", "Funding", "Researchers", "Knowledge", "Collaboration", "Patents"]},
}
