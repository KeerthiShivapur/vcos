import asyncio
from app.db.database import get_engine, Base
from sqlalchemy import inspect

async def main():
    from app.models import (
        organization, user, role, notification, workspace, ai, invitation, employee,
        department, team, skill, project, task, goal, meeting, calendar,
        collaboration, approval, governance, workload, knowledge, communication,
        executive, autonomy, continuous_twin, canonical_reliability, observability,
        workflow, enterprise, feature_flags, infrastructure, deployment_completeness,
        backup_manifest, release, industry, industry_module, industry_template,
        industry_policy, industry_configuration, digital_twin, developer,
        company_state, autonomous_plan, briefing, company_memory, decision_history,
        innovation, learning_cycle, optimization, organization_edge, organization_health,
        organization_node, prediction, recommendation, simulation, strategy_report,
        executive_intelligence, ai_governance, resilience_plan, brain,
        company_actions, organizational_learning, people_intelligence, skills_intelligence,
        ownership_intelligence, collaboration_intelligence, org_capability_intelligence,
        people_decision, execution_intelligence, execution_coordination, execution_strategy,
        resource_allocation_intelligence, customer_intelligence, business_commercial,
        business_performance, financial_resource_procurement, canonical_resource_asset,
        canonical_procurement_vendor, canonical_economic_intelligence, canonical_business_process,
        canonical_knowledge, canonical_communication_collaboration, canonical_business_intelligence,
        canonical_workforce, canonical_integration, company_operating, company_intent,
        canonical_company_continuity, longitudinal, learning_profile, course, learning_path,
        skill_gap, certification, assessment, academy, mentorship, career, onboarding,
        learning_recommendation, hr, customer, lead, contract, ticket, partner, portal, finance,
        adaptive_operating_profile, company_experience, company_actions, company_intent,
        canonical_company_continuity, longitudinal, learning_profile, course, learning_path,
        skill_gap, certification, assessment, academy, mentorship, career, onboarding,
        learning_recommendation, hr, customer, lead, contract, ticket, partner, portal, finance,
    )
    
    engine = get_engine()
    print('Tables in metadata:', len(Base.metadata.tables))
    if 'workspaces' in Base.metadata.tables:
        print('workspaces IN metadata')
    else:
        print('workspaces MISSING from metadata!')
    
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))
        print("create_all completed")
    
    def get_tables(sync_conn):
        return inspect(sync_conn).get_table_names()
    tables = await engine.run_sync(get_tables)
    print('Tables in DB:', sorted(tables))

asyncio.run(main())