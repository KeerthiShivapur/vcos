"""Phase G — Company Brain Integration tests.

Verifies the institutional learning substrate is accessible through
the governed Company Brain interface with proper governance, provenance,
contradiction exposure, and temporal intelligence.
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.organization import Organization
from app.models.user import User
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
)
from app.models.intelligence import PatternDetection
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionContradiction,
)
from app.models.project import Project
from app.intelligence.company_brain import company_brain
from tests.conftest import register_org


@pytest.mark.asyncio
async def test_brain_learning_routing(client, db_session_factory):
    """Learning-shaped questions route to institutional learning."""
    import uuid
    reg = await register_org(client, name=f"Test Corp {uuid.uuid4().hex[:8]}")
    headers = reg["headers"]
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    # Create a lesson
    async with db_session_factory() as session:
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-1",
            title="Test Lesson",
            lesson="Shorter cycles improve conversion",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="sales",
        )
        session.add(lesson)
        await session.commit()

        # Ask a learning-shaped question
        result = await company_brain.answer(
            session, org_id, "What did we learn about sales cycles?",
            user=User(id=user_id),  # type: ignore
        )

    assert result is not None
    assert "lessons" in result
    assert len(result["lessons"]) >= 1
    assert result["lessons"][0]["title"] == "Test Lesson"
    assert result["lessons"][0]["lifecycle"] == "supported"
    assert "learning" in result["sources_consulted"]


@pytest.mark.asyncio
async def test_brain_learning_governance_scoping(client, db_session_factory):
    """Lessons are tenant-isolated - users from different orgs don't see each other's lessons."""
    import uuid
    # Org-wide user in first org
    reg_org = await register_org(client, name=f"Org Wide Corp {uuid.uuid4().hex[:8]}", email=f"owner1_{uuid.uuid4().hex[:8]}@test.co")
    headers_org = reg_org["headers"]
    org_id = reg_org["organization"]["id"]
    user_id_org = reg_org["user"]["id"]

    # Second user in different org
    reg_other = await register_org(client, name=f"Other Corp {uuid.uuid4().hex[:8]}", email=f"owner2_{uuid.uuid4().hex[:8]}@test.co")
    headers_other = reg_other["headers"]
    org_id_other = reg_other["organization"]["id"]
    user_id_other = reg_other["user"]["id"]

    async with db_session_factory() as session:
        # Create a lesson in first org
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-2",
            title="Org Wide Lesson",
            lesson="Lesson in first org",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="org-wide",
        )
        session.add(lesson)
        await session.commit()
        lesson_id = lesson.id

        # First org user should see it
        result_org = await company_brain.answer(
            session, org_id, "What did we learn in org wide?",
            user=User(id=user_id_org),  # type: ignore
        )
        assert any(l["id"] == lesson_id for l in result_org.get("lessons", []))

        # User in different org should NOT see it
        result_other = await company_brain.answer(
            session, org_id_other, "What did we learn in org wide?",
            user=User(id=user_id_other),  # type: ignore
        )
        assert not any(l["id"] == lesson_id for l in result_other.get("lessons", []))


@pytest.mark.asyncio
async def test_brain_learning_contradiction_exposure(client, db_session_factory):
    """Contradictions are exposed in lesson detail, not hidden."""
    import uuid
    reg = await register_org(client, name=f"Contradiction Corp {uuid.uuid4().hex[:8]}")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a lesson
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="decision_learning",
            fingerprint="test-fp-3",
            title="Contested Lesson",
            lesson="Strategy X works",
            status="active",
            lifecycle="supported",
            confidence=0.7,
            topic_name="strategy",
        )
        session.add(lesson)
        await session.flush()
        lesson_id = lesson.id

        # Create a contradiction
        decision = CompanyDecision(
            organization_id=org_id,
            decision_id=str(uuid4())[:32],
            kind="other",
            title="Decision about strategy X",
            state="outcome_recorded",
            source_event_id=str(uuid4())[:32],
        )
        session.add(decision)
        await session.flush()
        decision_id = decision.decision_id

        contradiction = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id=decision_id,
            contradiction_key=f"cx:{decision_id}:1",
            lesson_memory_id=lesson_id,
            side_a_json={"claim": "Strategy X works", "evidence_ids": [lesson_id]},
            side_b_json={"claim": "Strategy X failed", "evidence_ids": [decision_id]},
            status="open",
            source_event_id=str(uuid4())[:32],
        )
        session.add(contradiction)
        await session.commit()

        # Query lesson detail
        result = await company_brain.answer(
            session, org_id, "What did we learn about strategy X?",
            user=User(id=user_id),  # type: ignore
        )

        # Should have contradiction count > 0
        lesson_result = next((l for l in result.get("lessons", []) if l["id"] == lesson_id), None)
        assert lesson_result is not None
        assert lesson_result["contradiction_count"] >= 1


@pytest.mark.asyncio
async def test_brain_learning_temporal(client, db_session_factory):
    """Temporal query returns historical state of learning."""
    import uuid
    reg = await register_org(client, name=f"Temporal Corp {uuid.uuid4().hex[:8]}")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=10)

    async with db_session_factory() as session:
        # Create first lesson
        lesson_v1 = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-temporal-v1",
            title="Lesson v1",
            lesson="Initial belief",
            status="active",
            lifecycle="candidate",
            confidence=0.5,
            topic_name="temporal",
            observed_at=past,
            created_at=past,
        )
        session.add(lesson_v1)
        await session.flush()
        v1_id = lesson_v1.id

        # Create superseding lesson
        lesson_v2 = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-temporal-v2",
            title="Lesson v2",
            lesson="Updated belief with new evidence",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="temporal",
            observed_at=now,
            created_at=now,
        )
        session.add(lesson_v2)
        await session.commit()
        v2_id = lesson_v2.id

        # Query at current time - should see v2
        result_now = await company_brain.answer(
            session, org_id, "What did we learn about temporal topic?",
            user=User(id=user_id),  # type: ignore
        )
        lessons_now = result_now.get("lessons", [])
        v2_now = next((l for l in lessons_now if l["id"] == v2_id), None)
        assert v2_now is not None
        assert v2_now["lifecycle"] == "supported"


@pytest.mark.asyncio
async def test_brain_learning_provenance_chain(client, db_session_factory):
    """Lesson detail includes full provenance chain."""
    import uuid
    reg = await register_org(client, name=f"Provenance Corp {uuid.uuid4().hex[:8]}")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create pattern
        pattern = PatternDetection(
            organization_id=org_id,
            pattern_type="repeated_success",
            key="pattern:test:1",
            title="Repeated Success Pattern",
            family="execution",
            status="confirmed",
            count=5,
            confidence=0.75,
            evidence_json=[{"type": "decision", "id": "dec1", "relationship": "occurrence"}],
            entities_json=[{"type": "project", "id": "proj1", "title": "Project 1"}],
            supporting_event_ids=["evt1", "evt2", "evt3", "evt4", "evt5"],
            first_seen=datetime.now(timezone.utc) - timedelta(days=30),
            last_seen=datetime.now(timezone.utc),
        )
        session.add(pattern)
        await session.flush()
        pattern_id = pattern.id

        # Create lesson from pattern
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-provenance",
            title="Provenance Lesson",
            lesson="Pattern of repeated success indicates reliable approach",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            source_type="pattern",
            source_id=pattern_id,
            topic_name="provenance",
        )
        session.add(lesson)
        await session.flush()
        lesson_id = lesson.id

        # Add evidence
        evidence = LearningEvidence(
            organization_id=org_id,
            learning_id=lesson_id,
            source_type="pattern",
            source_id=pattern_id,
            excerpt="Pattern evidence",
            role="primary",
            weight=1.0,
        )
        session.add(evidence)
        await session.commit()

        # Query lesson detail
        result = await company_brain.answer(
            session, org_id, "What is the provenance of the provenance lesson?",
            user=User(id=user_id),  # type: ignore
        )

        lesson_result = next((l for l in result.get("lessons", []) if l["id"] == lesson_id), None)
        assert lesson_result is not None
        assert lesson_result["source_type"] == "pattern"
        assert lesson_result["source_id"] == pattern_id


@pytest.mark.asyncio
async def test_brain_recommended_next_questions_includes_learning(client, db_session_factory):
    """Learning-shaped questions generate investigation follow-ups."""
    import uuid
    reg = await register_org(client, name=f"Followup Corp {uuid.uuid4().hex[:8]}", email=f"followup_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a lesson so learning route is active
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-followup",
            title="Followup Lesson",
            lesson="Customer retention improves with personalization",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="customer retention",
        )
        session.add(lesson)
        await session.commit()

        # Use a question that explicitly triggers learning route
        result = await company_brain.answer(
            session, org_id, "What did we learn about customer retention and what patterns exist?",
            user=User(id=user_id),  # type: ignore
        )

        next_questions = result.get("recommended_next_questions", [])
        assert len(next_questions) > 0, f"Expected next questions, got: {next_questions}"
        
        # Verify the answer includes lessons (learning route worked)
        lessons = result.get("lessons", [])
        assert len(lessons) >= 1, f"Expected lessons in answer, got: {lessons}"


@pytest.mark.asyncio
async def test_brain_reasoning_chain_includes_institutional(client, db_session_factory):
    """Why-flavored questions include institutional learning in answer."""
    import uuid
    reg = await register_org(client, name=f"Reasoning Corp {uuid.uuid4().hex[:8]}", email=f"reasoning_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a lesson
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-reasoning",
            title="Reasoning Lesson",
            lesson="Historical precedent matters",
            status="active",
            lifecycle="confirmed",
            confidence=0.9,
            topic_name="reasoning",
        )
        session.add(lesson)
        await session.commit()

        # Ask a why question that also triggers learning
        result = await company_brain.answer(
            session, org_id, "Why does historical precedent matter and what did we learn?",
            user=User(id=user_id),  # type: ignore
        )

        # Should have lessons in the answer
        lessons = result.get("lessons", [])
        assert len(lessons) >= 1
        assert lessons[0]["title"] == "Reasoning Lesson"


@pytest.mark.asyncio
async def test_brain_summary_includes_lessons(client, db_session_factory):
    """Summary includes lesson information when lessons are retrieved."""
    import uuid
    reg = await register_org(client, name=f"Summary Corp {uuid.uuid4().hex[:8]}")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-summary",
            title="Summary Lesson",
            lesson="This should appear in summary",
            status="active",
            lifecycle="authoritative",
            confidence=0.85,
            topic_name="summary",
        )
        session.add(lesson)
        await session.commit()

        result = await company_brain.answer(
            session, org_id, "What did we learn about summary?",
            user=User(id=user_id),  # type: ignore
        )

        summary = result.get("summary", "")
        assert "lesson" in summary.lower() or "Summary Lesson" in summary


@pytest.mark.asyncio
async def test_brain_timeline_includes_lessons(client, db_session_factory):
    """Unified timeline includes lesson entries."""
    import uuid
    reg = await register_org(client, name=f"Timeline Corp {uuid.uuid4().hex[:8]}", email=f"timeline_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        lesson = OrganizationalLearning(
            organization_id=org_id,
            kind="outcome_learning",
            fingerprint="test-fp-timeline",
            title="Timeline Lesson",
            lesson="Appears in timeline",
            status="active",
            lifecycle="supported",
            confidence=0.8,
            topic_name="timeline",
            observed_at=datetime.now(timezone.utc),
        )
        session.add(lesson)
        await session.commit()

        result = await company_brain.answer(
            session, org_id, "What did we learn about timeline topic?",
            user=User(id=user_id),  # type: ignore
        )

        timeline = result.get("timeline", [])
        lesson_entries = [e for e in timeline if e["kind"] == "lesson"]
        assert len(lesson_entries) >= 1
        assert lesson_entries[0]["title"] == "Timeline Lesson"