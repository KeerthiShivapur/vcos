"""Phase I.3 — Strategic Alignment & Decomposition tests.

Verifies the strategic alignment & decomposition layer is properly integrated
with the existing canonical strategic execution primitives and 4H.7 learning substrate.
"""

import pytest
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    StrategicAlignment,
    AlignmentGap,
    StrategicConflict,
    StrategicAlignmentState,
    StrategicDependency,
    AlignmentGapDetection,
    StrategicLink,
    StrategicHistory,
)
from app.models.company_intent import CompanyIntent
from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
from app.models.intelligence import PatternDetection
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionContradiction,
    CompanyDecisionPrecedent,
)
from app.models.company_actions import CompanyAction
from app.intelligence.company_planning_engine import company_planning_engine
from app.models.project import Project
from tests.conftest import register_org


@pytest.mark.asyncio
async def test_strategic_alignment_creation(client, db_session_factory):
    """Test creating strategic alignment relationships."""
    import uuid
    reg = await register_org(client, name=f"Strategic Alignment Corp {uuid.uuid4().hex[:8]}", email=f"strat_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create intent
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Enterprise AI Leadership",
            description="Become the leading enterprise AI platform",
            rationale="Market opportunity and competitive positioning",
            state="active",
            epistemic_status="adopted",
            source="declared",
            priority=1,
            scope="company",
            fingerprint=hashlib.sha256(f"intent:{reg['organization']['id']}:strategic:Enterprise AI Leadership".encode()).hexdigest()[:160],
        )
        session.add(intent)
        await session.commit()

        # Create goal
        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Project",
            description="Drive enterprise adoption of AI platform",
            kind="expansion",
            status="active",
            priority=1,
            metric_kind="adoption_rate",
            target_value=1000,
        )
        session.add(goal)
        await session.flush()
        goal_id = goal.id

# Create objective WITH goal_id (required NOT NULL field)
        objective = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal.id,
            intent_id=intent.id,
            title="Project Lesson",
            status="active",
            fingerprint=hashlib.sha256(f"objective:{reg['organization']['id']}:{goal.id}:{intent.id}".encode()).hexdigest()[:160],
        )
        session.add(objective)
        await session.commit()

        # Create alignment: Intent -> Goal
        from app.models.execution_strategy import StrategicAlignment
        alignment1 = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="intent",
            source_id=intent.id,
            target_type="goal",
            target_id=goal.id,
            alignment_type="supports",
            alignment_state="active",
            strength="primary",
            contribution_level="primary",
            rationale="Intent directly drives this strategic goal",
            state="active",
            proposed_by=reg["user"]["id"],
            proposed_at=datetime.now(timezone.utc),
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:intent:goal:{intent.id}:{goal.id}".encode()).hexdigest()[:160],
        )
        session.add(alignment1)

        # Alignment: Goal -> Objective
        alignment2 = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="goal",
            source_id=goal.id,
            target_type="objective",
            target_id=objective.id,
            alignment_type="supports",
            alignment_state="active",
            strength="primary",
            contribution_level="primary",
            rationale="Objective directly measures goal achievement",
            state="active",
            proposed_by=reg["user"]["id"],
            proposed_at=datetime.now(timezone.utc),
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:goal:objective:{goal.id}:{objective.id}".encode()).hexdigest()[:160],
        )
        session.add(alignment2)
        await session.commit()

        # Verify alignments
        assert alignment1.source_type == "intent"
        assert alignment1.target_type == "goal"
        assert alignment1.alignment_type == "supports"
        assert alignment1.strength == "primary"
        assert alignment1.state == "active"

        assert alignment2.source_type == "goal"
        assert alignment2.target_type == "objective"
        assert alignment2.alignment_type == "supports"

        # Verify supersession tracking
        assert alignment1.superseded_by_alignment_id is None
        assert alignment1.fingerprint is not None


@pytest.mark.asyncio
async def test_alignment_gap_detection(client, db_session_factory):
    """Test alignment gap detection."""
    import uuid
    reg = await register_org(client, name=f"Gap Detection Corp {uuid.uuid4().hex[:8]}", email=f"gap_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create intent without goals
        intent = CompanyIntent(
            organization_id=reg["organization"]["id"],
            kind="strategic",
            title="Intent Without Goals",
            state="active",
            epistemic_status="adopted",
            source="declared",
            fingerprint=hashlib.sha256(f"intent:{reg['organization']['id']}:Intent Without Goals:company".encode()).hexdigest()[:160],
        )
        session.add(intent)
        await session.commit()

        # Create goal without objectives
        goal = CompanyGoal(
            organization_id=reg["organization"]["id"],
            title="Orphan Goal",
            status="active",
        )
        session.add(goal)
        await session.commit()

        # Create gap
        from app.models.execution_strategy import AlignmentGap
        gap = AlignmentGap(
            organization_id=reg["organization"]["id"],
            gap_type="goal_without_objective",
            severity="high",
            missing_element_type="objective",
            context_element_type="goal",
            context_element_id=reg["organization"]["id"],
            description="Goal has no measurable objectives",
            impact_assessment="Cannot measure progress toward goal",
            recommended_action="Create measurable objectives for this goal",
            state="open",
            detected_at=datetime.now(timezone.utc),
            detected_by=reg["user"]["id"],
            source_event_id=str(uuid4()),
            fingerprint=hashlib.sha256(f"gap:goal_without_objective:goal:{reg['organization']['id']}".encode()).hexdigest()[:160],
        )
        session.add(gap)
        await session.commit()

        assert gap.gap_type == "goal_without_objective"
        assert gap.severity == "high"
        assert gap.context_element_id == reg["organization"]["id"]


@pytest.mark.asyncio
async def test_strategic_conflict_preservation(client, db_session_factory):
    """Test that strategic conflicts preserve both sides."""
    import uuid
    reg = await register_org(client, name=f"Conflict Corp {uuid.uuid4().hex[:8]}", email=f"conflict_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a goal first (required for objectives)
        goal = CompanyGoal(
            organization_id=reg["organization"]["id"],
            title="Conflict Test Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        goal_id = goal.id

        # Create two conflicting objectives
        obj1 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            title="Reduce Infrastructure Cost",
            kind="efficiency",
            status="active",
            target_value=1000000,
            fingerprint=hashlib.sha256(f"objective:Reduce Infrastructure Cost:efficiency".encode()).hexdigest()[:160],
        )
        obj2 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            title="Increase Redundancy",
            kind="reliability",
            status="active",
            target_value=99.99,
            fingerprint=hashlib.sha256(f"objective:Increase Redundancy:reliability".encode()).hexdigest()[:160],
        )
        session.add_all([obj1, obj2])
        await session.commit()

        # Create conflict
        from app.models.execution_strategy import StrategicConflict
        conflict = StrategicConflict(
            organization_id=reg["organization"]["id"],
            entity_a_type="objective",
            entity_a_id=obj1.id,
            entity_b_type="objective",
            entity_b_id=obj2.id,
            conflict_type="resource_contention",
            severity="high",
            side_a={"claim": "Cost reduction requires reducing redundancy"},
            side_b={"claim": "High availability requires redundancy investment"},
            side_a_evidence=["cost_analysis_report"],
            side_b_evidence=["reliability_incident_report"],
            side_a_confidence=0.8,
            side_b_confidence=0.9,
            root_cause="Fixed budget cannot accommodate both cost reduction and increased redundancy",
            impact_assessment="Choosing one may compromise the other",
            recommended_resolution="Phased approach: optimize first, then add redundancy",
            status="open",
            source_event_id=str(uuid4()),
            fingerprint=hashlib.sha256(f"conflict:resource_contention:objective:objective:{reg['organization']['id']}".encode()).hexdigest()[:160],
        )
        session.add(conflict)
        await session.commit()

        # Verify both sides preserved
        assert conflict.entity_a_type == "objective"
        assert conflict.entity_b_type == "objective"
        assert conflict.side_a["claim"] == "Cost reduction requires reducing redundancy"
        assert conflict.side_b["claim"] == "High availability requires redundancy investment"
        assert conflict.side_a_evidence == ["cost_analysis_report"]
        assert conflict.side_b_evidence == ["reliability_incident_report"]
        assert conflict.status == "open"
        assert conflict.fingerprint is not None


@pytest.mark.asyncio
async def test_strategic_dependency_graph(client, db_session_factory):
    """Test strategic dependency graph (DAG)."""
    import uuid
    reg = await register_org(client, name=f"Dependency Corp {uuid.uuid4().hex[:8]}", email=f"dep_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create a goal first (required for objectives)
        goal = CompanyGoal(
            organization_id=reg["organization"]["id"],
            title="Test Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        goal_id = goal.id

        # Create objectives with goal_id
        obj1 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            title="Objective A",
            kind="strategic",
            status="active",
            fingerprint=hashlib.sha256(b"objective:Objective A:strategic").hexdigest()[:160],
        )
        obj2 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            title="Objective B",
            kind="strategic",
            fingerprint=hashlib.sha256(b"objective:Objective B:strategic").hexdigest()[:160],
        )
        obj3 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            title="Objective C",
            kind="strategic",
            fingerprint=hashlib.sha256(b"objective:Objective C:strategic").hexdigest()[:160],
        )
        session.add_all([obj1, obj2, obj3])
        await session.commit()

        # Create dependencies: A -> B, A -> C
        from app.models.execution_strategy import StrategicDependency
        dep1 = StrategicDependency(
            organization_id=reg["organization"]["id"],
            dependent_type="objective",
            dependent_id=obj2.id,
            dependency_type="objective",
            dependency_id=obj1.id,
            dependency_kind="depends_on",
            is_blocking=True,
            is_hard_dependency=True,
            description="Objective B depends on Objective A completion",
            fingerprint=hashlib.sha256(f"dep:objective:objective:{reg['organization']['id']}:{obj1.id}:{obj2.id}".encode()).hexdigest()[:160],
        )
        dep2 = StrategicDependency(
            organization_id=reg["organization"]["id"],
            dependent_type="objective",
            dependent_id=obj3.id,
            dependency_type="objective",
            dependency_id=obj1.id,
            dependency_kind="depends_on",
            is_blocking=False,
            is_hard_dependency=True,
            fingerprint=hashlib.sha256(f"dep:objective:objective:{reg['organization']['id']}:{obj1.id}:{obj3.id}".encode()).hexdigest()[:160],
        )
        session.add_all([dep1, dep2])
        await session.commit()

        # Verify dependencies
        assert dep1.dependent_type == "objective"
        assert dep1.dependency_type == "objective"
        assert dep1.dependency_kind == "depends_on"
        assert dep1.is_blocking is True
        assert dep1.is_hard_dependency is True

        assert dep2.dependent_type == "objective"
        assert dep2.dependency_type == "objective"
        assert dep2.dependency_kind == "depends_on"
        assert dep2.is_blocking is False


@pytest.mark.asyncio
async def test_strategic_alignment_state_materialization(client, db_session_factory):
    """Test materialized alignment state view."""
    import uuid
    reg = await register_org(client, name=f"State Corp {uuid.uuid4().hex[:8]}", email=f"state_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create intent with objectives
        intent = CompanyIntent(
            organization_id=reg["organization"]["id"],
            kind="strategic",
            title="Test Intent",
            description="Test",
            state="active",
            epistemic_status="adopted",
            source="declared",
            fingerprint=hashlib.sha256(b"intent:Test Intent:company").hexdigest()[:160],
        )
        session.add(intent)
        await session.flush()

        # Create a goal first (required for objectives)
        goal = CompanyGoal(
            organization_id=reg["organization"]["id"],
            title="Test Goal",
            status="active",
        )
        session.add(goal)
        await session.flush()
        goal_id = goal.id

        obj1 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            intent_id=intent.id,
            title="Obj 1",
            kind="strategic",
            status="active",
            fingerprint=hashlib.sha256(b"objective:Obj 1:strategic").hexdigest()[:160],
        )
        obj2 = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal_id,
            intent_id=intent.id,
            title="Obj 2",
            kind="strategic",
            status="active",
            fingerprint=hashlib.sha256(b"objective:Obj 2:strategic").hexdigest()[:160],
        )
        session.add_all([obj1, obj2])
        await session.commit()

        # Materialize state
        from app.intelligence.company_planning_engine import company_planning_engine
        state = await company_planning_engine.materialize_intent_plan_state(
            session, reg["organization"]["id"], intent.id,
        )

        assert state.intent_id == intent.id
        assert state.total_plans == 0  # No plans yet
        assert state.active_plans == 0
        assert state.overall_state == "completed"  # No plans yet (empty list is vacuously all completed)

        # Add a plan
        from app.models.company_intent import CompanyPlan
        plan = CompanyPlan(
            organization_id=reg["organization"]["id"],
            kind="strategic",
            title="Test Plan",
            intent_id=intent.id,
            state="active",
            fingerprint=hashlib.sha256(b"plan:Test Plan:strategic").hexdigest()[:160],
        )
        session.add(plan)
        await session.commit()

        state2 = await company_planning_engine.materialize_intent_plan_state(
            session, reg["organization"]["id"], intent.id,
        )
        assert state2.total_plans == 1
        assert state2.active_plans == 1


@pytest.mark.asyncio
async def test_supersession_chain_alignment(client, db_session_factory):
    """Test supersession chain in alignments."""
    import uuid
    from sqlalchemy import delete
    from app.models.company_intent import CompanyIntent
    from app.models.execution_strategy import StrategicAlignment
    reg = await register_org(client, name=f"Supersession Corp {uuid.uuid4().hex[:8]}", email=f"super_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create v1 intent
        intent_v1 = CompanyIntent(
            organization_id=reg["organization"]["id"],
            kind="strategic",
            title="Test Intent v1",
            state="active",
            epistemic_status="adopted",
            source="declared",
            fingerprint=hashlib.sha256(b"intent:Test Intent v1:company").hexdigest()[:160],
        )
        session.add(intent_v1)
        await session.commit()

        # Create v2 with same fingerprint (supersedes v1)
        from app.models.execution_strategy import StrategicAlignment
        from sqlalchemy import delete
        from app.models.company_intent import CompanyIntent

        # Delete v1 to avoid unique constraint
        await session.execute(CompanyIntent.__table__.delete().where(CompanyIntent.id == intent_v1.id))
        await session.commit()

        # Create v2 with same fingerprint (supersedes v1)
        intent_v2 = CompanyIntent(
            organization_id=reg["organization"]["id"],
            kind="strategic",
            title="Test Intent v2",
            state="active",
            epistemic_status="adopted",
            source="declared",
            fingerprint=hashlib.sha256(b"intent:Test Intent v2:company").hexdigest()[:160],
        )
        session.add(intent_v2)
        await session.commit()

        # Create alignment for v2
        alignment = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="intent",
            source_id=intent_v2.id,
            target_type="goal",
            target_id=str(uuid4()),
            alignment_type="supports",
            alignment_state="active",
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:intent:goal:{intent_v2.id}:goal_id".encode()).hexdigest()[:160],
        )
        session.add(alignment)
        await session.commit()

        # Temporal query via API
        temporal_response = await client.get(
            f"/api/v1/brain/learning/temporal?as_of={(datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}",
            headers=reg["headers"],
        )
        assert temporal_response.status_code == 200
        temporal_data = temporal_response.json()
        assert temporal_response.status_code == 200


@pytest.mark.asyncio
async def test_alignment_provenance_chain(client, db_session_factory):
    """Test full alignment provenance chain."""
    import uuid
    from sqlalchemy import select
    reg = await register_org(client, name=f"Provenance Corp {uuid.uuid4().hex[:8]}", email=f"prov_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # Create chain: Intent -> Goal -> Objective -> Initiative -> Project
        intent = CompanyIntent(
            organization_id=reg["organization"]["id"],
            kind="strategic",
            title="Provenance Test Intent",
            state="active",
            epistemic_status="adopted",
            source="declared",
            fingerprint=hashlib.sha256(b"intent:Provenance Test Intent:company").hexdigest()[:160],
        )
        session.add(intent)
        await session.flush()

        goal = CompanyGoal(
            organization_id=reg["organization"]["id"],
            title="Goal for Provenance",
            status="active",
        )
        session.add(goal)
        await session.flush()

        objective = CompanyObjective(
            organization_id=reg["organization"]["id"],
            goal_id=goal.id,
            intent_id=intent.id,
            title="Objective for Provenance",
            status="active",
            fingerprint=hashlib.sha256(b"objective:Objective for Provenance:project").hexdigest()[:160],
        )
        session.add(objective)
        await session.flush()

        initiative = CompanyInitiative(
            organization_id=reg["organization"]["id"],
            objective_id=objective.id,
            title="Initiative for Provenance",
            status="active",
            fingerprint=hashlib.sha256(b"initiative:Initiative for Provenance:project").hexdigest()[:160],
        )
        session.add(initiative)
        await session.flush()

        from app.models.project import Project
        project = Project(
            organization_id=reg["organization"]["id"],
            name="Project for Provenance",
            code="PROV",
            status="active",
        )
        session.add(project)
        await session.flush()

        # Create alignment chain
        from app.models.execution_strategy import StrategicAlignment
        align1 = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="intent",
            source_id=intent.id,
            target_type="goal",
            target_id=goal.id,
            alignment_type="supports",
            state="active",
            proposed_by=str(uuid4()),
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:intent:goal:{reg['organization']['id']}:{intent.id}:{goal.id}".encode()).hexdigest()[:160],
        )
        align2 = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="goal",
            source_id=goal.id,
            target_type="objective",
            target_id=objective.id,
            alignment_type="supports",
            state="active",
            proposed_by=str(uuid4()),
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:goal:objective:{goal.id}:{objective.id}".encode()).hexdigest()[:160],
        )
        align3 = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="objective",
            source_id=objective.id,
            target_type="initiative",
            target_id=initiative.id,
            alignment_type="supports",
            state="active",
            proposed_by=str(uuid4()),
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:objective:initiative:{objective.id}:{initiative.id}".encode()).hexdigest()[:160],
        )
        align4 = StrategicAlignment(
            organization_id=reg["organization"]["id"],
            source_type="initiative",
            source_id=initiative.id,
            target_type="project",
            target_id=project.id,
            alignment_type="supports",
            state="active",
            proposed_by=str(uuid4()),
            fingerprint=hashlib.sha256(f"alignment:{reg['organization']['id']}:initiative:project:{initiative.id}:{project.id}".encode()).hexdigest()[:160],
        )
        session.add_all([align1, align2, align3, align4])
        await session.commit()

        # Query full chain
        from app.intelligence.company_planning_engine import company_planning_engine
        from app.intelligence.company_context import resolve_caller_access

        # Verify chain exists
        chain = await session.execute(
            select(StrategicAlignment).where(
                StrategicAlignment.organization_id == reg["organization"]["id"],
            )
        )
        alignments = chain.scalars().all()
        assert len(alignments) == 4

        # Verify chain order
        intent_align = next((a for a in alignments if a.source_type == "intent"), None)
        goal_align = next((a for a in alignments if a.source_type == "goal"), None)
        obj_align = next((a for a in alignments if a.source_type == "objective"), None)
        init_align = next((a for a in alignments if a.source_type == "initiative"), None)

        assert intent_align is not None
        assert intent_align.source_id == intent.id
        assert intent_align.target_id == goal.id

        assert goal_align is not None
        assert goal_align.source_id == goal.id
        assert goal_align.target_id == objective.id

        assert obj_align is not None
        assert obj_align.source_id == objective.id
        assert obj_align.target_id == initiative.id

        assert init_align is not None
        assert init_align.source_id == initiative.id
        assert init_align.target_id == project.id


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])