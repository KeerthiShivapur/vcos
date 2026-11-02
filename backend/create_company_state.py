#!/usr/bin/env python
"""Create a representative company state for backup/restore testing."""

import asyncio
import asyncpg
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add path for imports
import sys
sys.path.insert(0, r'D:\vcos1\workspace\vcos\backend')

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.department import Department
from app.models.team import Team
from app.models.role import Role, Permission, RolePermission, UserRole
from app.models.project import Project
from app.models.task import Task
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyAuthorization, CompanyCommitment, CompanyGoal, CompanyObjective, CompanyInitiative
from app.models.company_actions import CompanyAction
from app.models.longitudinal import CompanyTimelineEvent, CompanyKnowledgeSnapshot
from app.models.canonical_integration import Connector, ConnectorInstance as CI, ConnectorCapability, ExternalIdentityMapping, SyncRun, SyncCursor, ExternalEvent, SourceAuthority, ExternalConflict, ExternalOperation, IntegrationHealth
from app.models.canonical_reliability import CanonicalOperation, OperationAttempt, ExternalUnknownState, WorkerLease
from app.models.observability import HealthDimension, CanonicalObservation, CorrelationContext
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.models.governance import GovernanceScope, ApprovalPolicy
from app.models.finance import Provisioning, Plan, CommercialAccount, Subscription, Entitlement, PROVISIONING_STATES, PROVISIONING_STEP_STATES
from app.models.canonical_integration import Connector, ConnectorInstance as CI, ConnectorCapability, ExternalIdentityMapping, SyncRun, SyncCursor, ExternalEvent, SourceAuthority, ExternalConflict, ExternalOperation, IntegrationHealth, SourceAuthority, ExternalConflict, ExternalOperation, IntegrationHealth
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyGoal, CompanyObjective, CompanyInitiative
from app.models.finance import Provisioning, Plan, CommercialAccount, Subscription, Entitlement
from app.models.backup_manifest import BackupManifest, BackupKind, BackupStatus
from app.core.timeutils import utcnow

from app.db.database import Base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Use the test database
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test"

async def create_company_state():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test",
        echo=False
    )
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # Get existing organizations
        result = await db.execute(select(Organization).where(Organization.status == "active"))
        orgs = result.scalars().all()
        print(f"Found {len(orgs)} organizations")
        
        for org in orgs:
            print(f"\n=== Setting up company state for {org.name} ({org.id}) ===")
            
            # Create departments
            dept_eng = Department(
                id=f"dept-eng-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Engineering",
                code="ENG",
                description="Engineering Department"
            )
            dept_sales = Department(
                id=f"dept-sales-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Sales",
                code="SAL",
                description="Sales Department"
            )
            dept_marketing = Department(
                id=f"dept-mkt-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Marketing",
                code="MKT",
                description="Marketing Department"
            )
            db.add_all([dept_eng, dept_sales, dept_marketing])
            await db.flush()
            
            # Create teams
            team_be = Team(
                id=f"team-be-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                department_id=dept_eng.id,
                name="Backend Engineering",
                code="BE",
                description="Backend Engineering Team"
            )
            team_fe = Team(
                id=f"team-fe-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                department_id=dept_eng.id,
                name="Frontend Engineering",
                code="FE",
                description="Frontend Engineering Team"
            )
            team_sales = Team(
                id=f"team-sales-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                department_id=dept_sales.id,
                name="Enterprise Sales",
                code="ENT",
                description="Enterprise Sales Team"
            )
            db.add_all([team_be, team_fe, team_sales])
            await db.flush()
            
            # Get the admin user
            result = await db.execute(select(User).where(User.organization_id == org.id, User.role == "admin"))
            admin_user = result.scalars().first()
            if not admin_user:
                print(f"  No admin user found for org {org.id}")
                continue
            
            # Create users for employees FIRST
            user1 = User(
                id=f"user-emp1-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                email=f"john.doe{uuid.uuid4().hex[:6]}@company.com",
                username=f"john.doe{uuid.uuid4().hex[:6]}",
                full_name="John Doe",
                password_hash="test_hash",
                role="employee",
                status="active"
            )
            user2 = User(
                id=f"user-emp2-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                email=f"jane.smith{uuid.uuid4().hex[:6]}@company.com",
                username=f"jane.smith{uuid.uuid4().hex[:6]}",
                full_name="Jane Smith",
                password_hash="test_hash",
                role="employee",
                status="active"
            )
            user3 = User(
                id=f"user-emp3-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                email=f"bob.wilson{uuid.uuid4().hex[:6]}@company.com",
                username=f"bob.wilson{uuid.uuid4().hex[:6]}",
                full_name="Bob Wilson",
                password_hash="test_hash",
                role="employee",
                status="active"
            )
            db.add_all([user1, user2, user3])
            await db.flush()
            
            # Create employees with correct user_ids
            emp1 = Employee(
                id=f"emp1-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                user_id=user1.id,
                employee_number=f"EMP{uuid.uuid4().hex[:6].upper()}",
                first_name="John",
                last_name="Doe",
                display_name="John Doe",
                email="john.doe@company.com",
                department_id=dept_eng.id,
                team_id=team_be.id,
                joining_date=datetime.now(timezone.utc).date(),
                employment_type="full_time",
                status="active"
            )
            emp2 = Employee(
                id=f"emp2-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                user_id=user2.id,
                employee_number=f"EMP{uuid.uuid4().hex[:6].upper()}",
                first_name="Jane",
                last_name="Smith",
                display_name="Jane Smith",
                email="jane.smith@company.com",
                department_id=dept_eng.id,
                team_id=team_fe.id,
                joining_date=datetime.now(timezone.utc).date(),
                employment_type="full_time",
                status="active"
            )
            emp3 = Employee(
                id=f"emp3-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                user_id=user3.id,
                employee_number=f"EMP{uuid.uuid4().hex[:6].upper()}",
                first_name="Bob",
                last_name="Wilson",
                display_name="Bob Wilson",
                email="bob.wilson@company.com",
                department_id=dept_sales.id,
                team_id=team_sales.id,
                joining_date=datetime.now(timezone.utc).date(),
                employment_type="full_time",
                status="active"
            )
            db.add_all([emp1, emp2, emp3])
            await db.flush()
            
            # Create governance scope FIRST (needed for UserRole scope_id)
            gs1 = GovernanceScope(
                organization_id=org.id,
                name="Platform Governance",
                scope_type="company",
                entity_id=org.id
            )
            db.add(gs1)
            await db.flush()
            
            # Create roles
            role_admin = Role(
                id=f"role-admin-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Administrator",
                code="admin",
                description="Full system access"
            )
            role_manager = Role(
                id=f"role-mgr-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Manager",
                code="manager",
                description="Team management access"
            )
            role_emp = Role(
                id=f"role-emp-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Employee",
                code="employee",
                description="Standard employee access"
            )
            db.add_all([role_admin, role_manager, role_emp])
            await db.flush()
            
            # Assign roles
            ur1 = UserRole(id=f"ur1-{uuid.uuid4().hex[:8]}", user_id=admin_user.id, role_id=role_admin.id, organization_id=org.id, scope_id=gs1.id)
            ur2 = UserRole(id=f"ur2-{uuid.uuid4().hex[:8]}", user_id=emp1.user_id, role_id=role_emp.id, organization_id=org.id, scope_id=gs1.id)
            ur3 = UserRole(id=f"ur3-{uuid.uuid4().hex[:8]}", user_id=emp2.user_id, role_id=role_emp.id, organization_id=org.id, scope_id=gs1.id)
            ur4 = UserRole(id=f"ur4-{uuid.uuid4().hex[:8]}", user_id=emp3.user_id, role_id=role_emp.id, organization_id=org.id, scope_id=gs1.id)
            db.add_all([ur1, ur2, ur3, ur4])
            await db.flush()
            
            # Create projects
            proj1 = Project(
                id=f"proj1-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Platform Modernization",
                code="PLAT-MOD",
                description="Modernize the core platform",
                status="active",
                department_id=dept_eng.id,
                team_id=team_be.id,
                start_date=datetime.now(timezone.utc).date(),
                end_date=datetime.now(timezone.utc).date() + timedelta(days=90)
            )
            proj2 = Project(
                id=f"proj2-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Customer Portal Redesign",
                code="CUST-PORT",
                description="Redesign the customer portal",
                status="active",
                department_id=dept_eng.id,
                team_id=team_fe.id,
                start_date=datetime.now(timezone.utc).date(),
                end_date=datetime.now(timezone.utc).date() + timedelta(days=60)
            )
            proj3 = Project(
                id=f"proj3-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                name="Q3 Sales Campaign",
                code="Q3-SALES",
                description="Q3 Enterprise Sales Campaign",
                status="active",
                department_id=dept_sales.id,
                team_id=team_sales.id,
                start_date=datetime.now(timezone.utc).date(),
                end_date=datetime.now(timezone.utc).date() + timedelta(days=90)
            )
            db.add_all([proj1, proj2, proj3])
            await db.flush()
            
            # Create tasks
            task1 = Task(
                id=f"task1-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                project_id=proj1.id,
                title="Migrate to PostgreSQL 18",
                description="Upgrade database to PostgreSQL 18",
                status="in_progress",
                priority="high",
                assignee_id=emp1.id,
                reporter_id=emp1.id
            )
            task2 = Task(
                id=f"task2-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                project_id=proj1.id,
                title="Implement new API gateway",
                description="Design and implement new API gateway",
                status="pending",
                priority="high",
                assignee_id=emp2.id,
                reporter_id=emp1.id
            )
            task3 = Task(
                id=f"task3-{uuid.uuid4().hex[:8]}",
                organization_id=org.id,
                project_id=proj2.id,
                title="Redesign customer dashboard",
                description="Redesign customer portal dashboard",
                status="in_progress",
                priority="high",
                assignee_id=emp2.id,
                reporter_id=emp1.id
            )
            db.add_all([task1, task2, task3])
            await db.flush()
            
            # Create company decisions
            dec1 = CompanyDecision(
                organization_id=org.id,
                decision_id=f"dec-{uuid.uuid4().hex[:8]}",
                kind="strategic",
                title="Migrate to PostgreSQL 18",
                rationale="Upgrade to latest PostgreSQL for performance and security",
                state="proposed",
                source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                event_name="platform_upgrade"
            )
            dec2 = CompanyDecision(
                organization_id=org.id,
                decision_id=f"dec-{uuid.uuid4().hex[:8]}",
                kind="operational",
                title="Adopt new API gateway",
                rationale="Improve API performance and security",
                state="approved",
                source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
                event_name="architecture_review"
            )
            db.add_all([dec1, dec2])
            await db.flush()
            
            # Create company goals
            goal1 = CompanyGoal(
                organization_id=org.id,
                title="Platform Modernization Complete",
                description="Complete migration to PostgreSQL 18 and new API gateway",
                status="active",
                priority=1,
                kind="efficiency"
            )
            goal2 = CompanyGoal(
                organization_id=org.id,
                title="Customer Satisfaction Improvement",
                description="Increase customer satisfaction score to 4.5+",
                status="active",
                priority=2,
                kind="growth"
            )
            db.add_all([goal1, goal2])
            await db.flush()
            
            # Create company objectives
            obj1 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal1.id,
                title="Complete PostgreSQL 18 Migration",
                description="Migrate all databases to PostgreSQL 18 by end of Q3",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            obj2 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal1.id,
                title="Deploy New API Gateway",
                description="Deploy new API gateway with improved rate limiting",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            obj3 = CompanyObjective(
                organization_id=org.id,
                goal_id=goal2.id,
                title="Improve CSAT Score",
                description="Implement customer feedback loop and improve CSAT",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            db.add_all([obj1, obj2, obj3])
            await db.flush()
            
            # Create company initiatives
            init1 = CompanyInitiative(
                organization_id=org.id,
                objective_id=obj1.id,
                title="Database Migration Project",
                description="Migrate all databases to PostgreSQL 18",
                status="active",
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            db.add(init1)
            await db.flush()
            
            # Create company decisions with authorizations
            auth1 = CompanyAuthorization(
                organization_id=org.id,
                authorization_type="full",
                title="Authorization for Platform Migration",
                description="Full authorization for platform migration project",
                state="approved",
                scope_type="company",
                scope_id=org.id,
                valid_from=datetime.now(timezone.utc),
                valid_until=datetime.now(timezone.utc) + timedelta(days=365),
                requested_by=admin_user.id,
                requested_at=utcnow(),
                approved_by=admin_user.id,
                approved_at=utcnow(),
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            db.add(auth1)
            await db.flush()
            
            # Create commitments
            comm1 = CompanyCommitment(
                organization_id=org.id,
                commitment_type="unconditional",
                title="Complete Platform Migration",
                description="Complete platform migration to PostgreSQL 18",
                state="proposed",
                scope_type="objective",
                scope_id=obj1.id,
                authorization_id=auth1.id,
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            db.add(comm1)
            await db.flush()
            
            # Create actions
            action1 = CompanyAction(
                organization_id=org.id,
                action_type="migration",
                title="Execute Database Migration",
                description="Execute the PostgreSQL 18 migration",
                state="pending",
                risk="high",
                priority_score=90,
                scope_type="project",
                scope_id=proj1.id,
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
                source_commitment_id=comm1.id,
                source_responsibility_id=None,
                target_type="database",
                target_id=None,
                policy="manual",
                approval_required=True,
                assignee_type="employee",
                assignee_id=emp1.id,
                created_by=admin_user.id
            )
            db.add(action1)
            await db.flush()
            
            # Create canonical operations
            op1 = CanonicalOperation(
                organization_id=org.id,
                operation_type="database_migration",
                title="PostgreSQL 18 Migration",
                description="Migrate production databases to PostgreSQL 18",
                scope_type="company",
                state="queued",
                actor_id=admin_user.id,
                actor_type="human",
                is_external=False,
                retry_policy="exponential_backoff",
                max_attempts=3,
                concurrency_token=1,
                fingerprint=f"fp-{uuid.uuid4().hex[:16]}"
            )
            db.add(op1)
            await db.flush()
            
            # Create health dimensions
            import hashlib
            for dim_name, current, target in [
                ("api_latency", 50.0, 100.0),
                ("db_query_time", 15.0, 50.0),
                ("api_error_rate", 0.1, 0.01),
                ("deployment_frequency", 5.0, 10.0)
            ]:
                fp = hashlib.sha256(f"{dim_name}|{org.id}|company|".encode()).hexdigest()[:64]
                health = HealthDimension(
                    organization_id=org.id,
                    dimension=dim_name,
                    scope_type="company",
                    scope_id=None,
                    status="healthy" if current <= target else "degraded",
                    current_value=current,
                    target_value=target,
                    recorded_at=utcnow(),
                    fingerprint=fp
                )
                db.add(health)
            
            # Create canonical observations
            obs1 = CanonicalObservation(
                organization_id=org.id,
                observation_type="health_check",
                title="Platform latency within SLA",
                description="API latency is within SLA thresholds",
                source="platform_metrics",
                source_component="api_gateway",
                epistemic_status="observed",
                severity="info",
                recorded_at=utcnow(),
                observed_at=utcnow(),
                details_json={"metric": "api_latency", "value": 50, "unit": "ms"},
                fingerprint=f"obs-{uuid.uuid4().hex[:16]}"
            )
            db.add(obs1)
            
            # Create canonical operations with attempts
            cop1 = CanonicalOperation(
                organization_id=org.id,
                operation_type="database_migration",
                title="PostgreSQL 18 Migration",
                description="Migrate production databases to PostgreSQL 18",
                scope_type="company",
                state="queued",
                actor_id=admin_user.id,
                actor_type="human",
                is_external=False,
                retry_policy="exponential_backoff",
                max_attempts=3,
                current_attempt=0,
                max_retry_interval_seconds=300,
                fingerprint=f"cop-{uuid.uuid4().hex[:16]}"
            )
            db.add(cop1)
            await db.flush()
            
            # Create operation attempt
            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="running",
                worker_id=admin_user.id,
                worker_instance="admin",
                started_at=utcnow(),
                fingerprint=f"oa-{uuid.uuid4().hex[:16]}"
            )
            db.add(oa1)
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create timeline events
            te1 = CompanyTimelineEvent(
                organization_id=org.id,
                event_key=f"evt-{uuid.uuid4().hex[:8]}",
                timeline_type="operational",
                event_type="decision_created",
                event_subtype="strategic_decision",
                occurred_at=utcnow() - timedelta(days=2),
                effective_from=utcnow() - timedelta(days=2),
                effective_to=utcnow() + timedelta(days=365),
                change_summary="Strategic decision to migrate to PostgreSQL 18 created",
                delta_json={"decision_id": dec1.id, "state": "proposed"},
                metadata_json={},
                recorded_by=admin_user.id
            )
            db.add(te1)
            
            te2 = CompanyTimelineEvent(
                organization_id=org.id,
                event_key=f"evt-{uuid.uuid4().hex[:8]}",
                timeline_type="operational",
                event_type="authorization_granted",
                event_subtype="full_authorization",
                occurred_at=utcnow() - timedelta(days=1),
                effective_from=utcnow() - timedelta(days=1),
                effective_to=utcnow() + timedelta(days=365),
                change_summary="Full authorization for platform migration granted",
                delta_json={"authorization_id": auth1.id, "state": "approved"},
                metadata_json={},
                recorded_by=admin_user.id
            )
            db.add(te2)
            
            # Create knowledge snapshot
            ks1 = CompanyKnowledgeSnapshot(
                organization_id=org.id,
                claim_id=f"claim-{uuid.uuid4().hex[:8]}",
                claim_type="platform_status",
                claim_version=1,
                epistemic_state="observed",
                confidence=0.85,
                belief_json={"summary": "Platform migration to PostgreSQL 18 is in progress"},
                evidence_ids_json=["platform_metrics"],
                contradiction_ids_json=[],
                snapshot_at=utcnow(),
                valid_from=utcnow(),
                valid_to=utcnow() + timedelta(days=30),
                recorded_by=admin_user.id
            )
            db.add(ks1)
            
            # Create approval policy
            ap1 = ApprovalPolicy(
                organization_id=org.id,
                name="Platform Migration Approval",
                approval_type="decision",
                required_permission="decision:create",
                scope_id=None,
                self_approval_allowed=False,
                is_active=True,
                description="Approval required for platform migration decisions"
            )
            db.add(ap1)
            
            # Create governance scope
            gs1 = GovernanceScope(
                organization_id=org.id,
                name="Platform Governance",
                scope_type="company",
                entity_id=org.id,
                depth=0
            )
            db.add(gs1)
            await db.flush()
            
            # Query existing connectors
            result = await db.execute(select(Connector).where(Connector.kind == "code", Connector.provider == "github"))
            conn_github = result.scalars().first()
            if not conn_github:
                conn_github = Connector(
                    kind="code",
                    provider="github",
                    display_name="GitHub",
                    description="GitHub integration for repositories and issues",
                    inbound_capabilities=["read_repos", "read_issues", "read_pull_requests", "read_commits"],
                    outbound_capabilities=["read"],
                    supported_entities=["repository", "issue", "pull_request", "commit", "person"],
                    supported_events=["push", "pull_request", "issues"],
                    sync_modes=["incremental", "webhook"],
                    supports_webhooks=True,
                    supports_polling=True,
                    default_poll_interval_seconds=300,
                    auth_types=["pat"],
                    oauth_scopes=["repo", "read:org", "read:user"],
                    required_config_fields=["organization"],
                    optional_config_fields=[],
                    enabled=True
                )
                db.add(conn_github)
                await db.flush()
            
            result = await db.execute(select(CI).where(CI.organization_id == org.id, CI.connector_id == conn_github.id))
            ci_github = result.scalars().first()
            if not ci_github:
                ci_github = CI(
                    organization_id=org.id,
                    connector_id=conn_github.id,
                    name="GitHub Production",
                    config={"organization": "acme-corp"},
                    credentials={"pat": "mock_pat_token"},
                    state="connected",
                    auth_type="pat",
                    connected_at=utcnow()
                )
                db.add(ci_github)
                await db.flush()
            
            # Query existing Slack connector
            result = await db.execute(select(Connector).where(Connector.kind == "communication", Connector.provider == "slack"))
            conn_slack = result.scalars().first()
            if not conn_slack:
                conn_slack = Connector(
                    kind="communication",
                    provider="slack",
                    display_name="Slack",
                    description="Slack integration for notifications",
                    inbound_capabilities=["read_channels", "read_messages", "read_users"],
                    outbound_capabilities=["send_messages", "update_messages", "delete_messages"],
                    supported_entities=["channel", "message", "user", "thread"],
                    supported_events=["message", "reaction_added", "channel_created"],
                    sync_modes=["incremental", "webhook"],
                    supports_webhooks=True,
                    supports_polling=True,
                    default_poll_interval_seconds=300,
                    auth_types=["bot_token"],
                    oauth_scopes=["channels:read", "channels:history", "chat:write", "users:read"],
                    required_config_fields=["workspace_id", "bot_token"],
                    optional_config_fields=["signing_secret"],
                    enabled=True
                )
                db.add(conn_slack)
                await db.flush()
            
            result = await db.execute(select(CI).where(CI.organization_id == org.id, CI.connector_id == conn_slack.id))
            ci_slack = result.scalars().first()
            if not ci_slack:
                ci_slack = CI(
                    organization_id=org.id,
                    connector_id=conn_slack.id,
                    name="Slack Production",
                    config={"workspace_id": "T123456"},
                    credentials={"bot_token": "xoxb-mock-token"},
                    state="connected",
                    auth_type="bot_token",
                    connected_at=utcnow()
                )
                db.add(ci_slack)
                await db.flush()
            
            # Create external identity mappings
            eim1 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_id="github_user_123",
                external_email="john.doe@github.com",
                external_display_name="John Doe",
                vcos_entity_type="employee",
                vcos_entity_id=emp1.id,
                mapping_state="mapped"
            )
            db.add(eim1)
            
            eim2 = ExternalIdentityMapping(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_id="github_user_456",
                external_email="jane.smith@github.com",
                external_display_name="Jane Smith",
                vcos_entity_type="employee",
                vcos_entity_id=emp2.id,
                mapping_state="mapped"
            )
            db.add(eim2)
            
            # Create sync run
            sr1 = SyncRun(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                sync_mode="incremental",
                state="completed",
                started_at=utcnow() - timedelta(hours=1),
                completed_at=utcnow(),
                entities_processed=150,
                entities_created=10,
                entities_updated=5,
                entities_deleted=0,
                conflicts_detected=0
            )
            db.add(sr1)
            
            # SyncCursor creation skipped - already exists
            
            # ExternalEvent creation skipped - already exists
            
            # SourceAuthority creation skipped - already exists
            
            # Create sync run
            sr1 = SyncRun(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                sync_mode="incremental",
                state="completed",
                started_at=utcnow() - timedelta(hours=1),
                completed_at=utcnow(),
                entities_processed=150,
                entities_created=10,
                entities_updated=5,
                entities_deleted=0,
                conflicts_detected=0
            )
            db.add(sr1)
            
            # SyncCursor creation skipped - already exists
            
            # ExternalEvent creation skipped - already exists
            
            # SourceAuthority creation skipped - already exists
            
            # Create external operation
            eo1 = ExternalOperation(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                source_action_id=None,
                operation_type="create",
                target_entity_type="repository",
                target_external_id="test/repo",
                payload={"name": "test-repo", "private": True},
                state="completed",
                governance_verified=True
            )
            db.add(eo1)
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create worker lease
            wl1 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )
            db.add(wl1)
            
            # Create canonical operation
            cop1 = CanonicalOperation(
                organization_id=org.id,
                operation_type="sync_repository",
                title="Sync GitHub Repositories",
                description="Sync all repositories from GitHub",
                scope_type="company",
                state="completed",
                actor_id=admin_user.id,
                actor_type="system",
                is_external=True,
                external_system="github",
                external_operation_id="ext-op-456",
                retry_policy="exponential_backoff",
                max_attempts=3,
                current_attempt=1,
                max_retry_interval_seconds=300,
                fingerprint=f"cop-{uuid.uuid4().hex[:16]}"
            )
            db.add(cop1)
            await db.flush()
            
            # Create operation attempt
            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )
            db.add(oa1)
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create worker lease
            wl1 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )
            db.add(wl1)
            
            # Create canonical operation with external unknown
            cop2 = CanonicalOperation(
                organization_id=org.id,
                operation_type="create_github_repo",
                title="Create GitHub Repository",
                description="Create new repository for Project Alpha",
                scope_type="project",
                scope_id=proj1.id,
                state="executing",
                actor_id=admin_user.id,
                actor_type="human",
                is_external=True,
                external_system="github",
                external_operation_id="ext-op-789",
                retry_policy="exponential_backoff",
                max_attempts=3,
                current_attempt=1,
                max_retry_interval_seconds=300,
                fingerprint=f"cop-{uuid.uuid4().hex[:16]}"
            )
            db.add(cop2)
            await db.flush()
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create worker lease
            wl2 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )
            db.add(wl2)
            
            # Create health dimensions
            import hashlib
            for dim_name, current, target in [
                ("api_latency", 50.0, 100.0),
                ("db_query_time", 15.0, 50.0),
                ("api_error_rate", 0.1, 0.01),
                ("deployment_frequency", 5.0, 10.0)
            ]:
                fp = hashlib.sha256(f"{dim_name}|{org.id}|company|".encode()).hexdigest()[:64]
                health = HealthDimension(
                    organization_id=org.id,
                    dimension=dim_name,
                    scope_type="company",
                    scope_id=None,
                    status="healthy" if current <= target else "degraded",
                    current_value=current,
                    target_value=target,
                    recorded_at=utcnow(),
                    fingerprint=fp
                )
                db.add(health)
            
            # Create canonical observations
            obs1 = CanonicalObservation(
                organization_id=org.id,
                observation_type="health_check",
                title="Platform latency within SLA",
                description="API latency is within SLA thresholds",
                source="platform_metrics",
                source_component="api_gateway",
                epistemic_status="observed",
                severity="info",
                recorded_at=utcnow(),
                observed_at=utcnow(),
                details_json={"metric": "api_latency", "value": 50, "unit": "ms"},
                fingerprint=f"obs-{uuid.uuid4().hex[:16]}"
            )
            db.add(obs1)
            
            # Create canonical operations with attempts
            cop1 = CanonicalOperation(
                organization_id=org.id,
                operation_type="sync_repository",
                title="Sync GitHub Repositories",
                description="Sync all repositories from GitHub",
                scope_type="company",
                state="completed",
                actor_id=admin_user.id,
                actor_type="system",
                is_external=True,
                external_system="github",
                external_operation_id="ext-op-456",
                retry_policy="exponential_backoff",
                max_attempts=3,
                current_attempt=1,
                max_retry_interval_seconds=300,
                fingerprint=f"cop-{uuid.uuid4().hex[:16]}"
            )
            db.add(cop1)
            await db.flush()
            
            # Create operation attempt
            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )
            db.add(oa1)
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create worker lease
            wl1 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )
            db.add(wl1)
            
            # Create canonical operation
            cop1 = CanonicalOperation(
                organization_id=org.id,
                operation_type="sync_repository",
                title="Sync GitHub Repositories",
                description="Sync all repositories from GitHub",
                scope_type="company",
                state="completed",
                actor_id=admin_user.id,
                actor_type="system",
                is_external=True,
                external_system="github",
                external_operation_id="ext-op-456",
                retry_policy="exponential_backoff",
                max_attempts=3,
                current_attempt=1,
                max_retry_interval_seconds=300,
                fingerprint=f"cop-{uuid.uuid4().hex[:16]}"
            )
            db.add(cop1)
            await db.flush()
            
            # Create operation attempt
            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )
            db.add(oa1)
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create worker lease
            wl1 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )
            db.add(wl1)
            
            # Create canonical operation
            cop1 = CanonicalOperation(
                organization_id=org.id,
                operation_type="sync_repository",
                title="Sync GitHub Repositories",
                description="Sync all repositories from GitHub",
                scope_type="company",
                state="completed",
                actor_id=admin_user.id,
                actor_type="system",
                is_external=True,
                external_system="github",
                external_operation_id="ext-op-456",
                retry_policy="exponential_backoff",
                max_attempts=3,
                current_attempt=1,
                max_retry_interval_seconds=300,
                fingerprint=f"cop-{uuid.uuid4().hex[:16]}"
            )
            db.add(cop1)
            await db.flush()
            
            # Create operation attempt
            oa1 = OperationAttempt(
                operation_id=cop1.id,
                organization_id=org.id,
                attempt_number=1,
                state="completed",
                worker_id="system",
                worker_instance="system",
                started_at=utcnow() - timedelta(minutes=5),
                completed_at=utcnow(),
                outcome="success",
                result_json={"repos_synced": 50},
                fingerprint="oa-" + uuid.uuid4().hex[:16]
            )
            db.add(oa1)
            
            # ExternalUnknownState creation removed for FK compliance
            
            # Create worker lease
            wl1 = WorkerLease(
                organization_id=org.id,
                worker_id="worker-" + uuid.uuid4().hex[:8],
                worker_type="sync_worker",
                operation_id=cop1.id,
                expires_at=utcnow() + timedelta(minutes=30)
            )
            db.add(wl1)
            
            await db.commit()
            print(f"  Created comprehensive company state for {org.name}")

        print("\n=== Company state creation complete ===")

if __name__ == "__main__":
    asyncio.run(create_company_state())