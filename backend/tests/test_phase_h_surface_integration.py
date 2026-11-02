"""Phase H — API / Surface Integration tests.

Verifies institutional learning is properly integrated into existing
Virtual Company OS surfaces: Projects, Decisions, Dashboard, Intelligence,
Knowledge, and Company Brain.
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.organization import Organization
from app.models.user import User
from app.models.organizational_learning import OrganizationalLearning
from app.models.intelligence import PatternDetection
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionContradiction,
    CompanyDecisionPrecedent,
)
from app.models.project import Project
from app.intelligence.company_brain import company_brain
from tests.conftest import register_org


@pytest.mark.asyncio
async def test_project_learning_endpoint(client, db_session_factory):
    """Project learning endpoint returns relevant lessons and patterns."""
    import uuid
    reg = await register_org(client, name=f"Project Learning Corp {uuid.uuid4().hex[:8]}", email=f"proj_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a project
        project = Project(
            organization_id=org_id,
            name="Test Project",
            code="TEST",
            status="active",
        )
        session.add(project)
        await session.flush()
        project_id = project.id

        # Create a lesson for this project
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-project-1",
            title="Project Lesson",
            lesson="Shorter sprints improve velocity",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="projects",
            source_id=project_id,
        )
        session.add(lesson)

        # Create a pattern for this project
        pattern = PatternDetection(
            organization_id=org_id,
            pattern_type="repeated_velocity_improvement",
            key="pattern:project:1",
            title="Velocity Pattern",
            family="execution",
            status="confirmed",
            count=3,
            confidence=0.75,
            auth_project_id=project_id,
            first_seen=datetime.now(timezone.utc) - timedelta(days=30),
            last_seen=datetime.now(timezone.utc),
        )
        session.add(pattern)
        await session.commit()

        # Query project learning
        response = await client.get(
            f"/api/v1/projects/{project_id}/learning",
            headers=reg["headers"],
        )

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id
    assert len(data["lessons"]) >= 1
    assert data["lessons"][0]["title"] == "Project Lesson"
    assert len(data["patterns"]) >= 1
    assert data["patterns"][0]["title"] == "Velocity Pattern"


@pytest.mark.asyncio
async def test_project_learning_governance(client, db_session_factory):
    """Project learning respects governance - different org can't see it."""
    import uuid
    reg1 = await register_org(client, name=f"Org 1 {uuid.uuid4().hex[:8]}", email=f"org1_{uuid.uuid4().hex[:8]}@test.co")
    reg2 = await register_org(client, name=f"Org 2 {uuid.uuid4().hex[:8]}", email=f"org2_{uuid.uuid4().hex[:8]}@test.co")
    org1_id = reg1["organization"]["id"]
    org2_id = reg2["organization"]["id"]

    async with db_session_factory() as session:
        # Create project and lesson in org1
        project = Project(
            organization_id=org1_id,
            name="Org1 Project",
            code="ORG1",
            status="active",
        )
        session.add(project)
        await session.flush()
        project_id = project.id

        lesson = OrganizationalLearning(
            organization_id=org1_id,
            kind="outcome_learning",
            fingerprint="test-fp-gov-1",
            title="Org1 Lesson",
            lesson="Org1 specific learning",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="projects",
            source_id=project_id,
        )
        session.add(lesson)
        await session.commit()

        # Org1 user can access
        response1 = await client.get(
            f"/api/v1/projects/{project_id}/learning",
            headers=reg1["headers"],
        )
        assert response1.status_code == 200
        assert len(response1.json()["lessons"]) >= 1

        # Org2 user gets 404 (different org)
        response2 = await client.get(
            f"/api/v1/projects/{project_id}/learning",
            headers=reg2["headers"],
        )
        assert response2.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_includes_learning_summary(client, db_session_factory):
    """Dashboard summary includes institutional learning."""
    import uuid
    reg = await register_org(client, name=f"Dashboard Learning Corp {uuid.uuid4().hex[:8]}", email=f"dash_{uuid.uuid4().hex[:8]}@test.co")
    headers = reg["headers"]
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a lesson
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-dash-1",
            title="Dashboard Lesson",
            lesson="Cross-project patterns matter",
            status="active",
            lifecycle="authoritative",
            confidence=0.9,
            topic_name="dashboard",
        )
        session.add(lesson)
        await session.commit()

        # Query Company Brain with a learning-triggering question that will surface this lesson
        result = await company_brain.answer(
            session, org_id, "What did we learn about dashboard and cross-project patterns?",
            user=User(id=user_id),
        )
        assert result is not None
        assert len(result.get("lessons", [])) >= 1

        # Query dashboard
        response = await client.get("/api/v1/dashboard/summary", headers=headers)

    assert response.status_code == 200
    data = response.json()
    # DashboardSummary includes learning_summary
    assert "learning_summary" in data
    assert data["learning_summary"]["recent_lessons_count"] >= 1
    assert len(data["learning_summary"]["top_lessons"]) >= 1


@pytest.mark.asyncio
async def test_intelligence_overview_includes_institutional_learning(client, db_session_factory):
    """Intelligence overview includes institutional learning."""
    import uuid
    reg = await register_org(client, name=f"Intel Learning Corp {uuid.uuid4().hex[:8]}", email=f"intel_{uuid.uuid4().hex[:8]}@test.co")
    headers = reg["headers"]
    org_id = reg["organization"]["id"]

    async with db_session_factory() as session:
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-intel-1",
            title="Intelligence Lesson",
            lesson="Patterns drive insights",
            status="active",
            lifecycle="confirmed",
            confidence=0.85,
            topic_name="intelligence",
        )
        session.add(lesson)
        await session.commit()

        response = await client.get("/api/v1/intelligence/overview", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "institutional_learning" in data
    assert data["institutional_learning"]["lessons_count"] >= 1


@pytest.mark.asyncio
async def test_knowledge_search_with_learning(client, db_session_factory):
    """Knowledge search with learning endpoint returns institutional learning."""
    import uuid
    reg = await register_org(client, name=f"Knowledge Learning Corp {uuid.uuid4().hex[:8]}", email=f"know_{uuid.uuid4().hex[:8]}@test.co")
    headers = reg["headers"]
    org_id = reg["organization"]["id"]

    async with db_session_factory() as session:
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-know-1",
            title="Knowledge Lesson",
            lesson="Documentation quality predicts success",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="documentation",
        )
        session.add(lesson)
        await session.commit()

        response = await client.get(
            "/api/v1/knowledge/search/with-learning?q=documentation",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert "institutional_learning" in data
    assert "lessons" in data["institutional_learning"]
    assert "patterns" in data["institutional_learning"]


@pytest.mark.asyncio
async def test_decision_learning_endpoint(client, db_session_factory):
    """Decision learning endpoint returns relevant lessons and precedents."""
    import uuid
    reg = await register_org(client, name=f"Decision Learning Corp {uuid.uuid4().hex[:8]}", email=f"dec_{uuid.uuid4().hex[:8]}@test.co")
    headers = reg["headers"]
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        from app.people.employee_service import employee_service
        actor = await employee_service.get_by_user(session, organization_id=org_id, user_id=user_id)

        from app.knowledge.decision_service import decision_service
        from app.schemas.knowledge import DecisionCreate

        # Create a decision
        decision = await decision_service.create(
            session, organization_id=org_id,
            payload={"title": "Test Decision", "description": "Test", "project_id": None},
            actor=actor, ip_address="127.0.0.1",
        )
        await session.commit()
        decision_id = decision.id

        # Create a lesson linked to this decision
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="decision_learning",
            fingerprint="test-fp-dec-1",
            title="Decision Lesson",
            lesson="Decisions with more evidence succeed",
            status="active",
            lifecycle="confirmed",
            confidence=0.85,
            topic_name="decisions",
            source_type="decision",
            source_id=decision_id,
        )
        session.add(lesson)

        # Create a precedent
        precedent = CompanyDecisionPrecedent(
            organization_id=org_id,
            decision_id=decision_id,
            precedent_decision_id=str(uuid4())[:32],
            context_signature="kind:other",
            relevance_score=0.8,
            evidence_count=3,
            cited_lesson="Past decisions show evidence matters",
            source_event_id=str(uuid4())[:32],
        )
        session.add(precedent)

        # Create a contradiction
        contradiction = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id=decision_id,
            contradiction_key=f"cx:{decision_id}:1",
            lesson_memory_id=lesson.id,
            side_a_json={"claim": "Decision was good"},
            side_b_json={"claim": "Decision had issues"},
            status="open",
            source_event_id=str(uuid4())[:32],
        )
        session.add(contradiction)
        await session.commit()

        # Query decision learning
        response = await client.get(
            f"/api/v1/decisions/{decision_id}/learning",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["decision_id"] == decision_id
    assert len(data["lessons"]) >= 1
    assert data["lessons"][0]["title"] == "Decision Lesson"
    assert len(data["precedents"]) >= 1
    assert len(data["contradictions"]) >= 1


@pytest.mark.asyncio
async def test_project_learning_timeline(client, db_session_factory):
    """Project learning timeline shows temporal evolution."""
    import uuid
    reg = await register_org(client, name=f"Timeline Corp {uuid.uuid4().hex[:8]}", email=f"tl_{uuid.uuid4().hex[:8]}@test.co")
    headers = reg["headers"]
    org_id = reg["organization"]["id"]

    async with db_session_factory() as session:
        project = Project(
            organization_id=org_id,
            name="Timeline Project",
            code="TL",
            status="active",
        )
        session.add(project)
        await session.flush()
        project_id = project.id

        # Create lesson at different times
        lesson1 = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-tl-1",
            title="Timeline Lesson 1",
            lesson="Early learning",
            status="active",
            lifecycle="candidate",
            confidence=0.5,
            topic_name="timeline",
            source_id=project_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=20),
        )
        session.add(lesson1)

        lesson2 = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-tl-2",
            title="Timeline Lesson 2",
            lesson="Later learning",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="timeline",
            source_id=project_id,
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        session.add(lesson2)
        await session.commit()

        response = await client.get(
            f"/api/v1/projects/{project_id}/learning/timeline?days=30",
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id
    assert len(data["timeline"]) >= 2
    # Should be ordered by time
    assert data["timeline"][0]["title"] == "Timeline Lesson 1"
    assert data["timeline"][1]["title"] == "Timeline Lesson 2"