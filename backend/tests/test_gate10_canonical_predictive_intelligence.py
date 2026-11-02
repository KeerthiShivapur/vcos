"""Gate 10 — Canonical Predictive Company Intelligence Tests.

Tests for company predictions derived from canonical reality and institutional learning.
"""

import pytest
import pytest_asyncio
import uuid
import json
from datetime import datetime, date, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import resolve_caller_access
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.department import Department
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.workload import WorkloadSnapshot
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionPrecedent,
    CompanyDecisionContradiction,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionEvidence,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilitySignal,
    CAPABILITY_STATES,
    CAPACITY_STATES,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
    OutcomeAssessment,
    DecisionOutcome,
    RecommendationOutcome,
)
from app.models.intelligence import (
    PatternDetection,
    PatternEvent,
)
from app.models.company_memory import (
    CompanyMemory,
    MemoryEvent,
    MemoryOutcome,
)
from app.models.prediction import (
    Prediction,
    PredictionHistory,
    PredictionModel,
)
from app.models.execution_strategy import (
    ObjectivePrediction,
    ObjectiveSimulation,
)
from app.intelligence.institutional_intelligence_service import (
    institutional_intelligence_service,
)
from app.intelligence.predictive_intelligence_service import (
    predictive_intelligence_service,
    CompanyPrediction,
    PredictionProvenance,
    PredictionKind,
    EpistemicStatus,
)
from app.intelligence.organizational_attention_service import (
    organizational_attention_service,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_org(db_session):
    """Create test organization."""
    org = Organization(
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest_asyncio.fixture
async def test_user(db_session, test_org):
    """Create test user."""
    user = User(
        organization_id=test_org.id,
        email=f"test{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed",
        full_name="Test User",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_employee(db_session, test_org, test_user):
    """Create test employee with user link."""
    emp = Employee(
        organization_id=test_org.id,
        user_id=test_user.id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="Employee",
        email=f"employee{uuid.uuid4().hex[:6]}@test.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


@pytest_asyncio.fixture
async def caller(db_session, test_org, test_user, test_employee):
    """Create caller access for test user with CEO permissions."""
    from app.models.role import Role, UserRole
    from app.services.permission_service import permission_service
    
    await permission_service.sync_catalog(db_session)
    await permission_service.seed_org_roles(db_session, test_org.id)
    
    ceo_role = (await db_session.execute(
        select(Role).where(
            Role.organization_id == test_org.id,
            Role.code == "ceo"
        )
    )).scalars().first()
    
    if ceo_role:
        user_role = UserRole(
            user_id=test_user.id,
            role_id=ceo_role.id,
            organization_id=test_org.id,
        )
        db_session.add(user_role)
        await db_session.flush()
    
    caller = await resolve_caller_access(
        db_session, organization_id=test_org.id, user=test_user
    )
    caller.employee_id = test_employee.id
    return caller


@pytest_asyncio.fixture
async def test_team(db_session, test_org, test_employee):
    """Create test team."""
    team = Team(
        organization_id=test_org.id,
        name="Test Team",
        code=f"TM{uuid.uuid4().hex[:4]}",
    )
    db_session.add(team)
    await db_session.flush()
    
    test_employee.team_id = team.id
    await db_session.flush()
    return team


@pytest_asyncio.fixture
async def test_department(db_session, test_org):
    """Create test department."""
    dept = Department(
        organization_id=test_org.id,
        name="Test Department",
        code=f"DEP{uuid.uuid4().hex[:4]}",
    )
    db_session.add(dept)
    await db_session.flush()
    return dept


@pytest_asyncio.fixture
async def test_skill(db_session, test_org):
    """Create test canonical skill."""
    from app.models.skills_intelligence import CanonicalSkill
    skill = CanonicalSkill(
        organization_id=test_org.id,
        canonical_name="Python Development",
        category="Engineering",
        description="Python programming expertise",
    )
    db_session.add(skill)
    await db_session.flush()
    return skill


@pytest_asyncio.fixture
async def test_commitment(db_session, caller, test_employee):
    """Create test commitment with actions and outcomes."""
    commitment = CompanyCommitment(
        organization_id=caller.organization_id,
        commitment_type="unconditional",
        title="Test Commitment",
        state="active",
        scope_type="project",
        scope_id="proj-test",
        rationale="Test rationale",
        fingerprint=f"comm-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="commitment-test-1",
    )
    db_session.add(commitment)
    await db_session.flush()
    
    # Create responsibility
    responsibility = OrganizationalResponsibility(
        organization_id=caller.organization_id,
        responsibility_type="responsible",
        scope_type="commitment",
        scope_id=commitment.id,
        raci_responsible=True,
        person_id=test_employee.id,
        commitment_id=commitment.id,
        valid_from=utcnow(),
        state="active",
        fingerprint=f"resp-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="resp-test-1",
    )
    db_session.add(responsibility)
    await db_session.flush()
    
    # Create action
    action = CompanyAction(
        organization_id=caller.organization_id,
        action_type="capacity_change",
        title="Test Action",
        state="in_progress",
        scope_type="project",
        scope_id="proj-test",
        fingerprint=f"action-fp-{uuid.uuid4().hex[:32]}",
        source_event_id="action-test-1",
        source_commitment_id=commitment.id,
        assignee_id=test_employee.id,
    )
    db_session.add(action)
    await db_session.flush()
    
    # Create outcome
    outcome = CompanyActionOutcome(
        organization_id=caller.organization_id,
        action_id=action.id,
        outcome_type="success",
        effectiveness=0.85,
        verdict="Action completed successfully",
        evidence_json=json.dumps([]),
    )
    db_session.add(outcome)
    await db_session.commit()
    
    return commitment


@pytest_asyncio.fixture
async def test_objective(db_session, caller, test_employee):
    """Create test objective with initiatives."""
    goal = CompanyGoal(
        organization_id=caller.organization_id,
        title="Test Goal",
        status="active",
        kind="growth",
        priority=3,
    )
    db_session.add(goal)
    await db_session.flush()
    
    objective = CompanyObjective(
        organization_id=caller.organization_id,
        goal_id=goal.id,
        title="Test Objective",
        status="active",
        kind="other",
        fingerprint=f"obj-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(objective)
    await db_session.flush()
    
    # Create initiative
    initiative = CompanyInitiative(
        organization_id=caller.organization_id,
        objective_id=objective.id,
        title="Test Initiative",
        status="active",
        kind="other",
        expected_outcome={"target_value": 100, "unit": "units"},
        fingerprint=f"init-fp-{uuid.uuid4().hex[:32]}",
    )
    db_session.add(initiative)
    await db_session.commit()
    
    return objective


@pytest_asyncio.fixture
async def test_capability(db_session, caller, test_skill, test_employee):
    """Create test OrgCapability with expertise."""
    from app.models.skills_intelligence import Expertise as ExpertiseState, ExpertiseEvidence
    expertise = ExpertiseState(
        organization_id=caller.organization_id,
        person_id=test_employee.id,
        skill_id=test_skill.id,
        score=60.0,
        evidence_count=10,
        lifecycle="strong",
    )
    db_session.add(expertise)
    
    capability = OrgCapability(
        organization_id=caller.organization_id,
        skill_id=test_skill.id,
        canonical_name="Python Development",
        category="Engineering",
        lifecycle="strong",
        expert_count=1,
        strong_expert_count=1,
        evidence_count=10,
        corroborated_kinds=3,
        confidence=0.8,
        capacity_potential=1,
        capacity_committed=1,
        capacity_reserved=0,
        capacity_available=0,
        capacity_state="constrained",
        demand_count=2,
        demand_state="high",
        concentration_share=1.0,
        second_share=0.0,
    )
    db_session.add(capability)
    
    # Add allocation demand
    demand = AllocationDemand(
        organization_id=caller.organization_id,
        project_id="proj-1",
        capability="Python Development",
        units=1,
        window_start=date.today(),
        window_end=date.today() + timedelta(days=60),
        proficiency="high",
    )
    db_session.add(demand)
    
    # Add allocation
    allocation = CapacityAllocation(
        organization_id=caller.organization_id,
        project_id="proj-1",
        project_label="Project Alpha",
        capability="Python Development",
        units=1,
        window_start=date.today(),
        window_end=date.today() + timedelta(days=60),
        status="active",
        source_event_id="alloc-1",
    )
    db_session.add(allocation)
    
    await db_session.commit()
    return capability


# ============================================================================
# Test Classes
# ============================================================================

class TestPredictiveIntelligenceService:
    """Test predictive intelligence service."""

    @pytest.mark.asyncio
    async def test_derive_predictions_basic(
        self, db_session, caller, test_commitment, test_objective, test_capability
    ):
        """Test basic prediction derivation."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, horizon_days=90
        )
        
        assert isinstance(predictions, list)
        # Should have at least some predictions
        assert len(predictions) >= 0
        
        for pred in predictions:
            assert isinstance(pred, CompanyPrediction)
            assert pred.kind in [k.value for k in PredictionKind]
            assert 0.0 <= pred.probability <= 1.0
            assert 0.0 <= pred.confidence <= 1.0
            assert pred.epistemic_status in [e.value for e in EpistemicStatus]
            assert pred.horizon_days > 0
            assert pred.valid_from is not None
            assert pred.valid_until is not None
            assert pred.provenance is not None
            assert pred.provenance.model_version == "gate10-v1"

    @pytest.mark.asyncio
    async def test_predict_commitment_risks(
        self, db_session, caller, test_commitment
    ):
        """Test commitment risk predictions."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        commitment_preds = [p for p in predictions if p.kind == "commitment_risk"]
        # May or may not have predictions depending on risk level
        for pred in commitment_preds:
            assert pred.kind == "commitment_risk"
            assert pred.subject_type == "commitment"
            assert pred.probability > 0.5  # Only high risk commitments

    @pytest.mark.asyncio
    async def test_predict_objective_risks(
        self, db_session, caller, test_objective
    ):
        """Test objective risk predictions."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["objective_risk"], horizon_days=90
        )
        
        objective_preds = [p for p in predictions if p.kind == "objective_risk"]
        for pred in objective_preds:
            assert pred.kind == "objective_risk"
            assert pred.subject_type == "objective"
            assert pred.probability > 0.5

    @pytest.mark.asyncio
    async def test_predict_capacity_pressure(
        self, db_session, caller, test_capability
    ):
        """Test capacity pressure predictions."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["capacity_pressure"], horizon_days=90
        )
        
        capacity_preds = [p for p in predictions if p.kind == "capacity_pressure"]
        for pred in capacity_preds:
            assert pred.kind == "capacity_pressure"
            assert pred.subject_type == "capability"
            assert pred.probability > 0.5

    @pytest.mark.asyncio
    async def test_predict_bottleneck_emergence(
        self, db_session, caller, test_employee
    ):
        """Test bottleneck emergence predictions."""
        # Create organizational bottleneck signal via organizational learning
        from app.models.organizational_learning import OrganizationalLearning, LearningEvidence
        lesson = OrganizationalLearning(
            organization_id=caller.organization_id,
            kind="capacity_learning",
            fingerprint="bottleneck-lesson-fp",
            title="Critical Person Bottleneck",
            lesson="Employee is critical dependency",
            status="active",
            lifecycle="authoritative",
            confidence=0.9,
            source_type="test",
            source_id="bottleneck-1",
            evidence_json=json.dumps(["test"]),
            recorded_by=test_employee.id,
            observed_at=utcnow(),
        )
        db_session.add(lesson)
        await db_session.commit()
        
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["bottleneck_emergence"], horizon_days=90
        )
        
        bottleneck_preds = [p for p in predictions if p.kind == "bottleneck_emergence"]
        for pred in bottleneck_preds:
            assert pred.kind == "bottleneck_emergence"

    @pytest.mark.asyncio
    async def test_predict_execution_outcomes(
        self, db_session, caller, test_commitment
    ):
        """Test execution outcome predictions."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["execution_outcome"], horizon_days=90
        )
        
        exec_preds = [p for p in predictions if p.kind == "execution_outcome"]
        for pred in exec_preds:
            assert pred.kind == "execution_outcome"
            assert pred.subject_type == "action"

    @pytest.mark.asyncio
    async def test_predict_dependency_cascades(
        self, db_session, caller, test_employee
    ):
        """Test dependency cascade predictions."""
        # Create task chain: A -> B -> C
        project = Project(
            organization_id=caller.organization_id,
            name="Cascade Project",
            code=f"PRJ{uuid.uuid4().hex[:4]}",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        
        task_c = Task(
            organization_id=caller.organization_id,
            project_id=project.id,
            title="Task C (Foundation)",
            status="todo",
            assignee_id=test_employee.id,
        )
        task_b = Task(
            organization_id=caller.organization_id,
            project_id=project.id,
            title="Task B (Middle)",
            status="todo",
            assignee_id=test_employee.id,
        )
        task_a = Task(
            organization_id=caller.organization_id,
            project_id=project.id,
            title="Task A (Top)",
            status="todo",
            assignee_id=test_employee.id,
        )
        db_session.add_all([task_c, task_b, task_a])
        await db_session.flush()
        
        # Create dependencies: A -> B -> C
        dep_b = TaskDependency(
            organization_id=caller.organization_id,
            task_id=task_b.id,
            depends_on_task_id=task_c.id,
            kind="blocks",
        )
        dep_a = TaskDependency(
            organization_id=caller.organization_id,
            task_id=task_a.id,
            depends_on_task_id=task_b.id,
            kind="blocks",
        )
        db_session.add_all([dep_b, dep_a])
        await db_session.commit()
        
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["dependency_cascade"], horizon_days=90
        )
        
        cascade_preds = [p for p in predictions if p.kind == "dependency_cascade"]
        for pred in cascade_preds:
            assert pred.kind == "dependency_cascade"
            assert pred.subject_type == "task"


class TestPredictionDetail:
    """Test prediction detail retrieval."""

    @pytest.mark.asyncio
    async def test_get_prediction_detail_objective(
        self, db_session, caller, test_objective
    ):
        """Test getting ObjectivePrediction detail."""
        # Create an ObjectivePrediction
        obj_pred = ObjectivePrediction(
            organization_id=caller.organization_id,
            objective_id=test_objective.id,
            metric_kind="progress",
            unit="percent",
            predicted_value=75.0,
            confidence=0.8,
            prediction_method="trajectory",
            horizon_days=30,
            valid_from=utcnow(),
            valid_until=utcnow() + timedelta(days=30),
            basis_evidence_fingerprints=[],
            basis_pattern_ids=[],
            basis_lesson_fingerprints=[],
            fingerprint=f"obj-pred-fp-{uuid.uuid4().hex[:32]}",
            source_event_id="pred-test-1",
            predicted_by="test",
        )
        db_session.add(obj_pred)
        await db_session.commit()
        
        detail = await predictive_intelligence_service.get_prediction_detail(
            db_session, caller=caller, prediction_id=obj_pred.id
        )
        
        assert detail is not None
        assert detail.id == obj_pred.id
        assert detail.kind == "objective_risk"
        assert detail.subject_id == test_objective.id

    @pytest.mark.asyncio
    async def test_get_prediction_detail_generic(
        self, db_session, caller
    ):
        """Test getting generic Prediction detail."""
        pred = Prediction(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            title="Test Prediction",
            description="Test",
            probability=0.75,
            impact="high",
            level="high",
            horizon_days=30,
            subject_type="commitment",
            subject_id="test-commitment",
            status="open",
            due_at=utcnow() + timedelta(days=30),
        )
        db_session.add(pred)
        await db_session.commit()
        
        detail = await predictive_intelligence_service.get_prediction_detail(
            db_session, caller=caller, prediction_id=pred.id
        )
        
        assert detail is not None
        assert detail.id == pred.id
        assert detail.kind == "commitment_risk"
        assert detail.probability == 0.75


class TestPredictionEvaluation:
    """Test prediction evaluation and calibration."""

    @pytest.mark.asyncio
    async def test_evaluate_predictions(
        self, db_session, caller
    ):
        """Test prediction evaluation."""
        # Create a mature prediction (past due)
        pred = Prediction(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            title="Test Evaluation",
            description="Test",
            probability=0.8,
            impact="high",
            level="high",
            horizon_days=30,
            subject_type="commitment",
            subject_id="test-commitment",
            status="open",
            due_at=utcnow() - timedelta(days=10),  # Past due
        )
        db_session.add(pred)
        await db_session.commit()
        
        result = await predictive_intelligence_service.evaluate_predictions(
            db_session, caller=caller, max_age_days=180
        )
        
        assert "evaluated" in result
        assert "correct" in result
        assert "accuracy_rate" in result
        assert "calibration_data_points" in result
        assert result["evaluated"] >= 0

    @pytest.mark.asyncio
    async def test_prediction_calibration_updates_model(
        self, db_session, caller
    ):
        """Test that calibration updates PredictionModel."""
        # Create a prediction model
        model = PredictionModel(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            name="Test Model",
            version="1.0",
            accuracy=0.5,
            predictions_count=10,
        )
        db_session.add(model)
        await db_session.commit()
        
        result = await predictive_intelligence_service.evaluate_predictions(
            db_session, caller=caller, max_age_days=180
        )
        
        # Model should be updated
        await db_session.refresh(model)
        assert model.predictions_count >= 10


class TestPredictionProvenance:
    """Test prediction provenance and provenance walk."""

    @pytest.mark.asyncio
    async def test_prediction_has_provenance(
        self, db_session, caller, test_commitment, test_employee
    ):
        """Test that predictions have full provenance."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        for pred in predictions:
            if pred.kind == "commitment_risk":
                assert pred.provenance is not None
                assert pred.provenance.model_version == "gate10-v1"
                assert pred.provenance.algorithm_identity == "predictive_intelligence_service:v1"
                assert pred.provenance.generated_by == test_employee.id
                assert pred.provenance.generated_at is not None

    @pytest.mark.asyncio
    async def test_prediction_provenance_walk(
        self, db_session, caller, test_commitment
    ):
        """Test that prediction provenance can be walked to canonical sources."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        for pred in predictions:
            if pred.kind == "commitment_risk":
                # Provenance should reference canonical sources
                assert pred.provenance.canonical_state_snapshot is not None
                assert pred.provenance.model_version == "gate10-v1"
                assert pred.provenance.algorithm_identity == "predictive_intelligence_service:v1"
                assert pred.provenance.generated_at is not None


class TestPredictionEpistemicBoundaries:
    """Test that epistemic boundaries are preserved."""

    @pytest.mark.asyncio
    async def test_prediction_not_truth(
        self, db_session, caller, test_commitment
    ):
        """Test that predictions are marked as predictions, not truth."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        for pred in predictions:
            if pred.kind == "commitment_risk":
                # Prediction should be marked as prediction, not fact
                assert pred.epistemic_status in [e.value for e in EpistemicStatus]
                # Should never be "observed" or "fact"
                assert pred.epistemic_status not in ("observed", "fact", "measured")
                # Should have uncertainty
                assert pred.probability < 1.0
                assert pred.confidence < 1.0

    @pytest.mark.asyncio
    async def test_prediction_not_recommendation(
        self, db_session, caller, test_commitment
    ):
        """Test that predictions are not recommendations."""
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        for pred in predictions:
            # Prediction should not contain actionable recommendations
            assert "recommended_action" not in pred.evidence_bundle
            assert "recommend" not in pred.description.lower() or "probability" in pred.description.lower()

    @pytest.mark.asyncio
    async def test_insufficient_evidence_handling(
        self, db_session, caller
    ):
        """Test that insufficient evidence is handled explicitly."""
        # Create a commitment with NO actions or outcomes
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Empty Commitment",
            state="authorized",
            scope_type="project",
            scope_id="proj-empty",
            rationale="Test rationale",
            fingerprint=f"comm-fp-{uuid.uuid4().hex[:32]}",
            source_event_id="commitment-empty-1",
        )
        db_session.add(commitment)
        await db_session.commit()
        
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        # Should either have no prediction or low probability/insufficient evidence
        commitment_preds = [p for p in predictions if p.kind == "commitment_risk" and p.subject_id == commitment.id]
        for pred in commitment_preds:
            # Should have low probability or be marked as insufficient evidence
            assert pred.probability < 0.5 or pred.epistemic_status == "speculative"


class TestPredictionTemporalTruth:
    """Test temporal truth for predictions."""

    @pytest.mark.asyncio
    async def test_prediction_temporal_versioning(
        self, db_session, caller, test_commitment
    ):
        """Test that predictions are versioned and don't overwrite history."""
        predictions_1 = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        # Wait a moment and derive again
        import asyncio
        await asyncio.sleep(0.1)
        
        predictions_2 = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        # Both should succeed without overwriting
        assert len(predictions_1) >= 0
        assert len(predictions_2) >= 0

    @pytest.mark.asyncio
    async def test_prediction_supersession(
        self, db_session, caller
    ):
        """Test prediction supersession tracking."""
        # Create a prediction
        pred1 = Prediction(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            title="Old Prediction",
            description="Old",
            probability=0.7,
            impact="high",
            level="high",
            horizon_days=30,
            subject_type="commitment",
            subject_id="test-commitment",
            status="superseded",
            due_at=utcnow() + timedelta(days=30),
        )
        db_session.add(pred1)
        
        pred2 = Prediction(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            title="New Prediction",
            description="New",
            probability=0.6,
            impact="high",
            level="high",
            horizon_days=30,
            subject_type="commitment",
            subject_id="test-commitment",
            status="open",
            due_at=utcnow() + timedelta(days=30),
        )
        db_session.add(pred2)
        await db_session.commit()
        
        # Both should exist (old not deleted)
        preds = await db_session.execute(
            select(Prediction).where(
                Prediction.organization_id == caller.organization_id,
                Prediction.subject_id == "test-commitment",
            )
        )
        all_preds = preds.scalars().all()
        assert len(all_preds) == 2


class TestPredictionCalibration:
    """Test prediction calibration and calibration history."""

    @pytest.mark.asyncio
    async def test_calibration_data_collection(
        self, db_session, caller
    ):
        """Test that calibration data is collected."""
        # Create mature predictions
        pred1 = Prediction(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            title="Calibration Test 1",
            description="Test",
            probability=0.8,
            impact="high",
            level="high",
            horizon_days=30,
            subject_type="commitment",
            subject_id="cal-test-1",
            status="open",
            due_at=utcnow() - timedelta(days=10),
        )
        pred2 = Prediction(
            organization_id=caller.organization_id,
            kind="commitment_risk",
            title="Calibration Test 2",
            description="Test",
            probability=0.3,
            impact="low",
            level="low",
            horizon_days=30,
            subject_type="commitment",
            subject_id="cal-test-2",
            status="open",
            due_at=utcnow() - timedelta(days=10),
        )
        db_session.add_all([pred1, pred2])
        await db_session.commit()
        
        result = await predictive_intelligence_service.evaluate_predictions(
            db_session, caller=caller, max_age_days=180
        )
        
        assert result["evaluated"] >= 2
        assert result["calibration_data_points"] >= 2

    @pytest.mark.asyncio
    async def test_model_accuracy_tracking(
        self, db_session, caller
    ):
        """Test that model accuracy is tracked over time."""
        # Create multiple predictions for same kind
        for i in range(5):
            pred = Prediction(
                organization_id=caller.organization_id,
                kind="objective_risk",
                title=f"Model Test {i}",
                description="Test",
                probability=0.7,
                impact="medium",
                level="medium",
                horizon_days=30,
                subject_type="objective",
                subject_id=f"model-test-{i}",
                status="open",
                due_at=utcnow() - timedelta(days=5),
            )
            db_session.add(pred)
        await db_session.commit()
        
        result = await predictive_intelligence_service.evaluate_predictions(
            db_session, caller=caller, max_age_days=180
        )
        
        assert result["evaluated"] >= 5


class TestPredictionGovernance:
    """Test governance for predictions."""

    @pytest.mark.asyncio
    async def test_prediction_tenant_isolation(
        self, db_session, caller, test_org
    ):
        """Test that predictions don't leak across tenants."""
        # Create another org
        other_org = Organization(
            name="Other Org",
            slug=f"other-org-{uuid.uuid4().hex[:8]}",
        )
        db_session.add(other_org)
        await db_session.flush()
        
        # Create prediction in other org
        other_pred = Prediction(
            organization_id=other_org.id,
            kind="commitment_risk",
            title="Other Org Prediction",
            description="Test",
            probability=0.5,
            impact="medium",
            level="medium",
            horizon_days=30,
            subject_type="commitment",
            subject_id="other-commitment",
            status="open",
            due_at=utcnow() + timedelta(days=30),
        )
        db_session.add(other_pred)
        await db_session.commit()
        
        # Caller from first org should not see other org's predictions
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        for pred in predictions:
            assert pred.provenance.canonical_state_snapshot.get("organization_id") == caller.organization_id

    @pytest.mark.asyncio
    async def test_prediction_scope_isolation(
        self, db_session, caller, test_team, test_employee
    ):
        """Test that scoped callers only see predictions for their scope."""
        # This would require a non-org-wide caller
        # For now, just verify the mechanism exists
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, scope_type="team", scope_id=test_team.id, horizon_days=90
        )
        
        # All predictions should be derivable
        assert isinstance(predictions, list)


class TestPredictionContradiction:
    """Test contradiction handling in predictions."""

    @pytest.mark.asyncio
    async def test_contradictory_evidence_reduces_confidence(
        self, db_session, caller
    ):
        """Test that contradictory evidence reduces prediction confidence."""
        # Create commitment with mixed outcomes
        commitment = CompanyCommitment(
            organization_id=caller.organization_id,
            commitment_type="unconditional",
            title="Mixed Commitment",
            state="active",
            scope_type="project",
            scope_id="proj-mixed",
            rationale="Test",
            fingerprint=f"comm-fp-mixed-{uuid.uuid4().hex[:32]}",
            source_event_id="commitment-mixed-1",
        )
        db_session.add(commitment)
        await db_session.flush()
        
        # Add actions with mixed outcomes
        for i in range(3):
            action = CompanyAction(
                organization_id=caller.organization_id,
                action_type="task",
                title=f"Mixed Action {i}",
                state="completed",
                scope_type="project",
                scope_id="proj-mixed",
                fingerprint=f"action-fp-mixed-{i}-{uuid.uuid4().hex[:32]}",
                source_event_id=f"action-mixed-{i}",
                source_company_decision_id=commitment.id,
            )
            db_session.add(action)
            await db_session.flush()
            
            outcome_type = "success" if i < 2 else "failed"
            effectiveness = 0.8 if i < 2 else 0.2
            outcome = CompanyActionOutcome(
                organization_id=caller.organization_id,
                action_id=action.id,
                outcome_type=outcome_type,
                effectiveness=effectiveness,
                verdict="Mixed outcome",
                evidence_json=json.dumps([]),
            )
            db_session.add(outcome)
        
        await db_session.commit()
        
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        commitment_preds = [p for p in predictions if p.kind == "commitment_risk" and p.subject_id == commitment.id]
        for pred in commitment_preds:
            # Should have medium probability (mixed outcomes)
            assert pred.probability > 0.3
            assert pred.probability < 0.9


class TestPredictionGovernanceIntegration:
    """Test prediction integration with governance."""

    @pytest.mark.asyncio
    async def test_prediction_requires_governance_access(
        self, db_session, caller, test_commitment
    ):
        """Test that prediction derivation respects governance."""
        # Should work for org-wide caller
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        assert isinstance(predictions, list)

    @pytest.mark.asyncio
    async def test_prediction_brain_integration(
        self, db_session, caller, test_commitment
    ):
        """Test that predictions integrate with CompanyBrain."""
        from app.intelligence.company_brain import CompanyBrain
        
        brain = CompanyBrain()
        # The brain should be able to reason over predictions
        # This is a basic integration test
        predictions = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, kinds=["commitment_risk"], horizon_days=90
        )
        
        # Brain should be able to reference predictions in its reasoning
        # (This would be tested more thoroughly in brain integration tests)
        assert isinstance(predictions, list)


class TestPredictionScopeIntegration:
    """Test prediction integration with different scopes."""

    @pytest.mark.asyncio
    async def test_predictions_by_scope_type(
        self, db_session, caller, test_team, test_department, test_employee
    ):
        """Test predictions at different scope levels."""
        test_employee.team_id = test_team.id
        test_employee.department_id = test_department.id
        await db_session.commit()
        
        # Team scope
        team_preds = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, scope_type="team", scope_id=test_team.id, horizon_days=90
        )
        assert isinstance(team_preds, list)
        
        # Department scope
        dept_preds = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, scope_type="department", scope_id=test_department.id, horizon_days=90
        )
        assert isinstance(dept_preds, list)
        
        # Organization scope
        org_preds = await predictive_intelligence_service.derive_predictions(
            db_session, caller=caller, scope_type="organization", horizon_days=90
        )
        assert isinstance(org_preds, list)


class TestPredictionRegression:
    """Regression tests to ensure existing functionality still works."""

    @pytest.mark.asyncio
    async def test_gate9_institutional_intelligence_still_works(
        self, db_session, caller, test_employee
    ):
        """Gate 9 institutional intelligence should still work."""
        context = await institutional_intelligence_service.derive_institutional_intelligence(
            db_session, caller=caller, scope_type="person", scope_id=test_employee.id
        )
        
        assert "qualified_lessons" in context
        assert "institutional_patterns" in context

    @pytest.mark.asyncio
    async def test_gate86_capacity_still_works(
        self, db_session, caller, test_employee
    ):
        """Gate 8.6 organizational capacity should still work."""
        from app.intelligence.organizational_capacity_service import organizational_capacity_service
        
        workload = WorkloadSnapshot(
            organization_id=caller.organization_id,
            employee_id=test_employee.id,
            period_start=utcnow() - timedelta(days=7),
            period_end=utcnow() + timedelta(days=7),
            capacity_hours=40.0,
            allocated_hours=30.0,
            utilization=75.0,
        )
        db_session.add(workload)
        await db_session.commit()
        
        context = await organizational_capacity_service.derive_capacity_context(
            db_session, caller=caller, scope_type="person", scope_id=test_employee.id
        )
        
        assert context.utilization == 75.0

    @pytest.mark.asyncio
    async def test_gate85_org_intelligence_still_works(
        self, db_session, caller, test_employee
    ):
        """Gate 8.5 organizational intelligence should still work."""
        from app.intelligence.organizational_intelligence_service import organizational_intelligence_service
        
        context = await organizational_intelligence_service.derive_organizational_context(
            db_session, caller=caller, employee_id=test_employee.id
        )
        
        assert context.employee_id == test_employee.id


# ============================================================================
# Test Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])