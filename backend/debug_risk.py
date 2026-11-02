import asyncio
import uuid
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import Base, engine
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.execution_strategy import CompanyCommitment
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.intelligence.cross_domain_impact_service import cross_domain_impact_service
from app.intelligence.company_context import resolve_caller_access
from app.models.role import Role, UserRole
from app.services.permission_service import permission_service


async def test():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(bind=engine) as db:
        # Create org
        org = Organization(name='Test', slug='test-1')
        db.add(org)
        await db.flush()
        
        # Create user
        user = User(
            email='test@test.com', 
            password_hash='x', 
            full_name='Test', 
            status='active'
        )
        db.add(user)
        await db.flush()
        
        # Create employee
        emp = Employee(
            organization_id=org.id, 
            user_id=user.id, 
            employee_number='EMP1', 
            first_name='Test', 
            last_name='User', 
            email='test@test.com', 
            status='active'
        )
        db.add(emp)
        await db.flush()
        
        # Create commitment
        comm = CompanyCommitment(
            organization_id=org.id, 
            commitment_type='unconditional', 
            title='Test', 
            state='active', 
            scope_type='project', 
            scope_id='p1', 
            rationale='test', 
            fingerprint='fp1', 
            source_event_id='e1'
        )
        db.add(comm)
        await db.flush()
        
        # Add failed action
        action = CompanyAction(
            organization_id=org.id, 
            action_type='task', 
            title='Fail', 
            state='completed', 
            scope_type='project', 
            scope_id='p1', 
            fingerprint='fp1', 
            source_event_id='e1', 
            source_commitment_id=comm.id
        )
        db.add(action)
        await db.flush()
        
        outcome = CompanyActionOutcome(
            organization_id=org.id, 
            action_id=action.id, 
            outcome_type='failed', 
            effectiveness=0.1, 
            verdict='failed', 
            evidence_json='[]'
        )
        db.add(outcome)
        await db.commit()
        
        # Test risk assessment
        from app.intelligence.company_context import resolve_caller_access
        caller = await resolve_caller_access(db, organization_id=org.id, user=user)
        risk = await cross_domain_impact_service.derive_commitment_risk(db, caller=caller, commitment_id=comm.id)
        print(f'Risk level: {risk["risk_level"]}')
        print(f'Failed outcomes: {risk["failed_outcomes"]}')
        print(f'Risk factors: {risk["risk_factors"]}')

if __name__ == "__main__":
    asyncio.run(test())