"""Demo Company Seeder — Creates a realistic demo company with full canonical data.

This seeder creates "Nova Labs" — a fictional mid-size technology company
with realistic organizational structure, projects, people, commitments,
decisions, and evidence to demonstrate VCOS capabilities.

Run: python -m app.demo_seeder
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal, init_db
from app.models.organization import Organization, OrganizationSettings
from app.models.department import Department
from app.models.user import User
from app.models.employee import Employee
from app.models.role import Role, UserRoleModelModel
from app.models.workspace import Workspace
from app.models.project import Project
from app.models.task import Task
from app.models.meeting import Meeting
from app.models.goal import Goal
from app.models.knowledge import Document, WikiPage, Policy, SOP, Template, Decision as KnowledgeDecision
from app.models.calendar import CalendarEvent
from app.models.hr import LeaveType, LeaveRequest
from app.models.notification import Notification, AuditLog
from app.models.people_decision import PeopleDecision
from app.models.approval import Risk as ApprovalRisk
from app.core.security import hash_password
from app.core.timeutils import utcnow
from app.services.permission_service import permission_service
from app.people.employee_service import employee_service
from app.services.organization_service import organization_service
from app.models.role import Role, UserRoleModelModel
from app.models.workspace import Workspace
from app.models.organization import Organization, OrganizationSettings
from app.core.security import hash_password
from app.core.timeutils import utcnow


# ============================================================
# DEMO COMPANY DATA
# ============================================================

DEMO_ORG = {
    "name": "Nova Labs",
    "slug": "nova-labs",
    "industry": "Technology",
    "country": "US",
    "timezone": "America/Los_Angeles",
    "language": "en",
    "currency": "USD",
    "status": "active",
    "entity_type": "startup",
    "legal_name": "Nova Labs Inc.",
    "tax_id": "12-3456789",
    "registration_number": "C-2024-001234",
    "brand_primary_color": "#4F46E5",
}

DEMO_ADMIN = {
    "email": "sarah.chen@nova-labs.com",
    "username": "sarah.chen",
    "full_name": "Sarah Chen",
    "password": "DemoPass123!",
    "role": "ceo",
    "designation": "Founder & CEO",
}

# Demo employees
DEMO_EMPLOYEES = [
    {
        "email": "marcus.wong@nova-labs.com",
        "username": "marcus.wong",
        "full_name": "Marcus Wong",
        "password": "DemoPass123!",
        "role": "cto",
        "designation": "Chief Technology Officer",
        "department": "Engineering",
        "team": "Platform",
    },
    {
        "email": "priya.sharma@nova-labs.com",
        "username": "priya.sharma",
        "full_name": "Priya Sharma",
        "password": "DemoPass123!",
        "role": "vp_engineering",
        "designation": "VP Engineering",
        "department": "Engineering",
        "team": "Platform",
    },
    {
        "email": "alex.rodriguez@nova-labs.com",
        "username": "alex.rodriguez",
        "full_name": "Alex Rodriguez",
        "password": "DemoPass123!",
        "role": "engineering_lead",
        "designation": "Engineering Lead",
        "department": "Engineering",
        "team": "Platform",
    },
    {
        "email": "jordan.kim@nova-labs.com",
        "username": "jordan.kim",
        "full_name": "Jordan Kim",
        "password": "DemoPass123!",
        "role": "engineer",
        "designation": "Senior Engineer",
        "department": "Engineering",
        "team": "Platform",
    },
    {
        "email": "sophia.nguyen@nova-labs.com",
        "username": "sophia.nguyen",
        "full_name": "Sophia Nguyen",
        "password": "DemoPass123!",
        "role": "product_lead",
        "designation": "Product Lead",
        "department": "Product",
        "team": "Core Product",
    },
    {
        "email": "david.park@nova-labs.com",
        "username": "david.park",
        "full_name": "David Park",
        "password": "DemoPass123!",
        "role": "designer",
        "designation": "Senior Designer",
        "department": "Product",
        "team": "Core Product",
    },
    {
        "email": "emma.wilson@nova-labs.com",
        "username": "emma.wilson",
        "full_name": "Emma Wilson",
        "password": "DemoPass123!",
        "role": "engineer",
        "designation": "Full Stack Engineer",
        "department": "Engineering",
        "team": "Data Platform",
    },
    {
        "email": "carlos.mendoza@nova-labs.com",
        "username": "carlos.mendoza",
        "full_name": "Carlos Mendoza",
        "password": "DemoPass123!",
        "role": "devops_lead",
        "designation": "DevOps Lead",
        "department": "Engineering",
        "team": "Infrastructure",
    },
    {
        "email": "lisa.chang@nova-labs.com",
        "username": "lisa.chang",
        "full_name": "Lisa Chang",
        "password": "DemoPass123!",
        "role": "hr_lead",
        "designation": "People Operations Lead",
        "department": "People",
        "team": "People Operations",
    },
    {
        "email": "ryan.patel@nova-labs.com",
        "username": "ryan.patel",
        "full_name": "Ryan Patel",
        "password": "DemoPass123!",
        "role": "sales_lead",
        "designation": "Head of Sales",
        "department": "Revenue",
        "team": "Sales",
    },
]


# ============================================================
# PROJECTS & COMMITMENTS
# ============================================================

DEMO_PROJECTS = [
    {
        "name": "Nova Platform v2.0",
        "code": "NP2",
        "description": "Complete rewrite of the Nova platform with improved scalability and developer experience",
        "status": "active",
        "priority": "critical",
        "progress": 65,
        "health": "at_risk",
        "start_date": None,  # Will be set dynamically
        "end_date": None,
        "tags": ["platform", "core", "v2"],
    },
    {
        "name": "Customer 360 Dashboard",
        "code": "C360",
        "description": "Unified customer intelligence dashboard with real-time health scoring",
        "status": "active",
        "priority": "high",
        "progress": 40,
        "health": "healthy",
        "start_date": None,
        "end_date": None,
        "tags": ["analytics", "customer", "dashboard"],
    },
    {
        "name": "AI-Powered Meeting Intelligence",
        "code": "AIM",
        "description": "Real-time meeting transcription, action item extraction, and insights",
        "status": "active",
        "priority": "high",
        "progress": 25,
        "health": "healthy",
        "start_date": None,
        "end_date": None,
        "tags": ["ai", "meetings", "intelligence"],
    },
    {
        "name": "Enterprise SSO & Governance",
        "code": "ESSO",
        "description": "Enterprise-grade SSO, SCIM provisioning, and compliance governance",
        "status": "active",
        "priority": "high",
        "progress": 80,
        "health": "healthy",
        "start_date": None,
        "end_date": None,
        "tags": ["security", "sso", "compliance"],
    },
    {
        "name": "Developer Platform v1",
        "code": "DEV1",
        "description": "Public API, webhooks, extensions marketplace, and developer portal",
        "status": "planning",
        "priority": "medium",
        "progress": 10,
        "health": "healthy",
        "start_date": None,
        "end_date": None,
        "tags": ["api", "developer", "platform"],
    },
    {
        "name": "Mobile App v2",
        "code": "MOB2",
        "description": "Native iOS/Android app with offline sync and push notifications",
        "status": "active",
        "priority": "medium",
        "progress": 45,
        "health": "at_risk",
        "start_date": None,
        "end_date": None,
        "tags": ["mobile", "ios", "android"],
    },
]


# ============================================================
# DECISIONS & COMMITMENTS
# ============================================================

DEMO_DECISIONS = [
    {
        "title": "Adopt PostgreSQL as Primary Database",
        "description": "Standardize on PostgreSQL 16 for all canonical data with RLS for tenant isolation",
        "decision_type": "technical",
        "status": "approved",
        "priority": "high",
        "evidence_summary": "Evaluated PostgreSQL vs MySQL vs CockroachDB. PostgreSQL chosen for RLS maturity, JSONB support, and ecosystem maturity.",
        "rationale": "Tenant isolation requirement makes PostgreSQL RLS the decisive factor.",
    },
    {
        "title": "Adopt Row-Level Security for Multi-Tenancy",
        "description": "Implement database-level tenant isolation using PostgreSQL RLS policies",
        "decision_type": "security",
        "status": "approved",
        "priority": "critical",
        "evidence_summary": "Evaluated application-level vs database-level isolation. Database-level provides defense-in-depth.",
        "rationale": "Application-level isolation alone is insufficient for defense-in-depth security posture.",
    },
    {
        "title": "Standardize on Groq for LLM Inference",
        "description": "Use Groq's Llama-3.3-70b as primary LLM with deterministic fallback for governance",
        "decision_type": "technical",
        "status": "approved",
        "priority": "high",
        "evidence_summary": "Evaluated OpenAI, Anthropic, Azure OpenAI, and Groq. Groq offers best latency/cost for 70B model with deterministic fallback.",
        "rationale": "Deterministic engine provides governance; Groq provides best free-form generation.",
    },
    {
        "title": "Implement Row-Level Security for All Tenant Tables",
        "description": "Apply RLS policies to all 662 tenant-scoped tables with FORCE ROW LEVEL SECURITY",
        "decision_type": "security",
        "status": "approved",
        "priority": "critical",
        "evidence_summary": "662 tenant-scoped tables identified. 640 direct ownership, 22 indirect. All require FORCE RLS.",
        "rationale": "Table owner bypass is prevented by FORCE ROW LEVEL SECURITY.",
    },
    {
        "title": "Adopt Deterministic AI Engine as Governance Baseline",
        "description": "All AI reasoning must be reproducible; deterministic engine provides governance baseline",
        "decision_type": "governance",
        "status": "approved",
        "priority": "critical",
        "evidence_summary": "Non-deterministic LLMs cannot be audited. Deterministic engine provides audit trail and epistemic integrity.",
        "rationale": "Epistemic integrity requires reproducibility; LLMs alone cannot provide audit trail.",
    },
    {
        "title": "Adopt Canonical Mutation Boundary Pattern",
        "description": "All canonical mutations go through single boundary with idempotency, provenance, and governance",
        "decision_type": "architecture",
        "status": "approved",
        "priority": "critical",
        "evidence_summary": "Direct ORM mutations bypass governance. CanonicalMutationBoundary enforces provenance and idempotency.",
        "rationale": "Canonical mutation boundary is the enforcement point for canonical reality integrity.",
    },
]


# ============================================================
# GOALS & RISKS
# ============================================================

DEMO_GOALS = [
    {
        "title": "Launch Nova Platform v2.0 by Q3 2024",
        "description": "Complete platform rewrite with improved scalability and developer experience",
        "goal_type": "delivery",
        "target_date": None,  # Will be set dynamically
        "progress": 65,
        "priority": "critical",
    },
    {
        "title": "Achieve SOC 2 Type II Certification",
        "description": "Complete SOC 2 Type II audit for enterprise readiness",
        "goal_type": "compliance",
        "target_date": None,
        "progress": 80,
        "priority": "high",
    },
    {
        "title": "Reach 100 Enterprise Customers",
        "description": "Scale to 100 enterprise customers with $1M ARR",
        "goal_type": "growth",
        "target_date": None,
        "progress": 23,
        "priority": "high",
    },
    {
        "title": "Achieve 99.99% Platform Uptime",
        "description": "Implement multi-AZ deployment with automated failover",
        "goal_type": "reliability",
        "target_date": None,
        "progress": 92,
        "priority": "high",
    },
    {
        "title": "Launch Developer Platform & Marketplace",
        "description": "Public API, webhooks, extensions marketplace, and developer portal",
        "goal_type": "product",
        "target_date": None,
        "progress": 10,
        "priority": "medium",
    },
]

DEMO_RISKS = [
    {
        "title": "Platform v2.0 Delivery Delay",
        "description": "Platform v2.0 rewrite may miss Q3 2024 target due to scope creep and technical debt",
        "risk_type": "delivery",
        "probability": "high",
        "impact": "high",
        "status": "open",
        "mitigation": "Scope freeze, dedicated refactoring sprints, weekly milestone reviews",
    },
    {
        "title": "Key Personnel Dependency",
        "description": "Platform v2.0 depends on 3 senior engineers; loss of any would significantly impact timeline",
        "risk_type": "people",
        "probability": "medium",
        "impact": "critical",
        "status": "open",
        "mitigation": "Knowledge sharing sessions, documentation sprints, cross-training",
    },
    {
        "title": "SOC 2 Audit Findings",
        "description": "Potential audit findings could delay enterprise sales cycle",
        "risk_type": "compliance",
        "probability": "low",
        "impact": "high",
        "status": "open",
        "mitigation": "Pre-audit remediation, dedicated compliance engineer, automated evidence collection",
    },
    {
        "title": "AI Provider Dependency",
        "description": "Groq API availability and pricing changes could impact AI features",
        "risk_type": "vendor",
        "probability": "medium",
        "impact": "medium",
        "status": "open",
        "mitigation": "Deterministic engine fallback, multi-provider abstraction, local model evaluation",
    },
    {
        "title": "Data Residency Requirements",
        "description": "EU customers require EU data residency; current single-region deployment",
        "risk_type": "compliance",
        "probability": "medium",
        "impact": "high",
        "status": "open",
        "mitigation": "Multi-region deployment, data residency policies, EU region deployment",
    },
]


# ============================================================
# MEETINGS & EVIDENCE
# ============================================================

DEMO_MEETINGS = [
    {
        "title": "Weekly Leadership Sync",
        "description": "Weekly sync on company health, risks, and priorities",
        "meeting_type": "recurring",
        "recurrence": "weekly",
        "duration_minutes": 60,
    },
    {
        "title": "Platform v2.0 Architecture Review",
        "description": "Deep dive on v2.0 architecture decisions and technical risks",
        "meeting_type": "decision",
        "duration_minutes": 90,
    },
    {
        "title": "SOC 2 Readiness Review",
        "description": "Review SOC 2 evidence collection and audit readiness",
        "meeting_type": "governance",
        "duration_minutes": 60,
    },
    {
        "title": "Q2 Planning Session",
        "description": "Quarterly planning for Q3 priorities and resource allocation",
        "meeting_type": "planning",
        "duration_minutes": 120,
    },
    {
        "title": "Customer Advisory Board",
        "description": "Quarterly session with key enterprise customers",
        "meeting_type": "customer",
        "duration_minutes": 90,
    },
]


# ============================================================
# KNOWLEDGE BASE
# ============================================================

DEMO_KNOWLEDGE = [
    {
        "title": "Nova Labs Architecture Decision Record",
        "content": "All architecture decisions must be recorded as ADRs in the decision log with rationale, alternatives, and consequences.",
        "category": "architecture",
        "tags": ["architecture", "governance", "adr"],
    },
    {
        "title": "Security Incident Response Playbook",
        "content": "Step-by-step playbook for security incidents: detection, containment, eradication, recovery, and post-mortem.",
        "category": "security",
        "tags": ["security", "incident", "playbook"],
    },
    {
        "title": "Nova Platform Architecture Overview",
        "content": "PostgreSQL with RLS, FastAPI, React, Redis, OpenSearch, Neo4j, MinIO. Multi-AZ deployment with Terraform.",
        "category": "architecture",
        "tags": ["architecture", "infrastructure", "postgresql", "fastapi"],
    },
    {
        "title": "Nova Labs Security Policy",
        "content": "MFA required for all accounts. Password rotation every 90 days. VPN required for production access. Annual penetration testing.",
        "category": "security",
        "tags": ["security", "policy", "mfa", "vpn"],
    },
    {
        "title": "Incident Response Runbook",
        "content": "Severity definitions, escalation paths, communication templates, stakeholder notification, and post-mortem process.",
        "category": "operations",
        "tags": ["operations", "incident", "runbook"],
    },
]


async def seed_demo_company(db: AsyncSession) -> dict:
    """Seed the Nova Labs demo company with full canonical data."""
    now = utcnow()
    
    # 1. Create Organization
    org = Organization(**DEMO_ORG)
    db.add(org)
    await db.flush()
    
    # Organization Settings
    settings = OrganizationSettings(
        organization_id=org.id,
        allow_employee_self_registration=False,
        require_email_verification=True,
        default_theme="system",
        weekly_digest=True,
        announcement_enabled=True,
        retention_days_audit=2555,  # 7 years
        retention_days_notifications=90,
    )
    db.add(settings)
    await db.flush()
    
    # Seed Roles
    roles = await permission_service.seed_org_roles(db, org.id)
    ceo_role = roles["ceo"]
    
    # Create Admin User (Sarah Chen - CEO)
    admin = User(
        organization_id=org.id,
        email=DEMO_ADMIN["email"],
        username=DEMO_ADMIN["username"],
        full_name=DEMO_ADMIN["full_name"],
        password_hash=hash_password(DEMO_ADMIN["password"]),
        status="active",
        role=DEMO_ADMIN["role"],
        timezone=DEMO_ORG["timezone"],
        language=DEMO_ORG["language"],
        email_verified_at=utcnow(),
    )
    db.add(admin)
    await db.flush()
    org.owner_id = admin.id
    
    # Assign CEO role
    db.add(UserRoleModel(user_id=admin.id, role_id=ceo_role.id, organization_id=org.id))
    
    # Create Workspace
    workspace = Workspace(organization_id=org.id, user_id=admin.id)
    db.add(workspace)
    
    # Create Employee Record for CEO
    await employee_service.create_for_user(
        db,
        organization_id=org.id,
        user_id=admin.id,
        email=admin.email,
        full_name=admin.full_name,
        designation=DEMO_ADMIN["designation"],
    )
    await db.flush()
    
    # Initialize created_employees list
    created_employees = []
    
    # Add admin to created_employees for task assignment
    from app.models.employee import Employee as EmployeeModel
    admin_employee = await db.execute(select(EmployeeModel).where(EmployeeModel.user_id == admin.id))
    admin_emp = admin_employee.scalar_one_or_none()
    if admin_emp:
        created_employees.append({
            "user": admin,
            "employee": admin_emp,
            "designation": DEMO_ADMIN["designation"],
            "department": "Executive",
            "team": "Leadership",
        })
    
    # Create Demo Employees
    employees = []
    for emp_data in DEMO_EMPLOYEES:
        # Create User
        user = User(
            organization_id=org.id,
            email=emp_data["email"],
            username=emp_data["username"],
            full_name=emp_data["full_name"],
            password_hash=hash_password(emp_data["password"]),
            status="active",
            role=emp_data["role"],
            timezone=DEMO_ORG["timezone"],
            language=DEMO_ORG["language"],
            email_verified_at=utcnow(),
        )
        db.add(user)
        await db.flush()
        
        # Assign Role
        role = None
        for role in roles.values():
            if role.code == emp_data["role"]:
                role = role
                break
        if role:
            db.add(UserRoleModel(user_id=user.id, role_id=role.id, organization_id=org.id))
        
        # Create Employee Record
        employee = await employee_service.create_for_user(
            db,
            organization_id=org.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            designation=emp_data["designation"],
        )
        
        employees.append(user)
        created_employees.append({
            "user": user,
            "employee": employee,
            "designation": emp_data["designation"],
            "department": emp_data["department"],
            "team": emp_data["team"],
        })
    
    # 2. Create Departments
    departments = {}
    dept_data = [
        ("Engineering", "eng", "Technology"),
        ("Product", "prod", "Product"),
        ("Revenue", "rev", "Revenue"),
        ("People", "people", "People"),
        ("Finance", "fin", "Finance"),
        ("Legal", "legal", "Legal"),
    ]
    
    for name, code, parent_name in dept_data:
        dept = Department(
            organization_id=org.id,
            name=name,
            code=code,
            description=f"{name} Department",
            parent_id=departments.get(parent_name, None).id if parent_name in departments else None,
        )
        db.add(dept)
        await db.flush()
        departments[name] = dept
    
    # Assign employees to departments
    dept_assignments = {
        "Engineering": ["Engineering"],
        "Product": ["Product"],
        "Revenue": ["Revenue"],
        "People": ["People"],
    }
    
    for emp in created_employees:
        dept_name = emp["department"]
        if dept_name in departments:
            emp["employee"].department_id = departments[dept_name].id
    
    await db.flush()
    
    # 3. Create Teams
    from app.models.team import Team
    
    teams = {}
    team_data = [
        ("Platform", "plat", "Engineering"),
        ("Data Platform", "dataplat", "Engineering"),
        ("Infrastructure", "infra", "Engineering"),
        ("Core Product", "coreprod", "Product"),
        ("People Operations", "peopleops", "People"),
        ("Sales", "sales", "Revenue"),
    ]
    
    for name, code, dept_name in team_data:
        if dept_name in departments:
            team = Team(
                organization_id=org.id,
                name=name,
                code=code,
                description=f"{name} Team",
                department_id=departments[dept_name].id,
            )
            db.add(team)
            await db.flush()
            teams[name] = team
    
    # Assign employees to teams
    team_assignments = {
        "Platform": ["marcus.wong@nova-labs.com", "priya.sharma@nova-labs.com", "alex.rodriguez@nova-labs.com"],
        "Data Platform": ["emma.wilson@nova-labs.com"],
        "Infrastructure": ["carlos.mendoza@nova-labs.com"],
        "Core Product": ["sophia.nguyen@nova-labs.com", "david.park@nova-labs.com"],
        "People Operations": ["lisa.chang@nova-labs.com"],
        "Sales": ["ryan.patel@nova-labs.com"],
    }
    
    email_to_emp = {e["user"].email: e["employee"] for e in created_employees}
    
    for team_name, emails in team_assignments.items():
        if team_name in teams:
            for email in emails:
                if email in email_to_emp:
                    email_to_emp[email].team_id = teams[team_name].id
    
    await db.flush()
    
    # 4. Create Projects
    projects = {}
    base_date = utcnow() - timedelta(days=90)
    
    for proj_data in DEMO_PROJECTS:
        start = proj_data["start_date"] or (base_date + timedelta(days=proj_data.get("start_offset", 0)))
        end = proj_data["end_date"] or (base_date + timedelta(days=proj_data.get("end_offset", 180)))
        
        proj = Project(
            organization_id=org.id,
            name=proj_data["name"],
            code=proj_data["code"],
            description=proj_data["description"],
            status=proj_data["status"],
            priority=proj_data["priority"],
            progress=proj_data["progress"],
            health=proj_data["health"],
            start_date=start.date() if start else None,
            end_date=end.date() if end else None,
        )
        db.add(proj)
        await db.flush()
        projects[proj_data["code"]] = proj
    
    await db.flush()
    
    # 4. Create Tasks for Projects
    task_data = [
        ("NP2", "Database Schema Migration", "Migrate to PostgreSQL 16 with RLS", "in_progress", "high", "alex.rodriguez@nova-labs.com"),
        ("NP2", "RLS Policy Implementation", "Implement RLS on all 662 tenant tables", "done", "critical", "alex.rodriguez@nova-labs.com"),
        ("NP2", "API Gateway Rewrite", "Rewrite API gateway with new routing", "in_progress", "high", "marcus.wong@nova-labs.com"),
        ("NP2", "Developer Portal", "Build developer portal with API docs", "todo", "medium", "priya.sharma@nova-labs.com"),
        ("C360", "Customer Data Pipeline", "Build unified customer data pipeline", "in_progress", "high", "sophia.nguyen@nova-labs.com"),
        ("C360", "Health Scoring Engine", "Implement real-time customer health scoring", "todo", "high", "priya.sharma@nova-labs.com"),
        ("C360", "Executive Dashboard", "Build executive customer 360 dashboard", "in_progress", "medium", "david.park@nova-labs.com"),
        ("AIM", "Meeting Transcription", "Integrate real-time transcription", "in_progress", "high", "marcus.wong@nova-labs.com"),
        ("AIM", "Action Item Extraction", "Extract action items from transcripts", "todo", "high", "alex.rodriguez@nova-labs.com"),
        ("AIM", "Meeting Insights", "Generate meeting insights and summaries", "todo", "medium", "priya.sharma@nova-labs.com"),
        ("ESSO", "SAML/OIDC Integration", "Implement SAML and OIDC providers", "done", "critical", "carlos.mendoza@nova-labs.com"),
        ("ESSO", "SCIM Provisioning", "Implement SCIM 2.0 user provisioning", "in_progress", "high", "carlos.mendoza@nova-labs.com"),
        ("ESSO", "Audit Logging", "Comprehensive audit log for compliance", "in_progress", "high", "carlos.mendoza@nova-labs.com"),
        ("DEV1", "Public API Design", "Design public REST/GraphQL API", "todo", "medium", "marcus.wong@nova-labs.com"),
        ("DEV1", "Webhook System", "Build event-driven webhook system", "todo", "medium", "alex.rodriguez@nova-labs.com"),
        ("DEV1", "Extensions Marketplace", "Build extensions marketplace", "todo", "medium", "priya.sharma@nova-labs.com"),
        ("MOB2", "iOS App Rewrite", "Rewrite iOS app in SwiftUI", "in_progress", "high", "emma.wilson@nova-labs.com"),
        ("MOB2", "Android App Rewrite", "Rewrite Android app in Jetpack Compose", "in_progress", "high", "david.park@nova-labs.com"),
        ("MOB2", "Offline Sync", "Implement offline-first sync engine", "todo", "high", "alex.rodriguez@nova-labs.com"),
        ("MOB2", "Push Notifications", "Implement push notification service", "todo", "medium", "carlos.mendoza@nova-labs.com"),
    ]
    
    for proj_code, title, desc, status, priority, assignee_email in task_data:
        if proj_code in projects and assignee_email in email_to_emp:
            proj = projects[proj_code]
            assignee = email_to_emp[assignee_email]
            assignee_emp = email_to_emp[assignee_email]
            
            task = Task(
                organization_id=org.id,
                project_id=proj.id,
                title=title,
                description=desc,
                status=status,
                priority=priority,
                assignee_id=assignee_emp.id,
                reporter_id=email_to_emp["sarah.chen@nova-labs.com"].id,
            )
            db.add(task)
    
    await db.flush()
    
    # 5. Create Decisions
    for dec_data in DEMO_DECISIONS:
        decision = KnowledgeDecision(
            organization_id=org.id,
            title=dec_data["title"],
            slug=dec_data["title"].lower().replace(" ", "-")[:240],
            description=dec_data["description"],
            content=dec_data.get("evidence_summary", ""),
            status=dec_data["status"],
            decision_maker_id=admin.id,
            decided_at=utcnow(),
            impact=dec_data.get("rationale", ""),
        )
        db.add(decision)
    
    await db.flush()
    
    # 5. Create Goals
    for goal_data in DEMO_GOALS:
        target = goal_data["target_date"] or (utcnow() + timedelta(days=180))
        goal = Goal(
            organization_id=org.id,
            name=goal_data["title"],
            description=goal_data["description"],
            scope="company",
            end_date=target.date(),
            progress=goal_data["progress"],
            priority=goal_data["priority"],
            owner_id=admin_emp.id,
        )
        db.add(goal)
    
    await db.flush()
    
    # 6. Create Risks
    prob_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    impact_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    
    for risk_data in DEMO_RISKS:
        risk = ApprovalRisk(
            organization_id=org.id,
            title=risk_data["title"],
            description=risk_data["description"],
            probability=prob_map.get(risk_data["probability"], 2),
            impact=impact_map.get(risk_data["impact"], 2),
            status=risk_data["status"],
            mitigation=risk_data.get("mitigation", ""),
            owner_id=admin_emp.id,
        )
        db.add(risk)
    
    await db.flush()
    
    # 6. Create Meetings
    for meeting_data in DEMO_MEETINGS:
        meeting = Meeting(
            organization_id=org.id,
            title=meeting_data["title"],
            description=meeting_data["description"],
            meeting_type=meeting_data["meeting_type"],
            duration_minutes=meeting_data["duration_minutes"],
            organizer_id=admin_emp.id,
        )
        db.add(meeting)
    
    await db.flush()
    
    # 7. Create Knowledge Base Articles (as Documents)
    for kb_data in DEMO_KNOWLEDGE:
        slug = kb_data["title"].lower().replace(" ", "-").replace("'", "").replace(".", "")[:120]
        kb = Document(
            organization_id=org.id,
            title=kb_data["title"],
            slug=slug,
            content=kb_data["content"],
            status="published",
            author_id=admin_emp.id,
        )
        db.add(kb)
    
    await db.flush()
    
    # 8. Create Risks, Leave Types, Calendar Events
    leave_types = [
        ("Annual Leave", "annual", 20, True),
        ("Sick Leave", "sick", 10, True),
        ("Parental Leave", "parental", 90, True),
        ("Bereavement Leave", "bereavement", 5, True),
        ("Jury Duty", "jury", 10, True),
    ]
    
    for name, code, days, paid in leave_types:
        lt = LeaveType(
            organization_id=org.id,
            name=name,
            code=code,
            days_per_year=days,
            is_paid=paid,
        )
        db.add(lt)
    
    await db.flush()
    
    # Calendar events for demo
    for i in range(10):
        event = CalendarEvent(
            organization_id=org.id,
            title=f"Demo Event {i+1}",
            description=f"Sample calendar event {i+1}",
            start_at=utcnow() + timedelta(days=i, hours=9),
            end_at=utcnow() + timedelta(days=i, hours=10),
            created_by=admin_emp.id,
        )
        db.add(event)
    
    await db.flush()
    
    # 9. Create Notifications
    notifications = [
        ("Welcome to Nova Labs", "Your workspace is ready. Set up your profile and start exploring.", "info"),
        ("Platform v2.0 Milestone", "Platform v2.0 reached 65% completion. Architecture review scheduled.", "info"),
        ("SOC 2 Update", "SOC 2 Type II evidence collection at 80%. Audit scheduled for next month.", "info"),
        ("Security Update", "New MFA policies enforced. Please update your authentication methods.", "warning"),
    ]
    
    for title, body, priority in notifications:
        notif = Notification(
            organization_id=org.id,
            title=title,
            body=body,
            priority=priority,
            type="system",
            recipient_id=admin.id,
            actor_id=admin.id,
        )
        db.add(notif)
    
    await db.flush()
    
    # 10. Create Audit Logs
    import json
    for action in ["organization.created", "user.created", "project.created", "decision.recorded", "goal.set"]:
        audit = AuditLog(
            organization_id=org.id,
            action=action,
            actor_id=admin.id,
            actor_email=admin.email,
            resource_type=action.split(".")[0],
            resource_id=org.id,
            details_json=json.dumps({"demo": True}),
            created_at=utcnow(),
        )
        db.add(audit)
    
    await db.flush()
    
    # Final commit
    await db.commit()
    
    return {
        "organization": org,
        "admin": admin,
        "employees": created_employees,
        "projects": projects,
    }


async def main():
    """Run the demo company seeder."""
    print("Seeding Nova Labs demo company...")
    
    await init_db()
    
    async with SessionLocal() as db:
        # Check if demo company already exists
        from sqlalchemy import select
        from app.models.organization import Organization
        
        existing = await db.execute(
            select(Organization).where(Organization.slug == "nova-labs")
        )
        existing_org = existing.scalar_one_or_none()
        
        if existing_org:
            print("Demo company 'Nova Labs' already exists. Skipping seed.")
            return
        
        result = await seed_demo_company(db)
        
        print(f"[OK] Created organization: {result['organization'].name}")
        print(f"[OK] Created admin: {result['admin'].email}")
        print(f"[OK] Created {len(result['employees'])} employees")
        print(f"[OK] Created {len(result['projects'])} projects")
        print(f"\nDemo company 'Nova Labs' seeded successfully!")
        print(f"\nLogin credentials:")
        print(f"  Email: sarah.chen@nova-labs.com")
        print(f"  Password: DemoPass123!")
        print(f"  Organization: Nova Labs")


if __name__ == "__main__":
    asyncio.run(main())