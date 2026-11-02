"""
Phase I Gate 4 — Longitudinal Company Operating Simulation.

This test creates a synthetic company and operates it through multiple cycles,
traversing the complete canonical company graph across multiple operating cycles.
"""

import pytest
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.team import Team
from app.models.department import Department
from app.models.company_intent import CompanyIntent, CompanyPlan
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    StrategicOutcome,
    StrategicLink,
    VerificationEvidence,
    VerificationContext,
    ObjectiveOutcome,
    ObjectiveOutcomeAssessment,
    _compute_fingerprint,
)
from app.models.company_operating import CompanyDecision, CompanyDecisionContradiction
from app.models.company_actions import CompanyAction
from app.models.project import Project
from app.models.task import Task
from app.intelligence.company_planning_context_engine import company_planning_context_engine
from app.intelligence.adaptive_planning_engine import adaptive_planning_engine
from app.intelligence.decision_intelligence_engine import decision_intelligence_engine
from app.intelligence.governed_commitment_engine import governed_commitment_engine
from app.intelligence.adaptive_execution_engine import adaptive_execution_engine
from app.intelligence.verification_orchestration_engine import verification_orchestration_engine
from app.intelligence.company_brain import company_brain
from tests.conftest import register_org
from app.core.timeutils import utcnow


async def _create_department(db: AsyncSession, org_id: str, name: str, code: str) -> Department:
    dept = Department(
        organization_id=org_id,
        name=name,
        code=code,
    )
    db.add(dept)
    await db.flush()
    return dept


async def _create_team(db: AsyncSession, org_id: str, dept_id: str, name: str, code: str) -> Team:
    team = Team(
        organization_id=org_id,
        department_id=dept_id,
        name=name,
        code=code,
    )
    db.add(team)
    await db.flush()
    return team


async def _create_employee(db: AsyncSession, org_id: str, name: str = "Test Person") -> str:
    emp = Employee(
        organization_id=org_id,
        email=f"{uuid.uuid4().hex[:8]}@test.co",
        employee_number=f"EMP{hashlib.sha256(f'emp:{name}'.encode()).hexdigest()[:8].upper()}",
        first_name=name.split()[0],
        last_name=" ".join(name.split()[1:]) if len(name.split()) > 1 else "",
        display_name=name,
        status="active",
    )
    db.add(emp)
    await db.flush()
    await db.commit()
    return emp.id


async def _create_minimal_canonical_chain(db_session_factory, org_id: str) -> dict[str, str]:
    """Create minimal canonical data chain: Intent -> Goal -> Objective -> Initiative."""
    async with db_session_factory() as session:
        intent = CompanyIntent(
            organization_id=org_id,
            kind="strategic",
            title="Test Intent for 4I.9",
            state="active",
            fingerprint=hashlib.sha256(f"intent:4i9-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(intent)
        await session.flush()

        goal = CompanyGoal(
            organization_id=org_id,
            title="Test Goal for 4I.9",
            status="active",
            kind="expansion",
        )
        session.add(goal)
        await session.flush()

        objective = CompanyObjective(
            organization_id=org_id,
            goal_id=goal.id,
            title="Test Objective for 4I.9",
            description="Test objective for longitudinal company simulation",
            status="active",
            fingerprint=hashlib.sha256(f"objective:4i9-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(objective)
        await session.flush()

        initiative = CompanyInitiative(
            organization_id=org_id,
            objective_id=objective.id,
            title="Test Initiative for 4I.9",
            description="Test initiative for longitudinal company simulation",
            status="active",
            fingerprint=hashlib.sha256(f"initiative:4i9-test:{org_id}".encode()).hexdigest()[:160],
        )
        session.add(initiative)
        await session.flush()

        await session.commit()
        return {
            "intent_id": intent.id,
            "goal_id": goal.id,
            "objective_id": objective.id,
            "initiative_id": initiative.id,
        }


async def _create_intent(db: AsyncSession, org_id: str, title: str) -> CompanyIntent:
    intent = CompanyIntent(
        organization_id=org_id,
        kind="strategic",
        title=title,
        state="active",
        fingerprint=hashlib.sha256(f"intent:4i9-test:{org_id}".encode()).hexdigest()[:160],
    )
    db.add(intent)
    await db.flush()
    return intent


async def _create_goal(db: AsyncSession, org_id: str, title: str) -> CompanyGoal:
    goal = CompanyGoal(
        organization_id=org_id,
        title=title,
        status="active",
        kind="expansion",
    )
    db.add(goal)
    await db.flush()
    return goal


async def _create_objective(db: AsyncSession, org_id: str, goal_id: str, intent_id: str, title: str) -> CompanyObjective:
    objective = CompanyObjective(
        organization_id=org_id,
        goal_id=goal_id,
        intent_id=intent_id,
        title=title,
        description=f"Objective for {title}",
        status="active",
        fingerprint=hashlib.sha256(f"objective:4i9-test:{org_id}".encode()).hexdigest()[:160],
    )
    db.add(objective)
    await db.flush()
    return objective


async def _create_initiative(db: AsyncSession, org_id: str, objective_id: str, title: str) -> CompanyInitiative:
    init = CompanyInitiative(
        organization_id=org_id,
        objective_id=objective_id,
        title=title,
        description=f"Initiative for {title}",
        status="active",
        fingerprint=hashlib.sha256(f"initiative:{title}".encode()).hexdigest()[:160],
    )
    db.add(init)
    await db.flush()
    return init


async def _create_project(db: AsyncSession, org_id: str, name: str) -> Project:
    from app.models.project import Project
    proj = Project(
        organization_id=org_id,
        name=name,
        code=f"PRJ{hashlib.sha256(name.encode()).hexdigest()[:6].upper()}",
        status="active",
    )
    db.add(proj)
    await db.flush()
    return proj


async def _create_decision(db: AsyncSession, org_id: str, title: str) -> CompanyDecision:
    dec = CompanyDecision(
        organization_id=org_id,
        kind="strategic",
        title=title,
        recommendation_key="",
        rationale="Test decision",
        state="approved",
        approver_label="test",
        decision_id=hashlib.sha256(f"dec:{title}".encode()).hexdigest()[:160],
        source_event_id=f"test-event-{uuid.uuid4().hex[:8]}",
    )
    db.add(dec)
    await db.flush()
    return dec


async def _create_authorization(db: AsyncSession, org_id: str, decision_id: str, title: str) -> CompanyAuthorization:
    auth = CompanyAuthorization(
        organization_id=org_id,
        authorization_type="full",
        title=title,
        scope_type="company",
        state="approved",
        decision_id=decision_id,
        fingerprint=hashlib.sha256(f"auth:{title}".encode()).hexdigest()[:160],
    )
    db.add(auth)
    await db.flush()
    return auth


async def _create_commitment(db: AsyncSession, org_id: str, decision_id: str, auth_id: str, title: str) -> CompanyCommitment:
    comm = CompanyCommitment(
        organization_id=org_id,
        commitment_type="conditional",
        title=title,
        scope_type="objective",
        decision_id=decision_id,
        authorization_id=auth_id,
        state="authorized",
        fingerprint=hashlib.sha256(f"commit:{title}".encode()).hexdigest()[:160],
    )
    db.add(comm)
    await db.flush()
    return comm


async def _create_responsibility(db: AsyncSession, org_id: str, commitment_id: str, raci: dict) -> OrganizationalResponsibility:
    resp = OrganizationalResponsibility(
        organization_id=org_id,
        commitment_id=commitment_id,
        person_id=raci.get("person_id"),
        team_id=raci.get("team_id"),
        department_id=raci.get("department_id"),
        role_id=raci.get("role_id"),
        responsibility_type=raci.get("responsibility_type", "responsible"),
        raci_accountable=raci.get("raci_accountable", False),
        raci_responsible=raci.get("raci_responsible", False),
        raci_consulted=raci.get("raci_consulted", False),
        raci_informed=raci.get("raci_informed", False),
        valid_from=datetime.now(timezone.utc).date(),
        fingerprint=hashlib.sha256(f"resp:{raci.get('person_id', '')}:{commitment_id}".encode()).hexdigest()[:160],
    )
    db.add(resp)
    await db.flush()
    return resp


async def _create_action(db: AsyncSession, org_id: str, person_id: str, title: str) -> CompanyAction:
    from app.models.company_actions import CompanyAction
    action = CompanyAction(
        organization_id=org_id,
        action_type="work",
        title=title,
        description=f"Action for {title}",
        state="proposed",
        assignee_type="employee",
        assignee_id=person_id,
        assigned_at=utcnow(),
        fingerprint=hashlib.sha256(f"action:{title}".encode()).hexdigest()[:160],
    )
    db.add(action)
    await db.flush()
    return action


async def _create_work(db: AsyncSession, org_id: str, person_id: str, title: str) -> Task:
    from app.models.task import Task
    work = Task(
        organization_id=org_id,
        title=title,
        status="in_progress",
        assignee_id=person_id,
    )
    db.add(work)
    await db.flush()
    return work


async def _create_outcome(db: AsyncSession, org_id: str, initiative_id: str, expected: float, actual: float) -> ObjectiveOutcome:
    variance = ((actual - expected) / expected * 100) if expected else 0
    assessment = "outperformed" if actual > 1.1 * expected else "met" if actual >= 0.9 * expected else "underperformed" if actual >= 0.8 * expected else "missed"
    outcome = ObjectiveOutcome(
        organization_id=org_id,
        objective_id=initiative_id,  # Using initiative_id as objective_id for test
        metric_kind="retention",
        unit="pct",
        expected_value=expected,
        actual_value=actual,
        variance_pct=variance,
        outcome_state="actual",
        assessment=assessment,
        assessment_confidence=0.85,
        source_event_id=f"test-event-{uuid.uuid4().hex[:8]}",
        recorded_at=utcnow(),
        fingerprint=hashlib.sha256(f"outcome:{org_id}:{initiative_id}:{expected}:{actual}".encode()).hexdigest()[:160],
    )
    db.add(outcome)
    await db.flush()
    
    # Also create an assessment
    assessment_record = ObjectiveOutcomeAssessment(
        organization_id=org_id,
        objective_id=initiative_id,
        outcome_id=outcome.id,
        assessment_key=f"assessment-{uuid.uuid4().hex[:8]}",
        assessment=assessment,
        confidence=0.85,
        reasoning=f"Outcome assessment: expected {expected}, actual {actual}",
        variance_pct=variance,
        epistemic_status="measured",
        assessment_state="completed",
        fingerprint=hashlib.sha256(f"assessment:{org_id}:{initiative_id}:{assessment}".encode()).hexdigest()[:160],
    )
    db.add(assessment_record)
    await db.flush()
    return outcome


async def _create_evidence(db: AsyncSession, org_id: str, outcome_id: str, supports: str) -> VerificationEvidence:
    evidence = VerificationEvidence(
        organization_id=org_id,
        verification_id="test-verification",
        evidence_type="metric",
        evidence_id=f"evidence-{uuid.uuid4().hex[:8]}",
        evidence_type_detail="metric",
        summary="Test evidence",
        quality="primary",
        source="test",
        captured_at=utcnow(),
        supports_verdict=supports,
        fingerprint=hashlib.sha256(f"evidence:{org_id}:{outcome_id}:{supports}".encode()).hexdigest()[:160],
    )
    db.add(evidence)
    await db.flush()
    return evidence


async def _create_verification_context(db: AsyncSession, org_id: str, initiative_id: str) -> VerificationContext:
    vc = VerificationContext(
        organization_id=org_id,
        verification_type="plan_vs_reality",
        title="Test Verification",
        description="Test verification context",
        scope_type="company",
        scope_id=None,
        initiative_id=initiative_id,
        trigger="manual_request",
        fingerprint=hashlib.sha256(f"vc:{org_id}:{initiative_id}".encode()).hexdigest()[:160],
        valid_from=utcnow(),
    )
    db.add(vc)
    await db.flush()
    return vc


@pytest.mark.asyncio
async def test_longitudinal_company_simulation(client, db_session_factory):
    """
    Gate 4 — Longitudinal Company Simulation
    
    Runs a synthetic company through 5 operating cycles:
    1. Successful outcome
    2. Underperformance
    3. Contradictory evidence
    4. Capacity disruption
    5. Replanning
    
    Verifies the canonical graph remains consistent across all cycles.
    """
    import uuid
    reg = await register_org(client, name=f"Longitudinal Corp {uuid.uuid4().hex[:8]}", email=f"long_{uuid.uuid4().hex[:8]}@test.co")
    org_id = reg["organization"]["id"]
    user_id = reg["user"]["id"]

    async with db_session_factory() as session:
        # ========== SETUP: Create the company structure ==========
        
        # Create departments
        eng_dept = await _create_department(session, org_id, "Engineering", "ENG")
        prod_dept = await _create_department(session, org_id, "Product", "PRD")
        
        # Create teams
        eng_team = await _create_team(session, org_id, eng_dept.id, "Backend", "BE")
        prod_team = await _create_team(session, org_id, prod_dept.id, "Product", "PD")
        
        # Create employees
        ceo = await _create_employee(session, org_id, "CEO Jane")
        eng_mgr = await _create_employee(session, org_id, "Eng Manager")
        engineer = await _create_employee(session, org_id, "Engineer")
        pm = await _create_employee(session, org_id, "Product Mgr")
        
        # ========== STRATEGIC GRAPH ==========
        intent = await _create_intent(session, org_id, "Increase Customer Retention")
        goal = await _create_goal(session, org_id, "Achieve 90% Retention")
        objective = await _create_objective(session, org_id, goal.id, intent.id, "Reach 90% Retention")
        initiative = await _create_initiative(session, org_id, objective.id, "Improve Onboarding")
        project = await _create_project(session, org_id, "Onboarding Redesign")
        
        # Create strategic link
        link = StrategicLink(
            organization_id=org_id,
            initiative_id=initiative.id,
            project_id=project.id,
            source_event_id="test-link",
            linked_at=datetime.now(timezone.utc),
        )
        session.add(link)
        await session.flush()
        
        # ========== OPERATING GRAPH ==========
        decision = await _create_decision(session, org_id, "Improve Onboarding")
        authorization = await _create_authorization(session, org_id, decision.id, "Authorize Onboarding Project")
        commitment = await _create_commitment(session, org_id, decision.id, authorization.id, "Execute Onboarding Redesign")
        
        # Create responsibilities
        await _create_responsibility(session, org_id, commitment.id, raci={"person_id": eng_mgr, "raci_accountable": True, "raci_responsible": False, "responsibility_type": "accountable"})
        await _create_responsibility(session, org_id, commitment.id, raci={"person_id": engineer, "raci_accountable": False, "raci_responsible": True, "responsibility_type": "responsible"})
        await _create_responsibility(session, org_id, commitment.id, raci={"person_id": pm, "raci_consulted": True, "responsibility_type": "consulted"})
        
        # Create accountability links
        responsibilities = await session.execute(select(OrganizationalResponsibility).where(OrganizationalResponsibility.commitment_id == commitment.id))
        for resp in responsibilities.scalars().all():
            link = AccountabilityLink(
                organization_id=org_id,
                commitment_id=commitment.id,
                authorization_id=authorization.id,
                responsibility_id=resp.id,
                accountability_type="direct",
                valid_from=datetime.now(timezone.utc).date(),
                fingerprint=hashlib.sha256(f"link:{resp.id}".encode()).hexdigest()[:160],
            )
            session.add(link)
        
        await session.flush()
        
        # Create actions
        action1 = await _create_action(session, org_id, eng_mgr, "Design onboarding flow")
        action2 = await _create_action(session, org_id, engineer, "Build onboarding UI")
        action3 = await _create_action(session, org_id, pm, "Write documentation")
        
        # Set actions to in_progress for resource tracking
        for a in [action1, action2, action3]:
            a.state = "in_progress"
        await session.flush()
        
        # Create work
        await _create_work(session, org_id, eng_mgr, "Work for Design onboarding flow")
        await _create_work(session, org_id, engineer, "Work for Build onboarding UI")
        await _create_work(session, org_id, pm, "Work for Write documentation")
        
        await session.commit()
        
        # ========== CYCLE 1: SUCCESSFUL OUTCOME ==========
        print("=== CYCLE 1: Successful Outcome ===")
        outcome1 = await _create_outcome(session, org_id, objective.id, 90, 92)
        evidence1 = await _create_evidence(session, org_id, outcome1.id, "met")
        await session.commit()

        # Verify outcome recorded
        outcomes = await session.execute(select(ObjectiveOutcome).where(ObjectiveOutcome.objective_id == objective.id))
        assert len(outcomes.scalars().all()) == 1
        
        # Trigger adaptive planning
        await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", scope_id=None
        )
        
        # Trigger decision intelligence
        await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="strategic", title="Review Success", scope="company"
        )
        
        await session.commit()
        
        # ========== CYCLE 2: UNDERPERFORMANCE ==========
        print("=== CYCLE 2: Underperformance ===")
        outcome2 = await _create_outcome(session, org_id, objective.id, 90, 68)
        evidence2 = await _create_evidence(session, org_id, outcome2.id, "underperformed")
        await session.commit()

        # Adaptive planning should detect underperformance - force fresh planning context
        from app.intelligence.company_planning_context_engine import company_planning_context_engine
        fresh_pc = await company_planning_context_engine.synthesize_planning_context(session, org_id, scope="company", scope_id=None)
        
        adaptive_ctx = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", scope_id=None, planning_context=fresh_pc
        )
        
        # Verify outcome deviation signal detected (warning level for 1 underperforming outcome)
        outcome_signals = [s for s in adaptive_ctx.attention_signals if s.get("type") == "outcome_deviation"]
        assert len(outcome_signals) > 0, "Expected outcome_deviation signal for underperformance"
        assert adaptive_ctx.attention_count > 0

        # Decision intelligence should be triggered
        await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="strategic", title="Address Underperformance"
        )
        await session.commit()
        
        # ========== CYCLE 3: CONTRADICTORY EVIDENCE ==========
        print("=== CYCLE 3: Contradictory Evidence ===")
        
        contradiction = CompanyDecisionContradiction(
            organization_id=org_id,
            decision_id="test-decision",
            contradiction_key="cx:test-1",
            side_a_json={"claim": "customer satisfaction up", "evidence_ids": ["e1"]},
            side_b_json={"claim": "retention dropped", "evidence_ids": ["e2"]},
            status="open",
            source_event_id="test-contra",
        )
        session.add(contradiction)
        await session.flush()
        await session.commit()
        
        # Verify contradiction preserved
        contradictions = await session.execute(
            select(CompanyDecisionContradiction).where(CompanyDecisionContradiction.organization_id == org_id)
        )
        assert len(contradictions.scalars().all()) == 1
        
        # Company brain should see both sides
        brain_result = await company_brain.answer(
            session, org_id, "What is the status of retention?",
            user=User(id=user_id)
        )
        assert brain_result is not None
        
        # ========== CYCLE 4: CAPACITY DISRUPTION ==========
        print("=== CYCLE 4: Capacity Disruption ===")
        # Simulate engineer capacity drop: create more actions to trigger overload (>5 actions)
        for i in range(4, 10):  # Creates 6 more actions (total 7 for engineer)
            action = await _create_action(session, org_id, engineer, f"Additional task {i}")
            action.state = "in_progress"
            await _create_work(session, org_id, engineer, f"Work for Additional task {i}")
        await session.commit()

        # Adaptive planning should detect capacity issue (overloaded assignee)
        from app.intelligence.company_planning_context_engine import company_planning_context_engine
        fresh_pc = await company_planning_context_engine.synthesize_planning_context(session, org_id, scope="company", scope_id=None)
        adaptive_ctx = await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", scope_id=None, planning_context=fresh_pc
        )
        # Check for resource_contention signal (warning level for overloaded assignees)
        resource_signals = [s for s in adaptive_ctx.attention_signals if s.get("type") == "resource_contention"]
        assert len(resource_signals) > 0, "Expected resource_contention signal for overloaded assignee"
        assert adaptive_ctx.attention_count > 0

        await session.commit()
        
        # ========== CYCLE 5: REPLANNING ==========
        print("=== CYCLE 5: Replanning ===")
        # Trigger adaptive planning with fresh context
        from app.intelligence.company_planning_context_engine import company_planning_context_engine
        fresh_pc = await company_planning_context_engine.synthesize_planning_context(session, org_id, scope="company", scope_id=None)
        await adaptive_planning_engine.synthesize_adaptive_context(
            session, org_id, scope="company", scope_id=None, planning_context=fresh_pc
        )
        
        # Trigger decision intelligence
        await decision_intelligence_engine.synthesize_decision_intelligence(
            session, org_id, decision_type="strategic", title="Address Capacity Crisis"
        )
        
        # Governance should create new authorization
        new_decision = await _create_decision(session, org_id, "Hire Contractor")
        new_auth = await _create_authorization(session, org_id, new_decision.id, "Authorize Contractor")
        new_commitment = await _create_commitment(session, org_id, new_decision.id, new_auth.id, "Hire Contractor")
        
        # New responsibilities
        new_engineer = await _create_employee(session, org_id, "Contractor")
        await _create_responsibility(session, org_id, new_commitment.id, raci={"person_id": new_engineer, "raci_responsible": True})
        
        await session.commit()
        
        # Verify new commitment created
        commitments = await session.execute(
            select(CompanyCommitment).where(CompanyCommitment.organization_id == org_id)
        )
        commitments = list(commitments.scalars().all())
        assert len(commitments) >= 2  # Original + new
        
        # ========== VERIFY CANONICAL GRAPH INTEGRITY ==========
        print("=== VERIFYING CANONICAL GRAPH INTEGRITY ===")
        
        # Verify all entities still linked correctly
        intent_check = await session.get(CompanyIntent, intent.id)
        assert intent_check is not None
        
        goal_check = await session.get(CompanyGoal, goal.id)
        assert goal_check is not None
        
        obj_check = await session.get(CompanyObjective, objective.id)
        assert obj_check is not None
        
        init_check = await session.get(CompanyInitiative, initiative.id)
        assert init_check is not None
        
        proj_check = await session.get(Project, project.id)
        assert proj_check is not None
        
        # Verify decision chain
        decisions = await session.execute(
            select(CompanyDecision).where(CompanyDecision.organization_id == org_id)
        )
        decisions = list(decisions.scalars().all())
        assert len(decisions) >= 2
        
        # Verify commitment chain
        commitments = await session.execute(
            select(CompanyCommitment).where(CompanyCommitment.organization_id == org_id)
        )
        commitments = list(commitments.scalars().all())
        assert len(commitments) >= 2
        
        # Verify responsibilities
        responsibilities = await session.execute(
            select(OrganizationalResponsibility).where(OrganizationalResponsibility.organization_id == org_id)
        )
        responsibilities = list(responsibilities.scalars().all())
        assert len(responsibilities) >= 3
        
        # Verify accountability links
        links = await session.execute(
            select(AccountabilityLink).where(AccountabilityLink.organization_id == org_id)
        )
        links = list(links.scalars().all())
        assert len(links) >= 3
        
# Verify outcomes
        outcomes = await session.execute(
            select(ObjectiveOutcome).where(ObjectiveOutcome.organization_id == org_id)
        )
        outcomes = list(outcomes.scalars().all())
        assert len(outcomes) >= 2
        
        # Verify contradictions
        contradictions = await session.execute(
            select(CompanyDecisionContradiction).where(CompanyDecisionContradiction.organization_id == org_id)
        )
        contradictions = list(contradictions.scalars().all())
        assert len(contradictions) >= 1
        
        print("=== ALL CYCLES COMPLETED SUCCESSFULLY ===")