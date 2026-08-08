"""Media & entertainment pack definition (Phase 17.13).

Broadcasters, publishers, studios and agencies. Modules cover content,
productions, distribution, rights, talent, campaigns and audiences. The AI
does content intelligence, audience analytics and production monitoring.
"""

INDUSTRY_PACK = {
    "key": "media",
    "name": "Media & Entertainment Pack",
    "icon": "clapperboard",
    "color": "#ef4444",
    "description": "Broadcasters, publishers, studios, agencies and platforms — content, productions, distribution, rights, talent, campaigns and audience analytics.",
    "business_types": ["broadcaster", "publisher", "studio", "production_house", "advertising_agency", "streaming_platform", "news_org"],
    "countries": ["US", "GB", "IN", "BR", "DE", "FR", "JP", "KR", "NG", "AU"],
    "modules": [
        {"key": "content", "name": "Content", "category": "operations", "description": "Content registry, formats, versions and metadata.", "entities": ["content"], "permissions": []},
        {"key": "productions", "name": "Productions", "category": "operations", "description": "Production pipeline, shoots, budgets and deliverables.", "entities": ["production"], "permissions": []},
        {"key": "distribution", "name": "Distribution", "category": "operations", "description": "Platforms, territories, release windows and scheduling.", "entities": ["distribution"], "permissions": []},
        {"key": "rights", "name": "Rights", "category": "operations", "description": "Rights registry, licensing, expirations and clearances.", "entities": ["right"], "permissions": []},
        {"key": "talent", "name": "Talent", "category": "people", "description": "Talent registry, contracts, availability and payments.", "entities": ["talent"], "permissions": []},
        {"key": "campaigns", "name": "Campaigns", "category": "marketing", "description": "Ad campaigns, media plans and performance.", "entities": ["campaign"], "permissions": []},
        {"key": "audience-analytics", "name": "Audience Analytics", "category": "analytics", "description": "Audience segments, reach, engagement and ratings.", "entities": ["audience_metric"], "permissions": []},
    ],
    "templates": [
        {"key": "production-schedule", "name": "Production Schedule", "kind": "document", "description": "Shooting schedule template.", "content": {"sections": ["Production", "Shoot days", "Call times", "Locations", "Crew", "Deliverables"]}},
        {"key": "rights-register", "name": "Rights Register", "kind": "document", "description": "Rights tracking sheet.", "content": {"sections": ["Title", "Territory", "Rights", "Term", "Counterparty", "Expiry", "Notes"]}},
        {"key": "media-dashboard", "name": "Content Dashboard", "kind": "dashboard", "description": "Audience, productions, rights and campaigns panels.", "content": {"panels": ["Audience reach", "Engagement", "Productions in flight", "Rights expiring", "Campaign performance", "Content pipeline"]}},
        {"key": "media-report", "name": "Weekly Audience Report", "kind": "report", "description": "Weekly audience and content report.", "content": {"metrics": ["audience_reach", "engagement_index", "production_on_time", "rights_expiring", "campaign_roi", "content_output"]}},
    ],
    "workflows": [
        {"key": "content-release", "name": "Content Release", "description": "Concept to launch.", "steps": [
            {"key": "concept", "name": "Concept Approval", "assignee_role": "content_director"},
            {"key": "production", "name": "Production", "assignee_role": "producer"},
            {"key": "clearance", "name": "Rights & Clearance", "assignee_role": "rights_manager"},
            {"key": "qc", "name": "Quality Control", "assignee_role": "qc_lead"},
            {"key": "scheduling", "name": "Schedule & Slot", "assignee_role": "programming_lead"},
            {"key": "launch", "name": "Launch & Monitor", "assignee_role": "content_director"},
        ]},
        {"key": "campaign-flight", "name": "Campaign Flight", "description": "Brief to post-report.", "steps": [
            {"key": "brief", "name": "Campaign Brief", "assignee_role": "account_lead"},
            {"key": "plan", "name": "Media Plan", "assignee_role": "media_planner"},
            {"key": "approval", "name": "Client Approval", "assignee_role": "account_lead"},
            {"key": "launch", "name": "Campaign Launch", "assignee_role": "media_buyer"},
            {"key": "optimize", "name": "Optimization", "assignee_role": "analyst"},
            {"key": "post-report", "name": "Post-Campaign Report", "assignee_role": "analyst"},
        ]},
    ],
    "compliance": [
        {"framework": "Broadcast Standards", "region": "global", "rules": [
            {"key": "content-standards", "name": "Content classification compliance", "control": "Broadcast Code", "severity": "high", "evidence": ["qc_records"], "cadence_days": 90},
        ]},
        {"framework": "Rights & Copyright", "region": "global", "rules": [
            {"key": "rights-clearances", "name": "Rights clearances verified", "control": "IP", "severity": "critical", "evidence": ["rights_register"], "cadence_days": 30},
        ]},
    ],
    "ai": {"models": [
        {"key": "media-assistant", "name": "Media Operations Assistant", "system_prompt": "You assist media and entertainment teams with content, productions, distribution, rights, talent and audiences. Use the organization's content, production and audience data. Insight is advisory to creative decisions.", "terminology": ["reach", "engagement", "ratings", "clearance", "release window", "rights term", "deliverables"], "knowledge_scope": {"domains": ["content operations", "audience analytics", "rights management", "production"]}, "guardrails": ["Never override creative decisions", "Rights expiry flags are advisory"], "skills": {"summarize": "Summarize content pipeline, audience and campaign health.", "recommend": "Recommend distribution windows from audience data.", "assist": "Answer operational questions from media records."}},
    ]},
    "kpis": [
        {"key": "audience_reach", "name": "Audience Reach", "unit": "k", "benchmark": 500},
        {"key": "engagement_index", "name": "Engagement Index", "unit": "index", "benchmark": 70},
        {"key": "production_on_time", "name": "Productions On Time", "unit": "%", "benchmark": 85},
        {"key": "rights_expiring", "name": "Rights Expiring (90d)", "unit": "count", "benchmark": 3},
        {"key": "campaign_roi", "name": "Campaign ROI", "unit": "%", "benchmark": 200},
        {"key": "content_output", "name": "Content Output", "unit": "items", "benchmark": 30},
    ],
    "navigation": {"label": "Media & Entertainment", "sections": ["Content", "Productions", "Distribution", "Rights", "Talent", "Campaigns", "Audience Analytics"]},
}
