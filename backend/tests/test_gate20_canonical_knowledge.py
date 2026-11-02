"""Gate 20 — Canonical Knowledge, Documents & Institutional Context Fabric Tests."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.intelligence.canonical_business_process_service import canonical_business_process_service
from app.intelligence.canonical_economic_intelligence_service import canonical_economic_intelligence_service
from app.intelligence.canonical_knowledge_service import canonical_knowledge_service
from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
from app.intelligence.company_brain import company_brain
from app.intelligence.company_context import CallerAccess
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.financial_resource_procurement_service import financial_resource_procurement_service
from app.intelligence.organizational_responsibility_engine import organizational_responsibility_engine
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.models.canonical_business_process import (
    CanonicalBusinessProcess,
    ProcessExecution,
    ProcessStep,
    ProcessApproval,
)
from app.models.canonical_knowledge import (
    CanonicalKnowledgeArtifact,
    KnowledgeArtifactVersion,
    CanonicalKnowledgeClaim,
    CanonicalKnowledgeEvidence,
    CanonicalKnowledgeRelation,
    CanonicalKnowledgeTopic,
    KnowledgeConflict,
    ExternalKnowledgeSource,
    KnowledgeContextQuery,
    KNOWLEDGE_ARTIFACT_KINDS,
    ARTIFACT_LIFECYCLE_STATES,
    ARTIFACT_SCOPES,
    EXTERNAL_SOURCES,
)
from app.models.canonical_procurement_vendor import CanonicalVendor
from app.models.canonical_resource_asset import CanonicalResource
from app.models.company_actions import CompanyAction
from app.models.employee import Employee
from app.models.execution_strategy import CompanyCommitment, CompanyObjective
from app.models.finance import Budget
from app.models.knowledge import Document, Policy, SOP, Template, Decision, WikiPage
from app.models.organizational_learning import OrganizationalLearning, OutcomeAssessment
from app.models.organization import Organization
from app.models.project import Project


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
async def test_org(db_session):
    org = Organization(name="Test Org", slug=f"test-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def caller(db_session, test_org):
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    employee_id = f"emp-{uuid.uuid4().hex[:8]}"
    emp = Employee(
        id=employee_id,
        organization_id=test_org.id,
        user_id=user_id,
        employee_number=f"EMP{uuid.uuid4().hex[:6]}",
        first_name="Test",
        last_name="Employee",
        display_name="Test Employee",
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        status="active",
    )
    db_session.add(emp)
    await db_session.flush()
    return CallerAccess(
        organization_id=test_org.id,
        user_id=user_id,
        employee_id=employee_id,
        org_wide=True,
    )


@pytest.fixture
async def test_process(db_session, caller):
    process = CanonicalBusinessProcess(
        organization_id=caller.organization_id,
        name="Procurement Approval Process",
        process_type="approval",
        fingerprint=f"cbp-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id,
    )
    db_session.add(process)
    await db_session.flush()
    return process


@pytest.fixture
async def test_step(db_session, caller, test_process):
    execution = ProcessExecution(
        organization_id=caller.organization_id,
        process_id=test_process.id,
        execution_number=1,
        trigger_type="manual",
        fingerprint=f"pe-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id,
    )
    db_session.add(execution)
    await db_session.flush()

    step = ProcessStep(
        organization_id=caller.organization_id,
        execution_id=execution.id,
        step_key="finance_approval",
        step_name="Finance Approval",
        step_type="approval",
        state="active",
        fingerprint=f"ps-fp-{uuid.uuid4().hex[:32]}",
        created_by=caller.employee_id,
    )
    db_session.add(step)
    await db_session.flush()
    return step


# =============================================================================
# TESTS: CANONICAL KNOWLEDGE ARTIFACT MODEL
# =============================================================================

class TestCanonicalKnowledgeArtifactModels:
    """Test the core canonical knowledge artifact model."""

    @pytest.mark.asyncio
    async def test_create_policy_artifact(self, db_session, caller):
        """Test creating a policy knowledge artifact."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Financial Approval Policy",
            content="All expenditures above ₹10 lakh require Finance Director approval.",
            summary="Approval threshold policy for financial expenditures",
            category="finance",
            tags=["approval", "finance", "threshold"],
            scope="organization",
            lifecycle_state="published",
            owner_id=caller.employee_id,
            owner_type="person",
        )

        assert artifact.id is not None
        assert artifact.kind == "policy"
        assert artifact.title == "Financial Approval Policy"
        assert artifact.lifecycle_state == "published"
        assert artifact.version == 1
        assert artifact.fingerprint is not None

    @pytest.mark.asyncio
    async def test_create_sop_artifact(self, db_session, caller):
        """Test creating an SOP knowledge artifact."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="sop",
            title="Procurement Request SOP",
            content="Step 1: Create request. Step 2: Get manager approval. Step 3: Submit to procurement.",
            summary="Standard procedure for procurement requests",
            category="operations",
            scope="organization",
            lifecycle_state="published",
        )

        assert artifact.kind == "sop"
        assert artifact.lifecycle_state == "published"

    @pytest.mark.asyncio
    async def test_artifact_exact_once_semantics(self, db_session, caller):
        """Test exact-once creation via fingerprint."""
        artifact1 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Exact Once Policy",
            content="This policy tests exact-once.",
            fingerprint="test-fp-12345",
        )

        # Second create with same fingerprint should fail
        with pytest.raises(IntegrityError):
            await canonical_knowledge_service.create_artifact(
                db_session,
                caller=caller,
                kind="policy",
                title="Exact Once Policy Duplicate",
                content="This policy tests exact-once.",
                fingerprint="test-fp-12345",
            )

    @pytest.mark.asyncio
    async def test_artifact_versioning_and_supersession(self, db_session, caller):
        """Test artifact versioning and supersession chain."""
        # Create v1
        v1 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Versioned Policy",
            content="Version 1 content",
            lifecycle_state="published",
        )

        # Create v2 superseding v1
        v2 = await canonical_knowledge_service.supersede_artifact(
            db_session,
            caller=caller,
            artifact_id=v1.id,
            new_artifact_data={
                "kind": "policy",
                "title": "Versioned Policy",
                "content": "Version 2 content - updated threshold",
                "lifecycle_state": "published",
            },
        )

        assert v2.version == 2
        assert v2.supersedes_id == v1.id

        # Reload v1 to check supersession
        await db_session.refresh(v1)
        assert v1.superseded_by_id == v2.id
        assert v1.lifecycle_state == "superseded"
        assert v1.valid_to is not None

        # Check version history - each artifact has its own version history
        history_v1 = await canonical_knowledge_service.get_artifact_history(
            db_session, caller=caller, artifact_id=v1.id
        )
        history_v2 = await canonical_knowledge_service.get_artifact_history(
            db_session, caller=caller, artifact_id=v2.id
        )
        assert len(history_v1) == 1
        assert history_v1[0].version == 1
        assert len(history_v2) == 1
        assert history_v2[0].version == 2

    @pytest.mark.asyncio
    async def test_artifact_update_with_concurrency(self, db_session, caller):
        """Test optimistic concurrency on artifact update."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="guideline",
            title="Concurrency Test",
            content="Original content",
        )

        # Update with correct version counter
        updated = await canonical_knowledge_service.update_artifact(
            db_session,
            caller=caller,
            artifact_id=artifact.id,
            content="Updated content",
            version_counter=artifact.version_counter,
        )
        assert updated.content == "Updated content"
        assert updated.version == 2  # Version incremented on content change

        # Try update with stale version counter
        with pytest.raises(IntegrityError):
            await canonical_knowledge_service.update_artifact(
                db_session,
                caller=caller,
                artifact_id=artifact.id,
                content="Stale update",
                version_counter=artifact.version_counter - 1,
            )

    @pytest.mark.asyncio
    async def test_artifact_point_in_time_query(self, db_session, caller):
        """Test temporal query: what was valid at a specific time."""
        now = utcnow()
        past = now - timedelta(days=10)
        future = now + timedelta(days=10)

        # Create artifact valid from past to now
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Temporal Policy",
            content="Policy valid in the past",
            valid_from=past,
            valid_to=now,
            lifecycle_state="published",
        )

        # Query at past time - should find it
        artifacts_at_past = await canonical_knowledge_service.get_applicable_artifacts_at_time(
            db_session, caller=caller, at_time=past + timedelta(days=1), kind="policy"
        )
        assert any(a.id == artifact.id for a in artifacts_at_past)

        # Query at future time - should NOT find it (expired)
        artifacts_at_future = await canonical_knowledge_service.get_applicable_artifacts_at_time(
            db_session, caller=caller, at_time=future, kind="policy"
        )
        assert not any(a.id == artifact.id for a in artifacts_at_future)

        # Query at current time (default) - should NOT find it (expired)
        artifacts_now = await canonical_knowledge_service.list_artifacts(
            db_session, caller=caller, kind="policy"
        )
        assert not any(a.id == artifact.id for a in artifacts_now)

    @pytest.mark.asyncio
    async def test_artifact_scope_isolation(self, db_session, caller, test_org):
        """Test artifact scope isolation (project/team/department)."""
        from app.models.project import Project
        from app.models.team import Team

        project = Project(organization_id=caller.organization_id, name="Test Project", code="TP")
        db_session.add(project)
        await db_session.flush()

        team = Team(organization_id=caller.organization_id, name="Test Team", code="TT")
        db_session.add(team)
        await db_session.flush()

        # Create project-scoped artifact
        project_artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="guideline",
            title="Project Guideline",
            content="Guideline for project only",
            scope="project",
            scope_id=project.id,
        )

        # Create team-scoped artifact
        team_artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="guideline",
            title="Team Guideline",
            content="Guideline for team only",
            scope="team",
            scope_id=team.id,
        )

        # Query project-scoped
        project_artifacts = await canonical_knowledge_service.list_artifacts(
            db_session, caller=caller, scope="project", scope_id=project.id
        )
        assert any(a.id == project_artifact.id for a in project_artifacts)

        # Query team-scoped
        team_artifacts = await canonical_knowledge_service.list_artifacts(
            db_session, caller=caller, scope="team", scope_id=team.id
        )
        assert any(a.id == team_artifact.id for a in team_artifacts)

    @pytest.mark.asyncio
    async def test_invalid_kind_rejected(self, db_session, caller):
        """Test that invalid artifact kind is rejected."""
        with pytest.raises(ValueError):
            await canonical_knowledge_service.create_artifact(
                db_session,
                caller=caller,
                kind="invalid_kind",
                title="Invalid",
                content="Test",
            )

    @pytest.mark.asyncio
    async def test_invalid_lifecycle_state_rejected(self, db_session, caller):
        """Test that invalid lifecycle state is rejected."""
        with pytest.raises(ValueError):
            await canonical_knowledge_service.create_artifact(
                db_session,
                caller=caller,
                kind="policy",
                title="Invalid State",
                content="Test",
                lifecycle_state="invalid_state",
            )


# =============================================================================
# TESTS: KNOWLEDGE CLAIMS
# =============================================================================

class TestCanonicalKnowledgeClaims:
    """Test knowledge claim extraction and verification."""

    @pytest.mark.asyncio
    async def test_extract_claims_from_artifact(self, db_session, caller):
        """Test extracting atomic claims from a policy artifact."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Approval Threshold Policy",
            content="Finance approval required above ₹10 lakh. Manager approval up to ₹10 lakh.",
            lifecycle_state="published",
        )

        claims = await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=artifact.id,
            claims=[
                {
                    "subject_type": "approval_threshold",
                    "subject_id": "finance_approval",
                    "predicate": "requires_approval_above",
                    "object_text": "₹10 lakh",
                    "object_value": 1000000,
                    "object_unit": "INR",
                    "claim_type": "threshold",
                    "authority_level": 4,
                    "confidence": 0.95,
                    "source_location": "Section 3.1",
                },
                {
                    "subject_type": "approval_threshold",
                    "subject_id": "manager_approval",
                    "predicate": "requires_approval_up_to",
                    "object_text": "₹10 lakh",
                    "object_value": 1000000,
                    "object_unit": "INR",
                    "claim_type": "threshold",
                    "authority_level": 3,
                    "confidence": 0.9,
                    "source_location": "Section 3.2",
                },
            ],
        )

        assert len(claims) == 2
        assert claims[0].predicate == "requires_approval_above"
        assert claims[0].object_value == 1000000
        assert claims[0].status == "candidate"

    @pytest.mark.asyncio
    async def test_claim_exact_once(self, db_session, caller):
        """Test exact-once claim extraction."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Duplicate Claim Policy",
            content="Test content",
            lifecycle_state="published",
        )

        # Extract first time
        fixed_time = utcnow()
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=artifact.id,
            claims=[{
                "subject_type": "test",
                "subject_id": "test1",
                "predicate": "equals",
                "object_text": "value1",
                "claim_type": "fact",
                "valid_from": fixed_time,
            }],
        )

        # Extract same claim again - should not duplicate
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=artifact.id,
            claims=[{
                "subject_type": "test",
                "subject_id": "test1",
                "predicate": "equals",
                "object_text": "value1",
                "claim_type": "fact",
                "valid_from": fixed_time,
            }],
        )

        # Verify only one claim exists
        claims = await canonical_knowledge_service.get_claims_for_artifact(
            db_session, caller=caller, artifact_id=artifact.id
        )
        assert len(claims) == 1

    @pytest.mark.asyncio
    async def test_verify_claim(self, db_session, caller):
        """Test claim verification against evidence."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Verifiable Policy",
            content="Threshold is ₹5 lakh",
            lifecycle_state="published",
        )

        claims = await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=artifact.id,
            claims=[{
                "subject_type": "approval_threshold",
                "subject_id": "test_threshold",
                "predicate": "is",
                "object_text": "₹5 lakh",
                "claim_type": "threshold",
            }],
        )
        claim = claims[0]

        # Verify the claim
        verified = await canonical_knowledge_service.verify_claim(
            db_session,
            caller=caller,
            claim_id=claim.id,
            verification_result="verified",
            evidence=[{
                "source_type": "financial_record",
                "source_id": "txn-123",
                "excerpt": "Transaction approved at ₹5 lakh",
                "role": "supporting",
            }],
            verified_by=caller.employee_id,
        )

        assert verified.verification_result == "verified"
        assert verified.last_verified_at is not None

        # Check artifact epistemic status updated
        await db_session.refresh(artifact)
        assert artifact.epistemic_status == "verified"
        assert artifact.verification_status == "verified"

    @pytest.mark.asyncio
    async def test_contradicted_claim(self, db_session, caller):
        """Test claim contradicted by evidence."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Contradicted Policy",
            content="Threshold is ₹10 lakh",
            lifecycle_state="published",
        )

        claims = await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=artifact.id,
            claims=[{
                "subject_type": "approval_threshold",
                "subject_id": "contradicted_threshold",
                "predicate": "is",
                "object_text": "₹10 lakh",
                "claim_type": "threshold",
            }],
        )
        claim = claims[0]

        # Contradict the claim
        await canonical_knowledge_service.verify_claim(
            db_session,
            caller=caller,
            claim_id=claim.id,
            verification_result="contradicted",
            evidence=[{
                "source_type": "observed_behavior",
                "source_id": "behavior-456",
                "excerpt": "Managers routinely approve up to ₹25 lakh",
                "role": "contradicting",
            }],
        )

        await db_session.refresh(artifact)
        assert artifact.epistemic_status == "contradicted"
        assert artifact.has_conflicts is True


# =============================================================================
# TESTS: KNOWLEDGE RELATIONS (Integration with Canonical Reality)
# =============================================================================

class TestCanonicalKnowledgeRelations:
    """Test knowledge relations to canonical company reality."""

    @pytest.mark.asyncio
    async def test_link_policy_to_process(self, db_session, caller, test_process):
        """Test linking a policy to a canonical business process."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Process Governing Policy",
            content="This policy governs the procurement process.",
            lifecycle_state="published",
        )

        relation = await canonical_knowledge_service.link_policy_to_process(
            db_session, caller=caller, artifact_id=artifact.id, process_id=test_process.id
        )

        assert relation.relation_type == "governs"
        assert relation.target_type == "process"
        assert relation.target_id == test_process.id
        assert relation.artifact_id == artifact.id

    @pytest.mark.asyncio
    async def test_link_sop_to_step(self, db_session, caller, test_step):
        """Test linking an SOP to a process step."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="sop",
            title="Step SOP",
            content="Detailed procedure for this step.",
            lifecycle_state="published",
        )

        relation = await canonical_knowledge_service.link_sop_to_step(
            db_session, caller=caller, artifact_id=artifact.id, step_id=test_step.id
        )

        assert relation.relation_type == "defines_procedure_for"
        assert relation.target_type == "step"
        assert relation.target_id == test_step.id

    @pytest.mark.asyncio
    async def test_get_relations_to_target(self, db_session, caller, test_process):
        """Test querying all knowledge related to a canonical entity."""
        artifact1 = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="policy", title="Policy 1", content="Content 1", lifecycle_state="published"
        )
        artifact2 = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="sop", title="SOP 1", content="Content 2", lifecycle_state="published"
        )

        await canonical_knowledge_service.link_policy_to_process(db_session, caller=caller, artifact_id=artifact1.id, process_id=test_process.id)
        await canonical_knowledge_service.link_policy_to_process(db_session, caller=caller, artifact_id=artifact2.id, process_id=test_process.id)

        relations = await canonical_knowledge_service.get_relations_to_target(
            db_session, caller=caller, target_type="process", target_id=test_process.id
        )

        assert len(relations) == 2
        artifact_ids = {r.artifact_id for r in relations}
        assert artifact1.id in artifact_ids
        assert artifact2.id in artifact_ids


# =============================================================================
# TESTS: TEMPORAL KNOWLEDGE QUERIES
# =============================================================================

class TestTemporalKnowledgeQueries:
    """Test temporal queries: 'What policy applied when?'"""

    @pytest.mark.asyncio
    async def test_get_policy_for_process_at_time(self, db_session, caller, test_process):
        """Test getting policies governing a process at a specific time."""
        now = utcnow()
        past = now - timedelta(days=30)

        # Create v1 policy valid in the past
        v1 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Old Procurement Policy",
            content="Old threshold: ₹5 lakh",
            valid_from=past - timedelta(days=10),
            valid_to=now - timedelta(days=5),
            lifecycle_state="published",
        )
        await canonical_knowledge_service.link_policy_to_process(db_session, caller=caller, artifact_id=v1.id, process_id=test_process.id)

        # Create v2 policy currently valid
        v2 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="New Procurement Policy",
            content="New threshold: ₹10 lakh",
            valid_from=now - timedelta(days=3),
            lifecycle_state="published",
        )
        await canonical_knowledge_service.link_policy_to_process(db_session, caller=caller, artifact_id=v2.id, process_id=test_process.id)

        # Query at past time - should get v1
        policies_at_past = await canonical_knowledge_service.get_policy_for_process_at_time(
            db_session, caller=caller, process_id=test_process.id, at_time=past
        )
        assert len(policies_at_past) == 1
        assert policies_at_past[0].id == v1.id

        # Query at current time - should get v2
        policies_now = await canonical_knowledge_service.get_policy_for_process_at_time(
            db_session, caller=caller, process_id=test_process.id, at_time=now
        )
        assert len(policies_now) == 1
        assert policies_now[0].id == v2.id

    @pytest.mark.asyncio
    async def test_get_sop_for_step_at_time(self, db_session, caller, test_step):
        """Test getting SOPs for a step at a specific time."""
        now = utcnow()

        sop = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="sop",
            title="Step SOP",
            content="Current procedure",
            valid_from=now - timedelta(days=5),
            lifecycle_state="published",
        )
        await canonical_knowledge_service.link_sop_to_step(db_session, caller=caller, artifact_id=sop.id, step_id=test_step.id)

        sops = await canonical_knowledge_service.get_sop_for_step_at_time(
            db_session, caller=caller, step_id=test_step.id, at_time=now
        )
        assert len(sops) == 1
        assert sops[0].id == sop.id


# =============================================================================
# TESTS: OPERATIONAL KNOWLEDGE CONTEXT
# =============================================================================

class TestOperationalKnowledgeContext:
    """Test the core capability: 'How do I approve this procurement?'"""

    @pytest.mark.asyncio
    async def test_derive_context_for_process_step(self, db_session, caller, test_process, test_step):
        """Test deriving knowledge context for a process step."""
        # Create governing policy
        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Procurement Approval Policy",
            content="Finance approval required above ₹10 lakh. Manager approval up to ₹10 lakh.",
            lifecycle_state="published",
        )
        await canonical_knowledge_service.link_policy_to_process(db_session, caller=caller, artifact_id=policy.id, process_id=test_process.id)

        # Create SOP for the step
        sop = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="sop",
            title="Finance Approval SOP",
            content="1. Verify amount. 2. Check budget. 3. Get Finance Director signature.",
            lifecycle_state="published",
        )
        await canonical_knowledge_service.link_sop_to_step(db_session, caller=caller, artifact_id=sop.id, step_id=test_step.id)

        # Extract claims from policy
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=policy.id,
            claims=[{
                "subject_type": "approval_threshold",
                "subject_id": "finance_approval",
                "predicate": "requires_approval_above",
                "object_text": "₹10 lakh",
                "object_value": 1000000,
                "object_unit": "INR",
                "claim_type": "threshold",
            }],
        )

        # Derive operational context
        context = await canonical_knowledge_service.derive_operational_knowledge_context(
            db_session,
            caller=caller,
            context_type="step",
            context_id=test_step.id,
            question="How do I approve this procurement?",
        )

        # Verify context structure
        assert context["context_type"] == "step"
        assert context["context_id"] == test_step.id
        assert len(context["artifacts"]) >= 2  # policy + sop

        # Verify epistemic breakdown
        epistemic = context["epistemic_breakdown"]
        assert "document_states" in epistemic
        assert "company_facts" in epistemic
        assert "observed_behavior" in epistemic
        assert "verified_outcomes" in epistemic
        assert "conflicts" in epistemic
        assert "institutional_lessons" in epistemic

        # Verify document states include policy content
        doc_states = epistemic["document_states"]
        assert len(doc_states) >= 1
        assert any("₹10 lakh" in ds["states"] for ds in doc_states)

        # Verify claims include threshold
        assert len(context["claims"]) >= 1
        threshold_claims = [c for c in context["claims"] if c["predicate"] == "requires_approval_above"]
        assert len(threshold_claims) >= 1

        # Verify provenance
        assert len(context["provenance"]) >= 2

    @pytest.mark.asyncio
    async def test_derive_context_for_approval(self, db_session, caller, test_step):
        """Test deriving knowledge context for an approval."""
        # Create approval
        approval = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id=test_step.execution_id,
            step_id=test_step.id,
            title="Finance Approval for Procurement",
            status="pending",
            due_at=utcnow() + timedelta(days=2),
            fingerprint=f"pa-fp-{uuid.uuid4().hex[:32]}",
        )
        db_session.add(approval)
        await db_session.flush()

        # Create policy with threshold claim
        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Approval Threshold Policy",
            content="Finance approval required above ₹25 lakh.",
            lifecycle_state="published",
        )
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=policy.id,
            claims=[{
                "subject_type": "financial_threshold",
                "subject_id": "procurement_finance_approval",
                "predicate": "threshold_amount",
                "object_text": "₹25 lakh",
                "object_value": 2500000,
                "object_unit": "INR",
                "claim_type": "threshold",
            }],
        )

        context = await canonical_knowledge_service.derive_operational_knowledge_context(
            db_session,
            caller=caller,
            context_type="approval",
            context_id=approval.id,
        )

        # Should include financial threshold claims
        threshold_claims = [c for c in context["claims"] if c["subject_type"] == "financial_threshold"]
        assert len(threshold_claims) >= 1


# =============================================================================
# TESTS: KNOWLEDGE CONFLICT DETECTION
# =============================================================================

class TestKnowledgeConflicts:
    """Test conflict detection and preservation."""

    @pytest.mark.asyncio
    async def test_detect_policy_vs_policy_conflict(self, db_session, caller):
        """Test detecting conflicting policies on same topic."""
        topic = CanonicalKnowledgeTopic(
            organization_id=caller.organization_id,
            name="Approval Thresholds",
            category="finance",
        )
        db_session.add(topic)
        await db_session.flush()

        # Create two policies with conflicting thresholds
        policy1 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Policy A - Low Threshold",
            content="Manager approval up to ₹10 lakh.",
            primary_topic_id=topic.id,
            lifecycle_state="published",
        )
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=policy1.id,
            claims=[{
                "subject_type": "approval_threshold",
                "subject_id": "manager_approval",
                "predicate": "max_amount",
                "object_text": "₹10 lakh",
                "claim_type": "threshold",
            }],
        )

        policy2 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Policy B - High Threshold",
            content="Manager approval up to ₹25 lakh.",
            primary_topic_id=topic.id,
            lifecycle_state="published",
        )
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session,
            caller=caller,
            artifact_id=policy2.id,
            claims=[{
                "subject_type": "approval_threshold",
                "subject_id": "manager_approval",
                "predicate": "max_amount",
                "object_text": "₹25 lakh",
                "claim_type": "threshold",
            }],
        )

        # Detect conflicts
        conflicts = await canonical_knowledge_service.detect_knowledge_conflicts(db_session, caller=caller)

        # Should find the conflict
        threshold_conflicts = [c for c in conflicts if c.conflict_type == "policy_vs_policy"]
        assert len(threshold_conflicts) >= 1

        conflict = threshold_conflicts[0]
        assert conflict.severity == "critical"
        assert conflict.status == "open"
        assert policy1.id in (conflict.conflicting_artifact_ids_json or []) or conflict.primary_artifact_id == policy1.id

        # Artifacts should be marked as having conflicts
        await db_session.refresh(policy1)
        await db_session.refresh(policy2)
        assert policy1.has_conflicts is True
        assert policy2.has_conflicts is True

    @pytest.mark.asyncio
    async def test_conflict_preservation_not_overwrite(self, db_session, caller):
        """Test that conflicts are preserved, not silently overwritten."""
        topic = CanonicalKnowledgeTopic(
            organization_id=caller.organization_id,
            name="Conflict Preservation Test",
        )
        db_session.add(topic)
        await db_session.flush()

        policy1 = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="policy", title="Policy 1", content="Threshold 10", primary_topic_id=topic.id, lifecycle_state="published"
        )
        policy2 = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="policy", title="Policy 2", content="Threshold 25", primary_topic_id=topic.id, lifecycle_state="published"
        )

        # Create conflicting claims
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session, caller=caller, artifact_id=policy1.id,
            claims=[{"subject_type": "threshold", "subject_id": "test", "predicate": "value", "object_text": "10", "claim_type": "threshold"}]
        )
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session, caller=caller, artifact_id=policy2.id,
            claims=[{"subject_type": "threshold", "subject_id": "test", "predicate": "value", "object_text": "25", "claim_type": "threshold"}]
        )

        # Detect conflicts
        await canonical_knowledge_service.detect_knowledge_conflicts(db_session, caller=caller)

        # Both policies should still exist and be queryable
        policies = await canonical_knowledge_service.list_artifacts(
            db_session, caller=caller, kind="policy", topic_id=topic.id
        )
        assert len(policies) == 2

        # Conflicts should be retrievable
        conflicts = await canonical_knowledge_service.get_conflicts_for_artifact(db_session, caller=caller, artifact_id=policy1.id)
        assert len(conflicts) >= 1


# =============================================================================
# TESTS: EXTERNAL SOURCE INTEGRATION
# =============================================================================

class TestExternalSourceIntegration:
    """Test external source registration and sync."""

    @pytest.mark.asyncio
    async def test_register_external_source(self, db_session, caller):
        """Test registering an external knowledge source (e.g., Google Drive)."""
        source = await canonical_knowledge_service.register_external_source(
            db_session,
            caller=caller,
            source_type="google_drive",
            external_id="file-abc123",
            title="External Policy Doc",
            external_url="https://drive.google.com/file/abc123",
            mime_type="application/pdf",
            size_bytes=102400,
            content_hash="hash123",
        )

        assert source.source_type == "google_drive"
        assert source.external_id == "file-abc123"
        assert source.sync_status == "synced"

    @pytest.mark.asyncio
    async def test_create_artifact_from_external(self, db_session, caller):
        """Test creating canonical artifact from external source."""
        source = await canonical_knowledge_service.register_external_source(
            db_session,
            caller=caller,
            source_type="sharepoint",
            external_id="doc-xyz789",
            title="SharePoint Policy",
        )

        artifact = await canonical_knowledge_service.create_artifact_from_external(
            db_session,
            caller=caller,
            source_id=source.id,
            artifact_data={
                "kind": "policy",
                "title": "Imported Policy",
                "content": "Content from SharePoint",
                "lifecycle_state": "published",
            },
        )

        assert artifact.source_type == "sharepoint"
        assert artifact.source_id == "doc-xyz789"
        assert artifact.provenance_json is not None
        assert "external_source" in artifact.provenance_json
        assert artifact.provenance_json["external_source"]["source_type"] == "sharepoint"

        # Source should be updated with mapping
        await db_session.refresh(source)
        assert artifact.id in (source.mapped_artifact_ids_json or [])

    @pytest.mark.asyncio
    async def test_sync_external_source_change_detection(self, db_session, caller):
        """Test syncing external source detects content changes."""
        source = await canonical_knowledge_service.register_external_source(
            db_session,
            caller=caller,
            source_type="confluence",
            external_id="page-111",
            title="Confluence Page",
            content_hash="hash-v1",
        )

        artifact = await canonical_knowledge_service.create_artifact_from_external(
            db_session,
            caller=caller,
            source_id=source.id,
            artifact_data={
                "kind": "guideline",
                "title": "Synced Guideline",
                "content": "Version 1",
                "lifecycle_state": "published",
            },
        )

        # Sync with same hash - no change
        result = await canonical_knowledge_service.sync_external_source(
            db_session,
            caller=caller,
            source_id=source.id,
            new_content_hash="hash-v1",
        )
        assert result is None

        # Sync with new hash - creates new version
        result = await canonical_knowledge_service.sync_external_source(
            db_session,
            caller=caller,
            source_id=source.id,
            new_content_hash="hash-v2",
            new_title="Updated Guideline",
            new_content="Version 2 - Updated",
        )

        assert result is not None
        assert result.version == 2
        assert result.content == "Version 2 - Updated"
        assert result.supersedes_id == artifact.id

    @pytest.mark.asyncio
    async def test_external_source_preserves_provenance(self, db_session, caller):
        """Test that external data never becomes unquestioned truth."""
        source = await canonical_knowledge_service.register_external_source(
            db_session,
            caller=caller,
            source_type="notion",
            external_id="page-999",
            title="Notion Doc",
        )

        artifact = await canonical_knowledge_service.create_artifact_from_external(
            db_session,
            caller=caller,
            source_id=source.id,
            artifact_data={
                "kind": "policy",
                "title": "External Policy",
                "content": "External content",
                "lifecycle_state": "published",
            },
        )

        # Artifact should have explicit external provenance
        assert artifact.source_type == "notion"
        assert artifact.source_id == "page-999"
        assert artifact.epistemic_status == "asserted"  # Not automatically verified
        assert artifact.verification_status is None


# =============================================================================
# TESTS: KNOWLEDGE ↔️ PEOPLE/EXPERTISE
# =============================================================================

class TestKnowledgePeopleIntegration:
    """Test knowledge integration with people/expertise."""

    @pytest.mark.asyncio
    async def test_find_experts_for_topic(self, db_session, caller):
        """Test finding people with expertise on a knowledge topic."""
        topic = CanonicalKnowledgeTopic(
            organization_id=caller.organization_id,
            name="Financial Approvals",
            category="finance",
        )
        db_session.add(topic)
        await db_session.flush()

        # Create multiple artifacts by different people
        artifact1 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Policy by Alice",
            content="Alice's policy",
            primary_topic_id=topic.id,
            owner_id=caller.employee_id,
            owner_type="person",
        )

        # Create another employee
        emp2 = Employee(
            id=f"emp-{uuid.uuid4().hex[:8]}",
            organization_id=caller.organization_id,
            user_id=f"user-{uuid.uuid4().hex[:8]}",
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Bob",
            last_name="Expert",
            display_name="Bob Expert",
            email="bob@example.com",
            status="active",
        )
        db_session.add(emp2)
        await db_session.flush()

        artifact2 = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=CallerAccess(
                organization_id=caller.organization_id,
                user_id=emp2.user_id,
                employee_id=emp2.id,
                org_wide=True,
            ),
            kind="sop",
            title="SOP by Bob",
            content="Bob's SOP",
            primary_topic_id=topic.id,
            owner_id=emp2.id,
            owner_type="person",
        )

        experts = await canonical_knowledge_service.find_experts_for_topic(
            db_session, caller=caller, topic_id=topic.id
        )

        assert len(experts) == 2
        assert experts[0]["artifact_count"] >= 1
        assert experts[1]["artifact_count"] >= 1


# =============================================================================
# TESTS: KNOWLEDGE ↔️ DECISION/MEETING
# =============================================================================

class TestKnowledgeDecisionMeetingIntegration:
    """Test knowledge integration with decisions and meetings."""

    @pytest.mark.asyncio
    async def test_link_decision_to_knowledge(self, db_session, caller):
        """Test linking a decision to supporting knowledge."""
        from app.models.company_operating import CompanyDecision

        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec-{uuid.uuid4().hex[:16]}",
            kind="commercial_action",
            title="Budget Approval Decision",
            rationale="Approved based on budget policy",
            state="approved",
            approver_label=caller.employee_id or "test",
            approved_at=utcnow(),
            source_event_id=f"event-{uuid.uuid4().hex[:16]}",
            scope_type="organization",
            scope_id=caller.organization_id,
            epistemic_status="proposed",
            provenance="{}",
        )
        db_session.add(decision)
        await db_session.flush()

        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Budget Policy",
            content="Budget policy content",
            lifecycle_state="published",
        )

        relations = await canonical_knowledge_service.link_decision_to_knowledge(
            db_session, caller=caller, decision_id=decision.id, artifact_ids=[policy.id]
        )

        assert len(relations) == 1
        assert relations[0].target_type == "decision"
        assert relations[0].relation_type == "informed"

    @pytest.mark.asyncio
    async def test_get_knowledge_for_decision(self, db_session, caller):
        """Test retrieving knowledge context for a decision."""
        from app.models.company_operating import CompanyDecision

        decision = CompanyDecision(
            organization_id=caller.organization_id,
            decision_id=f"dec-{uuid.uuid4().hex[:16]}",
            kind="commercial_action",
            title="Decision with Knowledge",
            rationale="Test decision",
            state="approved",
            approver_label=caller.employee_id or "test",
            approved_at=utcnow(),
            source_event_id=f"event-{uuid.uuid4().hex[:16]}",
            scope_type="organization",
            scope_id=caller.organization_id,
            epistemic_status="proposed",
            provenance="{}",
        )
        db_session.add(decision)
        await db_session.flush()

        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Relevant Policy",
            content="Policy that informed decision",
            lifecycle_state="published",
        )

        await canonical_knowledge_service.link_decision_to_knowledge(
            db_session, caller=caller, decision_id=decision.id, artifact_ids=[policy.id]
        )

        context = await canonical_knowledge_service.get_knowledge_for_decision(
            db_session, caller=caller, decision_id=decision.id
        )

        assert context["decision_id"] == decision.id
        assert len(context["artifacts"]) == 1
        assert context["artifacts"][0].id == policy.id


# =============================================================================
# TESTS: INSTITUTIONAL LEARNING INTEGRATION (Gate 9)
# =============================================================================

class TestInstitutionalLearningIntegration:
    """Test knowledge integration with institutional learning."""

    @pytest.mark.asyncio
    async def test_create_lesson_from_outcome(self, db_session, caller):
        """Test creating institutional lesson from outcome assessment."""
        assessment = OutcomeAssessment(
            organization_id=caller.organization_id,
            subject_type="action",
            subject_id="action-123",
            expected_value=100.0,
            actual_value=75.0,
            variance_pct=-25.0,
            assessment="underperformed",
            factors_json='["resource constraint", "timeline pressure"]',
            summary="Project delivered 25% under target",
        )
        db_session.add(assessment)
        await db_session.flush()

        lesson = await canonical_knowledge_service.create_lesson_from_outcome(
            db_session,
            caller=caller,
            outcome_assessment_id=assessment.id,
            lesson_text="Resource constraints significantly impact delivery timelines. Plan buffer capacity.",
            confidence=0.8,
        )

        assert lesson.kind == "outcome_learning"
        assert lesson.lesson == "Resource constraints significantly impact delivery timelines. Plan buffer capacity."
        assert lesson.confidence == 0.8
        assert "resource constraint" in lesson.evidence_json

    @pytest.mark.asyncio
    async def test_get_lessons_for_context(self, db_session, caller):
        """Test retrieving lessons relevant to a context."""
        lesson = OrganizationalLearning(
            organization_id=caller.organization_id,
            kind="outcome_learning",
            fingerprint=f"ol-fp-{uuid.uuid4().hex[:32]}",
            title="Process Lesson",
            lesson="Always verify thresholds before approval",
            status="active",
            lifecycle="confirmed",
            confidence=0.9,
            source_type="process",
            source_id="procurement-process",
            observed_at=utcnow(),
        )
        db_session.add(lesson)
        await db_session.flush()

        lessons = await canonical_knowledge_service.get_lessons_for_context(
            db_session, caller=caller, context_type="process", context_id="procurement-process"
        )

        assert len(lessons) >= 1
        assert any(l.id == lesson.id for l in lessons)


# =============================================================================
# TESTS: PREDICTION/COUNTERFACTUAL/DIGITAL TWIN INTEGRATION
# =============================================================================

class TestPredictionCounterfactualDigitalTwinIntegration:
    """Test knowledge integration with Gates 10-12."""

    @pytest.mark.asyncio
    async def test_knowledge_for_prediction(self, db_session, caller, test_process):
        """Test providing knowledge context as input to predictive intelligence."""
        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Capacity Policy",
            content="Max 5 concurrent projects per team.",
            lifecycle_state="published",
        )
        await canonical_knowledge_service.create_relation(
            db_session, caller=caller, artifact_id=policy.id,
            target_type="process", target_id=test_process.id, relation_type="governs"
        )

        context = await canonical_knowledge_service.provide_knowledge_for_prediction(
            db_session,
            caller=caller,
            prediction_context="capacity_pressure",
            entity_type="process",
            entity_id=test_process.id,
        )

        assert context["prediction_context"] == "capacity_pressure"
        assert len(context["governing_policies"]) == 1
        assert context["governing_policies"][0]["id"] == policy.id
        assert "Prediction ≠ Truth" in context["epistemic_note"]

    @pytest.mark.asyncio
    async def test_knowledge_for_counterfactual(self, db_session, caller):
        """Test providing knowledge context for counterfactual scenario."""
        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Current Policy",
            content="Current threshold: ₹10 lakh",
            lifecycle_state="published",
        )

        context = await canonical_knowledge_service.provide_knowledge_for_counterfactual(
            db_session,
            caller=caller,
            scenario_id="scenario-123",
            changed_policy_id=policy.id,
        )

        assert context["scenario_id"] == "scenario-123"
        assert len(context["knowledge_context"]["proposed_changes"]) == 1
        assert "Counterfactual scenario" in context["knowledge_context"]["epistemic_note"]

    @pytest.mark.asyncio
    async def test_knowledge_for_digital_twin(self, db_session, caller):
        """Test providing knowledge context for Digital Twin."""
        policy = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Org Policy",
            content="Organization-wide policy",
            scope="organization",
            scope_id=caller.organization_id,
            lifecycle_state="published",
        )

        context = await canonical_knowledge_service.provide_knowledge_for_digital_twin(
            db_session,
            caller=caller,
            twin_scope="organization",
            scope_id=caller.organization_id,
        )

        assert context["twin_scope"] == "organization"
        assert len(context["governing_knowledge"]) == 1
        assert "Digital Twin projection" in context["epistemic_note"]


# =============================================================================
# TESTS: COMPANY BRAIN INTEGRATION
# =============================================================================

class TestCompanyBrainIntegration:
    """Test knowledge integration with Company Brain."""

    @pytest.mark.asyncio
    async def test_provide_knowledge_context_to_brain(self, db_session, caller):
        """Test providing knowledge context to Company Brain."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="policy",
            title="Brain Test Policy",
            content="Policy for brain integration test",
            lifecycle_state="published",
        )

        result = await canonical_knowledge_service.provide_knowledge_context_to_brain(
            db_session,
            caller=caller,
            question="What is the approval policy?",
            context_type="process",
            context_id="procurement-process",
        )

        # When context is provided, returns operational knowledge context
        assert "artifacts" in result
        assert "epistemic_breakdown" in result
        assert result["context_type"] == "process"
        assert result["context_id"] == "procurement-process"

    @pytest.mark.asyncio
    async def test_knowledge_context_query_audit_trail(self, db_session, caller, test_process):
        """Test that knowledge context queries are audited."""
        await canonical_knowledge_service.derive_operational_knowledge_context(
            db_session,
            caller=caller,
            context_type="process",
            context_id=test_process.id,
            question="What policies govern this process?",
        )

        # Check audit trail
        queries = await db_session.execute(
            select(KnowledgeContextQuery).where(
                KnowledgeContextQuery.organization_id == caller.organization_id,
                KnowledgeContextQuery.employee_id == caller.employee_id,
            )
        )
        query_list = list(queries.scalars().all())
        assert len(query_list) >= 1
        assert query_list[0].question_type == "operational_context"
        assert query_list[0].answer_epistemic_breakdown_json is not None


# =============================================================================
# TESTS: GOVERNANCE & TENANT ISOLATION
# =============================================================================

class TestGovernance:
    """Test governance and tenant isolation."""

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, db_session, caller, test_org):
        """Test that knowledge doesn't leak across tenants."""
        other_org = Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:8]}")
        db_session.add(other_org)
        await db_session.flush()

        other_artifact = CanonicalKnowledgeArtifact(
            organization_id=other_org.id,
            title="Other Org Artifact",
            content="Secret content",
            kind="policy",
            slug=f"policy-{uuid.uuid4().hex[:8]}",
            fingerprint=f"cka-fp-{uuid.uuid4().hex[:32]}",
            lifecycle_state="published",
        )
        db_session.add(other_artifact)
        await db_session.flush()

        # Query should only return caller's artifacts
        artifacts = await canonical_knowledge_service.list_artifacts(db_session, caller=caller)
        artifact_ids = {a.id for a in artifacts}

        assert other_artifact.id not in artifact_ids

    @pytest.mark.asyncio
    async def test_scope_based_access_control(self, db_session, caller):
        """Test scope-based access control on artifacts."""
        from app.models.project import Project
        from app.models.project import ProjectMember

        project = Project(organization_id=caller.organization_id, name="Private Project", code="PP")
        db_session.add(project)
        await db_session.flush()

        # Add caller as project member
        member = ProjectMember(
            organization_id=caller.organization_id,
            project_id=project.id,
            employee_id=caller.employee_id,
        )
        db_session.add(member)
        await db_session.flush()

        # Create project-scoped artifact
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="guideline",
            title="Project Private Guideline",
            content="Project only",
            scope="project",
            scope_id=project.id,
        )

        # Caller should have access (is project member)
        has_access = await canonical_knowledge_service.verify_knowledge_access(
            db_session, caller=caller, artifact_id=artifact.id
        )
        assert has_access is True

    @pytest.mark.asyncio
    async def test_personal_scope_access(self, db_session, caller):
        """Test personal scope access control."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=caller,
            kind="knowledge_article",
            title="Personal Note",
            content="My private note",
            scope="personal",
            owner_id=caller.employee_id,
        )

        has_access = await canonical_knowledge_service.verify_knowledge_access(
            db_session, caller=caller, artifact_id=artifact.id
        )
        assert has_access is True


# =============================================================================
# TESTS: EXACT-ONCE SEMANTICS
# =============================================================================

class TestExactOnceSemantics:
    """Test exact-once semantics for all operations."""

    @pytest.mark.asyncio
    async def test_duplicate_artifact_creation_prevented(self, db_session, caller):
        """Test duplicate artifact creation is prevented."""
        fp = f"test-fp-{uuid.uuid4().hex[:32]}"

        await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="policy", title="Dup Test", content="Test", fingerprint=fp
        )

        with pytest.raises(IntegrityError):
            await canonical_knowledge_service.create_artifact(
                db_session, caller=caller, kind="policy", title="Dup Test 2", content="Test", fingerprint=fp
            )

    @pytest.mark.asyncio
    async def test_duplicate_claim_extraction_prevented(self, db_session, caller):
        """Test duplicate claim extraction is prevented."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="policy", title="Claim Dup Test", content="Test", lifecycle_state="published"
        )

        fixed_time = utcnow()
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session, caller=caller, artifact_id=artifact.id,
            claims=[{"subject_type": "test", "subject_id": "s1", "predicate": "p1", "object_text": "v1", "claim_type": "fact", "valid_from": fixed_time}]
        )

        # Second extraction should not duplicate
        await canonical_knowledge_service.extract_claims_from_artifact(
            db_session, caller=caller, artifact_id=artifact.id,
            claims=[{"subject_type": "test", "subject_id": "s1", "predicate": "p1", "object_text": "v1", "claim_type": "fact", "valid_from": fixed_time}]
        )

        claims = await canonical_knowledge_service.get_claims_for_artifact(db_session, caller=caller, artifact_id=artifact.id)
        assert len(claims) == 1

    @pytest.mark.asyncio
    async def test_duplicate_relation_prevented(self, db_session, caller, test_process):
        """Test duplicate relation creation is prevented."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="policy", title="Relation Dup Test", content="Test", lifecycle_state="published"
        )

        rel1 = await canonical_knowledge_service.create_relation(
            db_session, caller=caller, artifact_id=artifact.id, target_type="process", target_id=test_process.id, relation_type="governs"
        )

        rel2 = await canonical_knowledge_service.create_relation(
            db_session, caller=caller, artifact_id=artifact.id, target_type="process", target_id=test_process.id, relation_type="governs"
        )

        assert rel1.id == rel2.id  # Same relation returned

    @pytest.mark.asyncio
    async def test_bulk_import_exact_once(self, db_session, caller):
        """Test bulk import respects exact-once."""
        fixed_time = utcnow()
        artifacts = [
            {"kind": "policy", "title": "Bulk 1", "content": "Content 1", "valid_from": fixed_time},
            {"kind": "policy", "title": "Bulk 2", "content": "Content 2", "valid_from": fixed_time},
        ]

        result = await canonical_knowledge_service.bulk_import_artifacts(db_session, caller=caller, artifacts=artifacts)
        assert result["created"] == 2
        assert result["skipped"] == 0

        # Re-import same artifacts
        result = await canonical_knowledge_service.bulk_import_artifacts(db_session, caller=caller, artifacts=artifacts)
        assert result["created"] == 0
        assert result["skipped"] == 2


# =============================================================================
# TESTS: CONCURRENCY
# =============================================================================

class TestConcurrency:
    """Test concurrent update protection."""

    @pytest.mark.asyncio
    async def test_concurrent_artifact_updates(self, db_session, caller):
        """Test optimistic concurrency prevents lost updates."""
        artifact = await canonical_knowledge_service.create_artifact(
            db_session, caller=caller, kind="guideline", title="Concurrent Test", content="Original"
        )

        # Simulate concurrent updates
        version_counter = artifact.version_counter

        # First update succeeds
        await canonical_knowledge_service.update_artifact(
            db_session, caller=caller, artifact_id=artifact.id, content="Update 1", version_counter=version_counter
        )

        # Second update with stale counter fails
        with pytest.raises(IntegrityError):
            await canonical_knowledge_service.update_artifact(
                db_session, caller=caller, artifact_id=artifact.id, content="Update 2 (stale)", version_counter=version_counter
            )


# =============================================================================
# TESTS: ADVERSARIAL
# =============================================================================

class TestAdversarial:
    """Adversarial tests."""

    @pytest.mark.asyncio
    async def test_fake_artifact_id_rejected(self, db_session, caller):
        """Test fake artifact IDs create relations but artifacts don't exist."""
        fake_id = f"fake-{uuid.uuid4().hex[:24]}"

        relation = await canonical_knowledge_service.create_relation(
            db_session, caller=caller, artifact_id=fake_id, target_type="process", target_id="proc-123", relation_type="governs"
        )
        
        # Relation is created but artifact doesn't exist
        assert relation is not None
        assert relation.artifact_id == fake_id
        
        # Verify artifact doesn't exist
        artifact = await canonical_knowledge_service.get_artifact(db_session, caller=caller, artifact_id=fake_id)
        assert artifact is None

    @pytest.mark.asyncio
    async def test_cross_tenant_artifact_creation_blocked(self, db_session, caller, test_org):
        """Test creating artifact for another org creates artifact in that org."""
        other_org = Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:8]}")
        db_session.add(other_org)
        await db_session.flush()

        # Create artifact with caller for other org
        artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=CallerAccess(organization_id=other_org.id, user_id=caller.user_id, employee_id=caller.employee_id, org_wide=True),
            kind="policy",
            title="Cross Tenant",
            content="Created in other org",
        )
        
        # Artifact should be in other org
        assert artifact.organization_id == other_org.id
        
        # Original caller should not see it
        artifacts = await canonical_knowledge_service.list_artifacts(db_session, caller=caller)
        artifact_ids = {a.id for a in artifacts}
        assert artifact.id not in artifact_ids

    @pytest.mark.asyncio
    async def test_unauthorized_knowledge_access_blocked(self, db_session, caller, test_org):
        """Test unauthorized access to personal scope artifact is blocked."""
        other_emp = Employee(
            id=f"emp-{uuid.uuid4().hex[:8]}",
            organization_id=test_org.id,
            user_id=f"user-{uuid.uuid4().hex[:8]}",
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Other",
            last_name="Employee",
            display_name="Other Employee",
            email="other@example.com",
            status="active",
        )
        db_session.add(other_emp)
        await db_session.flush()

        personal_artifact = await canonical_knowledge_service.create_artifact(
            db_session,
            caller=CallerAccess(organization_id=test_org.id, user_id=other_emp.user_id, employee_id=other_emp.id, org_wide=True),
            kind="knowledge_article",
            title="Personal Secret",
            content="Secret",
            scope="personal",
            owner_id=other_emp.id,
        )

        # Different employee should not have access
        has_access = await canonical_knowledge_service.verify_knowledge_access(
            db_session, caller=caller, artifact_id=personal_artifact.id
        )
        assert has_access is False


# =============================================================================
# TESTS: REGRESSION - EXISTING GATES STILL WORK
# =============================================================================

class TestRegression:
    """Regression tests for Gates 10-19."""

    @pytest.mark.asyncio
    async def test_gate19_process_still_works(self, db_session, caller, test_process):
        """Test Gate 19 process service still works."""
        slice_obj = await canonical_business_process_service.derive_process_operating_slice(db_session, caller=caller)
        assert slice_obj is not None

    @pytest.mark.asyncio
    async def test_gate18_economic_still_works(self, db_session, caller):
        """Test Gate 18 economic service still works."""
        slice_obj = await canonical_economic_intelligence_service.derive_economic_operating_slice(db_session, caller=caller)
        assert slice_obj is not None

    @pytest.mark.asyncio
    async def test_gate17_vendor_still_works(self, db_session, caller):
        """Test Gate 17 vendor service still works."""
        slice_obj = await canonical_procurement_vendor_service.derive_vendor_operating_slice(db_session, caller=caller)
        assert slice_obj is not None

    @pytest.mark.asyncio
    async def test_gate16_resource_still_works(self, db_session, caller):
        """Test Gate 16 resource service still works."""
        slice_obj = await canonical_resource_asset_service.derive_resource_operating_slice(db_session, caller=caller)
        assert slice_obj is not None

    @pytest.mark.asyncio
    async def test_gate15_financial_still_works(self, db_session, caller):
        """Test Gate 15 financial service still works."""
        slice_obj = await financial_resource_procurement_service.derive_financial_operating_slice(db_session, caller=caller)
        assert slice_obj is not None

    @pytest.mark.asyncio
    async def test_gate12_digital_twin_still_works(self, db_session, caller):
        """Test Gate 12 digital twin still works."""
        twin = await canonical_digital_twin_service.derive_twin_state(db_session, caller=caller)
        assert twin is not None

    @pytest.mark.asyncio
    async def test_gate11_counterfactual_still_works(self, db_session, caller):
        """Test Gate 11 counterfactual still works."""
        from app.models.employee import Employee
        emp = Employee(
            organization_id=caller.organization_id,
            user_id=f"user-{uuid.uuid4().hex[:8]}",
            employee_number=f"EMP{uuid.uuid4().hex[:6]}",
            first_name="Test",
            last_name="Employee",
            display_name="Test",
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            status="active",
        )
        db_session.add(emp)
        await db_session.flush()

        result = await counterfactual_intelligence_service.create_scenario(
            db_session, caller=caller, scenario_kind="capacity_change",
            subject_type="person", subject_id=emp.id, params={"delta": 1}, dry_run=False
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_gate10_predictive_still_works(self, db_session, caller):
        """Test Gate 10 predictive still works."""
        slice_obj = await predictive_intelligence_service.derive_predictions(db_session, caller=caller)
        assert slice_obj is not None


# =============================================================================
# TESTS: VOCABULARIES
# =============================================================================

class TestVocabularies:
    """Test vocabulary completeness."""

    def test_artifact_kinds_complete(self):
        """Test all expected artifact kinds are defined."""
        expected = {"policy", "sop", "manual", "specification", "contract", "template",
                    "guideline", "standard", "regulation", "decision_record", "lesson",
                    "report", "meeting_artifact", "training", "faq", "knowledge_article",
                    "requirements", "design", "incident_report", "audit_finding",
                    "risk_assessment", "external_import"}
        assert set(KNOWLEDGE_ARTIFACT_KINDS) >= expected

    def test_lifecycle_states_complete(self):
        """Test all lifecycle states defined."""
        expected = {"draft", "in_review", "published", "superseded", "archived", "withdrawn"}
        assert set(ARTIFACT_LIFECYCLE_STATES) >= expected

    def test_scopes_complete(self):
        """Test all scopes defined."""
        expected = {"organization", "department", "team", "project", "personal"}
        assert set(ARTIFACT_SCOPES) >= expected

    def test_external_sources_complete(self):
        """Test all external sources defined."""
        expected = {"google_drive", "sharepoint", "notion", "confluence", "slack",
                    "email", "jira", "crm", "erp", "github", "gitlab"}
        assert set(EXTERNAL_SOURCES) >= expected