"""Canonical People, Talent & Workforce Operating Fabric Service — Gate 21.

Derives the canonical person operating context by composing Gates 6-20 into a
single coherent workforce fabric. This is a DERIVED PROJECTION layer — it does
NOT create a parallel HR/Talent/People graph/brain/system.

All data is composed from existing canonical primitives:
- Gates 6-9: Temporal truth, provenance, verification, institutional learning
- Gates 8-14: People, Work, Communication, Meetings, Org Intelligence, Capacity, Customer
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric
- Gate 17: Procurement + Vendor + External Capacity Operating Fabric
- Gate 18: Economic Intelligence
- Gate 19: Enterprise Operations & Business Process Fabric
- Gate 20: Canonical Knowledge, Documents & Institutional Context Fabric

Epistemic boundaries preserved:
Identity ≠ Employment ≠ Role ≠ Responsibility ≠ Authorization ≠ Accountability
Skill ≠ Expertise ≠ Capability ≠ Capability Aggregate
Development ≠ Course Completion ≠ Capability Change
Performance ≠ AI Score ≠ Outcome Evidence ≠ Verification
Offboarding must propagate impact through canonical reality
"""

import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.canonical_business_process_service import canonical_business_process_service
from app.intelligence.canonical_economic_intelligence_service import canonical_economic_intelligence_service
from app.intelligence.canonical_knowledge_service import canonical_knowledge_service
from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
from app.intelligence.company_brain import company_brain
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
    CanonicalKnowledgeClaim,
    CanonicalKnowledgeRelation,
    CanonicalKnowledgeTopic,
)
from app.models.canonical_procurement_vendor import CanonicalVendor
from app.models.canonical_resource_asset import CanonicalResource
from app.models.canonical_workforce import (
    PersonWorkforceExtension,
    WorkforceCapabilityGap,
    WorkforceContinuityEvent,
    WorkforceDevelopmentNeed,
    WORKFORCE_LIFECYCLE_STATES,
    EMPLOYMENT_TYPES,
    MEMBERSHIP_STATUSES,
    RELATIONSHIP_TYPES,
    ROLE_TYPES,
    RESPONSIBILITY_TYPES,
    RESPONSIBILITY_SCOPES,
    ACCOUNTABILITY_TYPES,
    WORKLOAD_STATES,
    SUCCESSION_STATUSES,
    DEVELOPMENT_STATES,
    PERFORMANCE_KINDS,
)
from app.models.company_actions import CompanyAction
from app.models.company_memory import CompanyMemory
from app.models.department import Department
from app.models.employee import (
    Employee,
    EmployeeAvailability,
    EmployeePresence,
    EmployeeSkill,
    EmployeeCertification,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    OrganizationalResponsibility,
    AccountabilityLink,
)
from app.models.finance import Budget
from app.models.knowledge import KnowledgeSource
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
    OutcomeAssessment,
)
from app.models.people_intelligence import (
    PersonIdentity,
    PersonMembership,
    PersonRoleAssignment,
    ReportingRelationship,
    PeopleTimeline,
    MEMBERSHIP_STATUSES,
    RELATIONSHIP_TYPES,
    ROLE_TYPES,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.role import Role
from app.models.skills_intelligence import (
    CanonicalSkill,
    Expertise,
    ExpertiseEvidence,
    CapabilityAggregate,
)
from app.models.team import Team
from app.models.workload import WorkloadSnapshot
from app.models.organization import TimestampMixin, gen_uuid
from app.intelligence.company_context import CallerAccess

logger = logging.getLogger("vcos.intelligence.canonical_workforce")


# =============================================================================
# UTILITIES
# =============================================================================

def _compute_fingerprint(data: dict) -> str:
    """Compute deterministic fingerprint for exact-once semantics."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:160]


# =============================================================================
# SERVICE CLASS
# =============================================================================

class CanonicalWorkforceService:
    """Canonical Workforce Service — Gate 21."""

    # -------------------------------------------------------------------------
    # 1. PERSON WORKFORCE EXTENSION CRUD
    # -------------------------------------------------------------------------

    async def create_workforce_extension(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: str,
        workforce_status: str = "active",
        employment_type: str = "full_time",
        hire_date: Optional[date] = None,
        probation_end_date: Optional[date] = None,
        compensation_band_id: Optional[str] = None,
        cost_center_id: Optional[str] = None,
        work_schedule_id: Optional[str] = None,
        security_clearance: Optional[str] = None,
        compliance_profile: Optional[dict] = None,
        fingerprint: Optional[str] = None,
    ) -> PersonWorkforceExtension:
        """Create a person workforce extension with exact-once semantics."""

        if workforce_status not in WORKFORCE_LIFECYCLE_STATES:
            raise ValueError(f"Invalid workforce_status: {workforce_status}")
        if employment_type not in EMPLOYMENT_TYPES:
            raise ValueError(f"Invalid employment_type: {employment_type}")

        # Verify employee exists and belongs to caller's org
        employee = await db.get(Employee, employee_id)
        if not employee or employee.organization_id != caller.organization_id:
            raise ValueError("Employee not found")

        # Check for existing extension
        existing = await db.execute(
            select(PersonWorkforceExtension).where(
                PersonWorkforceExtension.organization_id == caller.organization_id,
                PersonWorkforceExtension.employee_id == employee_id,
            )
        )
        if existing.scalar_one_or_none():
            raise IntegrityError("Workforce extension already exists for employee", None, None)

        fp = fingerprint or _compute_fingerprint({
            "org": caller.organization_id,
            "emp": employee_id,
            "status": workforce_status,
            "type": employment_type,
            "hire": hire_date.isoformat() if hire_date else None,
        })

        existing_fp = await db.execute(
            select(PersonWorkforceExtension).where(
                PersonWorkforceExtension.organization_id == caller.organization_id,
                PersonWorkforceExtension.fingerprint == fp,
            )
        )
        if existing_fp.scalar_one_or_none():
            raise IntegrityError("Duplicate workforce extension fingerprint", None, None)

        extension = PersonWorkforceExtension(
            organization_id=caller.organization_id,
            employee_id=employee_id,
            workforce_status=workforce_status,
            employment_type=employment_type,
            hire_date=hire_date,
            probation_end_date=probation_end_date,
            compensation_band_id=compensation_band_id,
            cost_center_id=cost_center_id,
            work_schedule_id=work_schedule_id,
            security_clearance=security_clearance,
            compliance_profile_json=compliance_profile or {},
            source_event_id=f"ext-create-{uuid.uuid4().hex[:16]}",
            created_by=caller.employee_id or caller.user_id,
            fingerprint=fp,
        )

        db.add(extension)
        await db.flush()
        return extension

    async def update_workforce_extension(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: str,
        workforce_status: Optional[str] = None,
        employment_type: Optional[str] = None,
        notice_date: Optional[date] = None,
        departure_date: Optional[date] = None,
        alumni_since_date: Optional[date] = None,
        compliance_profile: Optional[dict] = None,
    ) -> Optional[PersonWorkforceExtension]:
        """Update workforce extension."""

        extension = await db.execute(
            select(PersonWorkforceExtension).where(
                PersonWorkforceExtension.organization_id == caller.organization_id,
                PersonWorkforceExtension.employee_id == employee_id,
            )
        )
        extension = extension.scalar_one_or_none()
        if not extension:
            return None

        if workforce_status is not None:
            if workforce_status not in WORKFORCE_LIFECYCLE_STATES:
                raise ValueError(f"Invalid workforce_status: {workforce_status}")
            extension.workforce_status = workforce_status
            if workforce_status == "notice":
                extension.notice_date = notice_date or date.today()
            elif workforce_status == "departed":
                extension.departure_date = departure_date or date.today()
            elif workforce_status == "alumni":
                extension.alumni_since_date = alumni_since_date or date.today()

        if employment_type is not None:
            if employment_type not in EMPLOYMENT_TYPES:
                raise ValueError(f"Invalid employment_type: {employment_type}")
            extension.employment_type = employment_type

        if compliance_profile is not None:
            extension.compliance_profile_json = compliance_profile

        extension.updated_at = utcnow()
        await db.flush()
        return extension

    async def get_workforce_extension(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        employee_id: str,
    ) -> Optional[PersonWorkforceExtension]:
        """Get workforce extension for an employee."""
        result = await db.execute(
            select(PersonWorkforceExtension).where(
                PersonWorkforceExtension.organization_id == caller.organization_id,
                PersonWorkforceExtension.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # 2. CANONICAL PERSON OPERATING CONTEXT — The core capability
    # -------------------------------------------------------------------------

    async def derive_person_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        person_id: str,
        at_time: Optional[datetime] = None,
        include_predictions: bool = True,
        include_counterfactuals: bool = False,
        include_digital_twin: bool = False,
    ) -> dict:
        """
        Derive the complete canonical operating context for a person.

        This is the CORE CAPABILITY of Gate 21: given a person, derive their
        complete organizational context from canonical reality.

        Returns a structured context with epistemic transparency.
        """

        at_time = at_time or utcnow()

        # Verify person exists and caller has access
        person = await db.get(Employee, person_id)
        if not person or person.organization_id != caller.organization_id:
            raise ValueError("Person not found")

        # Check governance access
        if not await self._verify_person_access(db, caller, person_id):
            raise ValueError("Access denied")

        context = {
            "queried_at": utcnow().isoformat(),
            "person_id": person_id,
            "at_time": at_time.isoformat(),
            "identity": await self._derive_identity_context(db, caller, person, at_time),
            "membership": await self._derive_membership_context(db, caller, person, at_time),
            "roles": await self._derive_roles_context(db, caller, person, at_time),
            "reporting": await self._derive_reporting_context(db, caller, person, at_time),
            "responsibilities": await self._derive_responsibilities_context(db, caller, person, at_time),
            "commitments": await self._derive_commitments_context(db, caller, person, at_time),
            "capability": await self._derive_capability_context(db, caller, person, at_time),
            "capacity": await self._derive_capacity_context(db, caller, person, at_time),
            "work": await self._derive_work_context(db, caller, person, at_time),
            "processes": await self._derive_process_context(db, caller, person, at_time),
            "knowledge": await self._derive_knowledge_context(db, caller, person, at_time),
            "customers": await self._derive_customer_context(db, caller, person, at_time),
            "assets": await self._derive_assets_context(db, caller, person, at_time),
            "learning": await self._derive_learning_context(db, caller, person, at_time),
            "development": await self._derive_development_context(db, caller, person, at_time),
            "continuity": await self._derive_continuity_context(db, caller, person, at_time),
            "epistemic_breakdown": {
                "identity_claims": [],       # What the system says about identity
                "membership_facts": [],      # Actual membership state
                "role_assignments": [],      # Actual role windows
                "responsibilities_owned": [], # Explicit responsibilities
                "capabilities": [],          # Evidence-derived capabilities
                "capacity_facts": [],        # Measured capacity
                "work_evidence": [],         # Observed work
                "process_participation": [], # Actual process involvement
                "knowledge_claims": [],      # Knowledge ownership
                "verified_outcomes": [],     # Verified outcomes
                "learning_evidence": [],     # Institutional learning
                "predictions": [],           # Predictive intelligence
                "uncertainties": [],         # Known unknowns
            },
        }

        # Populate epistemic breakdown
        await self._populate_epistemic_breakdown(db, caller, person, context, at_time)

        # Optional integrations
        if include_predictions:
            context["predictions"] = await self._provide_workforce_predictions(
                db, caller, person_id, at_time
            )
        if include_counterfactuals:
            context["counterfactuals"] = await self._provide_workforce_counterfactuals(
                db, caller, person_id, at_time
            )
        if include_digital_twin:
            context["digital_twin"] = await self._provide_workforce_digital_twin(
                db, caller, person_id, at_time
            )

        # Log query for audit
        await self._log_context_query(
            db, caller, person_id, context, at_time
        )

        return context

    # -------------------------------------------------------------------------
    # CONTEXT DERIVATION HELPERS
    # -------------------------------------------------------------------------

    async def _derive_identity_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive identity context from PersonIdentity and Employee."""
        identities = await db.execute(
            select(PersonIdentity).where(
                PersonIdentity.organization_id == caller.organization_id,
                PersonIdentity.person_id == person.id,
                PersonIdentity.status == "active",
            )
        )

        return {
            "employee_id": person.id,
            "user_id": person.user_id,
            "employee_number": person.employee_number,
            "full_name": person.full_name,
            "email": person.email,
            "phone": person.phone,
            "display_name": person.display_name,
            "avatar_url": person.avatar_url,
            "external_identities": [{
                "source": i.source,
                "source_key": i.source_key,
                "kind": i.kind,
                "verified": i.verified,
            } for i in identities.scalars().all()],
        }

    async def _derive_membership_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive temporal membership context from PersonMembership."""
        memberships = await db.execute(
            select(PersonMembership).where(
                PersonMembership.organization_id == caller.organization_id,
                PersonMembership.person_id == person.id,
                PersonMembership.valid_from <= at_time,
                or_(
                    PersonMembership.valid_to.is_(None),
                    PersonMembership.valid_to > at_time,
                ),
            ).order_by(PersonMembership.valid_from.desc())
        )

        membership = memberships.scalars().first()

        # Also get workforce extension
        extension = await self.get_workforce_extension(db, caller=caller, employee_id=person.id)

        return {
            "current_membership": {
                "status": membership.employment_status if membership else "unknown",
                "valid_from": membership.valid_from.isoformat() if membership else None,
                "valid_to": membership.valid_to.isoformat() if membership and membership.valid_to else None,
                "employment_type": membership.employment_type,
                "designation_snapshot": membership.designation_snapshot,
            } if membership else None,
            "workforce_extension": {
                "workforce_status": extension.workforce_status if extension else "unknown",
                "employment_type": extension.employment_type if extension else "unknown",
                "hire_date": extension.hire_date.isoformat() if extension and extension.hire_date else None,
                "probation_end_date": extension.probation_end_date.isoformat() if extension and extension.probation_end_date else None,
                "notice_date": extension.notice_date.isoformat() if extension and extension.notice_date else None,
                "departure_date": extension.departure_date.isoformat() if extension and extension.departure_date else None,
                "alumni_since_date": extension.alumni_since_date.isoformat() if extension and extension.alumni_since_date else None,
            } if extension else None,
        }

    async def _derive_roles_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive temporal role assignments from PersonRoleAssignment."""
        roles = await db.execute(
            select(PersonRoleAssignment).where(
                PersonRoleAssignment.organization_id == caller.organization_id,
                PersonRoleAssignment.person_id == person.id,
                PersonRoleAssignment.valid_from <= at_time,
                or_(
                    PersonRoleAssignment.valid_to.is_(None),
                    PersonRoleAssignment.valid_to > at_time,
                ),
            ).order_by(PersonRoleAssignment.valid_from.desc())
        )

        roles_list = []
        for ra in roles.scalars().all():
            role = await db.get(Role, ra.role_id) if ra.role_id else None
            roles_list.append({
                "assignment_id": ra.id,
                "role_id": ra.role_id,
                "role_title": ra.role_title,
                "role_type": ra.role_type,
                "is_primary": ra.is_primary,
                "valid_from": ra.valid_from.isoformat(),
                "valid_to": ra.valid_to.isoformat() if ra.valid_to else None,
                "role": {
                    "name": role.name,
                    "code": role.code,
                    "description": role.description,
                } if role else None,
            })

        return {
            "current_roles": roles_list,
            "primary_role": next((r for r in roles_list if r["is_primary"]), None),
        }

    async def _derive_reporting_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive reporting relationships from ReportingRelationship."""
        reporting = await db.execute(
            select(ReportingRelationship).where(
                ReportingRelationship.organization_id == caller.organization_id,
                ReportingRelationship.person_id == person.id,
                ReportingRelationship.valid_from <= at_time,
                or_(
                    ReportingRelationship.valid_to.is_(None),
                    ReportingRelationship.valid_to > at_time,
                ),
            )
        )

        reports_to = []
        for rr in reporting.scalars().all():
            manager = await db.get(Employee, rr.manager_person_id)
            reports_to.append({
                "relationship_id": rr.id,
                "type": rr.relationship_type,
                "manager": {
                    "person_id": manager.id,
                    "name": manager.full_name,
                    "email": manager.email,
                } if manager else None,
                "valid_from": rr.valid_from.isoformat(),
                "valid_to": rr.valid_to.isoformat() if rr.valid_to else None,
            })

        # Also get direct reports (people who report to this person)
        direct_reports = await db.execute(
            select(ReportingRelationship).where(
                ReportingRelationship.organization_id == caller.organization_id,
                ReportingRelationship.manager_person_id == person.id,
                ReportingRelationship.valid_from <= at_time,
                or_(
                    ReportingRelationship.valid_to.is_(None),
                    ReportingRelationship.valid_to > at_time,
                ),
            )
        )

        return {
            "reports_to": reports_to,
            "direct_reports": [{
                "person_id": rr.person_id,
                "type": rr.relationship_type,
            } for rr in direct_reports.scalars().all()],
            "span_of_control": len(list(direct_reports.scalars().all())),
        }

    async def _derive_responsibilities_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive responsibilities from OrganizationalResponsibility."""
        responsibilities = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                or_(
                    OrganizationalResponsibility.person_id == person.id,
                    OrganizationalResponsibility.role_id.in_(
                        select(PersonRoleAssignment.role_id).where(
                            PersonRoleAssignment.organization_id == caller.organization_id,
                            PersonRoleAssignment.person_id == person.id,
                            PersonRoleAssignment.valid_from <= at_time,
                            or_(
                                PersonRoleAssignment.valid_to.is_(None),
                                PersonRoleAssignment.valid_to > at_time,
                            ),
                        )
                    ) if person.id else False,
                ),
                OrganizationalResponsibility.valid_from <= at_time,
                or_(
                    OrganizationalResponsibility.valid_to.is_(None),
                    OrganizationalResponsibility.valid_to > at_time,
                ),
            )
        )

        resp_list = []
        for r in responsibilities.scalars().all():
            resp_list.append({
                "responsibility_id": r.id,
                "type": r.responsibility_type,
                "scope_type": r.scope_type,
                "scope_id": r.scope_id,
                "raci": {
                    "accountable": r.raci_accountable,
                    "responsible": r.raci_responsible,
                    "consulted": r.raci_consulted,
                    "informed": r.raci_informed,
                },
                "objective_id": r.objective_id,
                "initiative_id": r.initiative_id,
                "project_id": r.project_id,
                "commitment_id": r.commitment_id,
                "valid_from": r.valid_from.isoformat(),
                "valid_to": r.valid_to.isoformat() if r.valid_to else None,
                "state": r.state,
            })

        # Group by RACI
        return {
            "all": resp_list,
            "accountable": [r for r in resp_list if r["raci"]["accountable"]],
            "responsible": [r for r in resp_list if r["raci"]["responsible"]],
            "consulted": [r for r in resp_list if r["raci"]["consulted"]],
            "informed": [r for r in resp_list if r["raci"]["informed"]],
        }

    async def _derive_commitments_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive commitments from AccountabilityLink and CompanyCommitment."""
        # Get responsibilities with commitment links
        links = await db.execute(
            select(AccountabilityLink).where(
                AccountabilityLink.organization_id == caller.organization_id,
                AccountabilityLink.responsibility_id.in_(
                    select(OrganizationalResponsibility.id).where(
                        OrganizationalResponsibility.organization_id == caller.organization_id,
                        or_(
                            OrganizationalResponsibility.person_id == person.id,
                            OrganizationalResponsibility.role_id.in_(
                                select(PersonRoleAssignment.role_id).where(
                                    PersonRoleAssignment.organization_id == caller.organization_id,
                                    PersonRoleAssignment.person_id == person.id,
                                    PersonRoleAssignment.valid_from <= at_time,
                                    or_(
                                        PersonRoleAssignment.valid_to.is_(None),
                                        PersonRoleAssignment.valid_to > at_time,
                                    ),
                                )
                            ) if person.id else False,
                        ),
                        OrganizationalResponsibility.valid_from <= at_time,
                        or_(
                            OrganizationalResponsibility.valid_to.is_(None),
                            OrganizationalResponsibility.valid_to > at_time,
                        ),
                    )
                ),
                AccountabilityLink.valid_from <= at_time,
                or_(
                    AccountabilityLink.valid_to.is_(None),
                    AccountabilityLink.valid_to > at_time,
                ),
            )
        )

        commitments = []
        for link in links.scalars().all():
            commitment = await db.get(CompanyCommitment, link.commitment_id)
            if commitment:
                commitments.append({
                    "commitment_id": commitment.id,
                    "title": commitment.title,
                    "state": commitment.state,
                    "accountability_type": link.accountability_type,
                    "valid_from": link.valid_from.isoformat(),
                    "valid_to": link.valid_to.isoformat() if link.valid_to else None,
                })

        return {
            "commitments": commitments,
            "count": len(commitments),
        }

    async def _derive_capability_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive capability from Expertise and PersonSkill."""
        # Get expertise
        expertise = await db.execute(
            select(Expertise).where(
                Expertise.organization_id == caller.organization_id,
                Expertise.person_id == person.id,
            ).order_by(Expertise.score.desc())
        )

        expertise_list = []
        for exp in expertise.scalars().all():
            skill = await db.get(CanonicalSkill, exp.skill_id)
            expertise_list.append({
                "skill_id": exp.skill_id,
                "skill_name": skill.canonical_name if skill else "Unknown",
                "skill_category": skill.category if skill else None,
                "score": exp.score,
                "confidence": exp.confidence,
                "lifecycle": exp.lifecycle,
                "evidence_count": exp.evidence_count,
                "strong_count": exp.strong_count,
                "medium_count": exp.medium_count,
                "corroborated_kinds": exp.corroborated_kinds,
                "freshness": exp.freshness,
                "historical_peak": exp.historical_peak,
                "last_observed": exp.last_observed.isoformat() if exp.last_observed else None,
            })

        # Get declared skills
        person_skills = await db.execute(
            select(EmployeeSkill).where(
                EmployeeSkill.organization_id == caller.organization_id,
                EmployeeSkill.employee_id == person.id,
            )
        )

        declared_skills = []
        for ps in person_skills.scalars().all():
            skill = await db.get(CanonicalSkill, ps.skill_id)
            declared_skills.append({
                "skill_id": ps.skill_id,
                "skill_name": skill.canonical_name if skill else "Unknown",
                "declared_level": ps.level,
                "years_experience": ps.years_experience,
                "verified": ps.verified,
            })

        return {
            "expertise": expertise_list,
            "declared_skills": declared_skills,
            "top_skills": expertise_list[:10],
            "expertise_count": len([e for e in expertise_list if e["lifecycle"] in ("strong", "authoritative")]),
        }

    async def _derive_capacity_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive capacity from availability, workload, and allocations."""
        # Availability
        availability = await db.execute(
            select(EmployeeAvailability).where(
                EmployeeAvailability.organization_id == caller.organization_id,
                EmployeeAvailability.employee_id == person.id,
            )
        )
        avail = availability.scalar_one_or_none()

        # Current workload
        workload = await db.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.organization_id == caller.organization_id,
                WorkloadSnapshot.employee_id == person.id,
            ).order_by(WorkloadSnapshot.period_start.desc()).limit(1)
        )
        current_workload = workload.scalar_one_or_none()

        # Active allocations
        allocations = await db.execute(
            select(CapacityAllocation).where(
                CapacityAllocation.organization_id == caller.organization_id,
                # Need to join through project to find person's allocations
                # For simplicity, use project-based lookup
            )
        )

        return {
            "availability": {
                "status": avail.status if avail else "unknown",
                "note": avail.note,
                "available_from": avail.available_from.isoformat() if avail and avail.available_from else None,
                "available_until": avail.available_until.isoformat() if avail and avail.available_until else None,
            } if avail else None,
            "workload": {
                "period_start": current_workload.period_start.isoformat() if current_workload and current_workload.period_start else None,
                "period_end": current_workload.period_end.isoformat() if current_workload and current_workload.period_end else None,
                "capacity_hours": current_workload.capacity_hours if current_workload else None,
                "allocated_hours": current_workload.allocated_hours if current_workload else None,
                "utilization": current_workload.utilization if current_workload else None,
                "is_overloaded": current_workload.is_overloaded if current_workload else None,
            } if current_workload else None,
            "state": current_workload.is_overloaded if current_workload else False,
        }

    async def _derive_work_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive work context from tasks, actions, and projects."""
        # Company actions assigned to this person
        actions = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.assignee_id == person.id,
                CompanyAction.assignee_type == "employee",
                CompanyAction.state.in_(["in_progress", "ready", "awaiting_approval"]),
            ).order_by(CompanyAction.priority_score.desc()).limit(20)
        )

        # Project membership
        from app.models.project import ProjectMember
        projects = await db.execute(
            select(ProjectMember).where(
                ProjectMember.organization_id == caller.organization_id,
                ProjectMember.employee_id == person.id,
            )
        )

        return {
            "active_actions": [{
                "action_id": a.id,
                "title": a.title,
                "type": a.action_type,
                "state": a.state,
                "risk": a.risk,
                "due_at": a.due_at.isoformat() if a.due_at else None,
            } for a in actions.scalars().all()],
            "projects": [{
                "project_id": p.project_id,
                "role": p.role,
            } for p in projects.scalars().all()],
        }

    async def _derive_process_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive process context from Gate 19 processes."""
        # Process executions where person is owner or participant
        executions = await db.execute(
            select(ProcessExecution).where(
                ProcessExecution.organization_id == caller.organization_id,
                or_(
                    ProcessExecution.owner_id == person.id,
                    ProcessExecution.participants_json.contains(person.id),
                ),
                ProcessExecution.state.in_(["active", "paused"]),
            )
        )

        exec_list = []
        for exec in executions.scalars().all():
            process = await db.get(CanonicalBusinessProcess, exec.process_id)
            exec_list.append({
                "execution_id": exec.id,
                "process_id": exec.process_id,
                "process_name": process.name if process else "Unknown",
                "state": exec.state,
                "current_step": exec.current_step_key,
            })

        # Process steps assigned to this person
        steps = await db.execute(
            select(ProcessStep).where(
                ProcessStep.organization_id == caller.organization_id,
                # Check if person is assigned to step
                # This depends on allocation model
            )
        )

        return {
            "active_executions": exec_list,
            "owned_executions": [e for e in exec_list if e.get("owner_id") == person.id],
        }

    async def _derive_knowledge_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive knowledge context from Gate 20."""
        # Knowledge artifacts owned/authored
        artifacts = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                or_(
                    CanonicalKnowledgeArtifact.owner_id == person.id,
                    CanonicalKnowledgeArtifact.author_id == person.id,
                ),
            ).limit(20)
        )

        # Claims by this person
        claims = await db.execute(
            select(CanonicalKnowledgeClaim).where(
                CanonicalKnowledgeClaim.organization_id == caller.organization_id,
                CanonicalKnowledgeClaim.created_by == person.id,
            ).limit(20)
        )

        # Knowledge relations where person is target
        relations = await db.execute(
            select(CanonicalKnowledgeRelation).where(
                CanonicalKnowledgeRelation.organization_id == caller.organization_id,
                CanonicalKnowledgeRelation.target_type == "person",
                CanonicalKnowledgeRelation.target_id == person.id,
            )
        )

        return {
            "owned_artifacts": [{
                "artifact_id": a.id,
                "title": a.title,
                "kind": a.kind,
                "lifecycle_state": a.lifecycle_state,
                "epistemic_status": a.epistemic_status,
            } for a in artifacts.scalars().all()],
            "authored_claims": [{
                "claim_id": c.id,
                "predicate": c.predicate,
                "object_text": c.object_text,
                "status": c.status,
                "verification_result": c.verification_result,
            } for c in claims.scalars().all()],
            "knowledge_relations": [{
                "relation_id": r.id,
                "source_type": r.source_type,
                "relation_type": r.relation_type,
            } for r in relations.scalars().all()],
        }

    async def _derive_customer_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive customer context from Gate 14."""
        from app.models.customer import Customer
        from app.models.business_commercial import BusinessNeed, CommercialIntent
        from app.models.project import ProjectMember

        # Customer account ownership
        customers = await db.execute(
            select(Customer).where(
                Customer.organization_id == caller.organization_id,
                # Check if person is account owner or team member
            )
        )

        # Project-based customer relationships
        project_memberships = await db.execute(
            select(ProjectMember).where(
                ProjectMember.organization_id == caller.organization_id,
                ProjectMember.employee_id == person.id,
            )
        )

        project_ids = [pm.project_id for pm in project_memberships.scalars().all()]

        # Business needs/commercial intents for those projects
        needs = await db.execute(
            select(BusinessNeed).where(
                BusinessNeed.organization_id == caller.organization_id,
                BusinessNeed.project_id.in_(project_ids) if project_ids else False,
            )
        )

        intents = await db.execute(
            select(CommercialIntent).where(
                CommercialIntent.organization_id == caller.organization_id,
                CommercialIntent.project_id.in_(project_ids) if project_ids else False,
            )
        )

        return {
            "projects_with_customer_work": project_ids,
            "business_needs": len(list(needs.scalars().all())),
            "commercial_intents": len(list(intents.scalars().all())),
        }

    async def _derive_assets_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive asset assignments from EmployeeAsset."""
        from app.models.hr import EmployeeAsset

        assets = await db.execute(
            select(EmployeeAsset).where(
                EmployeeAsset.organization_id == caller.organization_id,
                EmployeeAsset.employee_id == person.id,
                EmployeeAsset.status.in_(["assigned", "available"]),
            )
        )

        return {
            "assigned_assets": [{
                "asset_id": a.id,
                "name": a.name,
                "category": a.category,
                "serial_number": a.serial_number,
                "status": a.status,
            } for a in assets.scalars().all()],
        }

    async def _derive_learning_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive learning context from Gate 9 and Gate 20."""
        # Organizational learning where person is source or subject
        learning = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.source_id == person.id,
            ).order_by(OrganizationalLearning.observed_at.desc()).limit(10)
        )

        # Outcome assessments for this person's actions
        assessments = await db.execute(
            select(OutcomeAssessment).where(
                OutcomeAssessment.organization_id == caller.organization_id,
                OutcomeAssessment.subject_type.in_(["action", "task"]),
                OutcomeAssessment.subject_id.in_(
                    select(CompanyAction.id).where(
                        CompanyAction.organization_id == caller.organization_id,
                        CompanyAction.assignee_id == person.id,
                    )
                ),
            ).limit(10)
        )

        return {
            "lessons_learned": [{
                "learning_id": l.id,
                "title": l.title,
                "lesson": l.lesson,
                "kind": l.kind,
                "confidence": l.confidence,
            } for l in learning.scalars().all()],
            "outcome_assessments": [{
                "assessment_id": a.id,
                "subject_type": a.subject_type,
                "subject_id": a.subject_id,
                "assessment": a.assessment,
                "variance_pct": a.variance_pct,
            } for a in assessments.scalars().all()],
        }

    async def _derive_development_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive development needs from WorkforceDevelopmentNeed."""
        dev_needs = await db.execute(
            select(WorkforceDevelopmentNeed).where(
                WorkforceDevelopmentNeed.organization_id == caller.organization_id,
                WorkforceDevelopmentNeed.person_id == person.id,
            ).order_by(WorkforceDevelopmentNeed.created_at.desc())
        )

        return {
            "development_needs": [{
                "need_id": d.id,
                "skill_id": d.skill_id,
                "target_proficiency": d.target_proficiency,
                "current_proficiency": d.current_proficiency,
                "state": d.state,
                "progress": d.progress,
                "source_type": d.source_type,
                "source_id": d.source_id,
                "capability_change_verified": d.capability_change_verified,
            } for d in dev_needs.scalars().all()],
        }

    async def _derive_continuity_context(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        at_time: datetime,
    ) -> dict:
        """Derive continuity risk from WorkforceContinuityEvent."""
        events = await db.execute(
            select(WorkforceContinuityEvent).where(
                WorkforceContinuityEvent.organization_id == caller.organization_id,
                WorkforceContinuityEvent.person_id == person.id,
                WorkforceContinuityEvent.status.in_(["active", "mitigating"]),
            )
        )

        return {
            "active_continuity_events": [{
                "event_id": e.id,
                "event_type": e.event_type,
                "severity": e.severity,
                "effective_from": e.effective_from.isoformat(),
                "effective_to": e.effective_to.isoformat() if e.effective_to else None,
                "impact_summary": e.impact_summary,
                "mitigation_status": e.mitigation_status,
                "successor_person_id": e.successor_person_id,
            } for e in events.scalars().all()],
        }

    # -------------------------------------------------------------------------
    # 3. EPISTEMIC BREAKDOWN POPULATION
    # -------------------------------------------------------------------------

    async def _populate_epistemic_breakdown(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person: Employee,
        context: dict,
        at_time: datetime,
    ) -> None:
        """Populate epistemic breakdown for transparency."""

        # Identity claims
        context["epistemic_breakdown"]["identity_claims"].append({
            "source": "employee_record",
            "claims": f"Employee {person.employee_number} is {person.full_name}",
            "confidence": "high",
            "provenance": "HR system of record",
        })

        # Membership facts
        if context["membership"]["current_membership"]:
            context["epistemic_breakdown"]["membership_facts"].append({
                "source": "person_membership",
                "claims": f"Current status: {context['membership']['current_membership']['status']}",
                "confidence": "high",
                "valid_from": context["membership"]["current_membership"]["valid_from"],
            })

        # Role assignments
        for role in context["roles"]["current_roles"]:
            context["epistemic_breakdown"]["role_assignments"].append({
                "source": "person_role_assignment",
                "claims": f"Holds role {role['role_title']} ({role['role_type']})",
                "confidence": "high",
                "is_primary": role["is_primary"],
            })

        # Responsibilities
        for resp in context["responsibilities"]["all"]:
            context["epistemic_breakdown"]["responsibilities_owned"].append({
                "source": "organizational_responsibility",
                "claims": f"Responsible for {resp['scope_type']}:{resp['scope_id']} (RACI: {resp['raci']})",
                "confidence": "high",
            })

        # Capabilities
        for exp in context["capability"]["expertise"][:5]:
            context["epistemic_breakdown"]["capabilities"].append({
                "source": "expertise_evidence",
                "claims": f"Expertise in {exp['skill_name']}: score {exp['score']}, lifecycle {exp['lifecycle']}",
                "confidence": str(exp["confidence"]),
                "evidence_count": exp["evidence_count"],
            })

        # Capacity facts
        if context["capacity"]["workload"]:
            context["epistemic_breakdown"]["capacity_facts"].append({
                "source": "workload_snapshot",
                "claims": f"Utilization: {context['capacity']['workload']['utilization']}%, overloaded: {context['capacity']['workload']['is_overloaded']}",
                "confidence": "measured",
            })

    # -------------------------------------------------------------------------
    # 4. PREDICTION / COUNTERFACTUAL / DIGITAL TWIN INTEGRATION
    # -------------------------------------------------------------------------

    async def _provide_workforce_predictions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
        at_time: datetime,
    ) -> dict:
        """Provide workforce predictions as input to Gate 10."""
        # Get capacity pressure prediction
        capacity_context = await self._derive_capacity_context(db, caller, await db.get(Employee, person_id), at_time)

        workload = capacity_context.get("workload") or {}

        return {
            "capacity_pressure_risk": capacity_context.get("state", False),
            "utilization": workload.get("utilization"),
            "overloaded": capacity_context.get("state", False),
            "epistemic_note": "Workforce predictions use capacity and capability as contextual input. Prediction ≠ Truth.",
        }

    async def _provide_workforce_counterfactuals(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
        at_time: datetime,
    ) -> dict:
        """Provide workforce counterfactual scenarios as input to Gate 11."""
        person = await db.get(Employee, person_id)

        # Get responsibilities
        responsibilities = await self._derive_responsibilities_context(db, caller, person, at_time)

        return {
            "person_unavailable_scenario": {
                "person_id": person_id,
                "responsibilities_at_risk": len(responsibilities["accountable"]) + len(responsibilities["responsible"]),
                "epistemic_note": "Counterfactual scenario. Scenario changes are hypothetical and isolated from canonical reality.",
            },
        }

    async def _provide_workforce_digital_twin(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
        at_time: datetime,
    ) -> dict:
        """Provide workforce state for Digital Twin (Gate 12)."""
        person = await db.get(Employee, person_id)
        context = await self.derive_person_operating_context(
            db, caller=caller, person_id=person_id, at_time=at_time,
            include_predictions=False, include_counterfactuals=False, include_digital_twin=False
        )

        return {
            "person_id": person_id,
            "twin_scope": "person",
            "current_state": {
                "membership": context["membership"],
                "roles": context["roles"],
                "responsibilities_count": len(context["responsibilities"]["all"]),
                "expertise_count": len(context["capability"]["expertise"]),
                "capacity_state": context["capacity"]["state"],
                "active_actions": len(context["work"]["active_actions"]),
            },
            "epistemic_note": "Digital Twin projection. Represents current canonical state, not predicted behavior.",
        }

    # -------------------------------------------------------------------------
    # 5. WORKFORCE CAPABILITY GAP DETECTION
    # -------------------------------------------------------------------------

    async def detect_capability_gaps(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[WorkforceCapabilityGap]:
        """Detect capability gaps from process demands vs available capacity."""
        gaps_created = []

        # Get active process demands
        demands = await db.execute(
            select(AllocationDemand).where(
                AllocationDemand.organization_id == caller.organization_id,
            )
        )

        for demand in demands.scalars().all():
            # Check available supply
            supply = await db.execute(
                select(CapacitySnapshot).where(
                    CapacitySnapshot.organization_id == caller.organization_id,
                    CapacitySnapshot.capability == demand.capability,
                    CapacitySnapshot.window_start <= demand.window_end,
                    CapacitySnapshot.window_end >= demand.window_start,
                ).order_by(CapacitySnapshot.occurred_at.desc()).limit(1)
            )

            supply_snapshot = supply.scalar_one_or_none()

            if not supply_snapshot or supply_snapshot.supply_units < demand.units:
                # Gap detected
                fp = _compute_fingerprint({
                    "org": caller.organization_id,
                    "type": "capability_gap",
                    "skill": demand.capability,
                    "window": f"{demand.window_start}_{demand.window_end}",
                    "project": demand.project_id,
                })

                existing = await db.execute(
                    select(WorkforceCapabilityGap).where(
                        WorkforceCapabilityGap.organization_id == caller.organization_id,
                        WorkforceCapabilityGap.fingerprint == fp,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                gap = WorkforceCapabilityGap(
                    organization_id=caller.organization_id,
                    skill_id=demand.capability,  # This should be canonical_skill.id - simplified
                    scope_type="project",
                    scope_id=demand.project_id,
                    required_units=demand.units,
                    required_proficiency=demand.proficiency,
                    available_units=supply_snapshot.supply_units if supply_snapshot else 0,
                    severity="critical" if not supply_snapshot else "warning",
                    source_type="process_demand",
                    source_id=demand.id,
                    affected_process_ids_json=[demand.project_id],
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=fp,
                )
                db.add(gap)
                gaps_created.append(gap)

        await db.flush()
        return gaps_created

    # -------------------------------------------------------------------------
    # 6. WORKFORCE CONTINUITY EVENT CREATION
    # -------------------------------------------------------------------------

    async def create_continuity_event(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        person_id: str,
        event_type: str,
        trigger_source: str,
        trigger_id: str,
        effective_from: datetime,
        effective_to: Optional[datetime] = None,
        notice_period_days: Optional[int] = None,
    ) -> WorkforceContinuityEvent:
        """Create a workforce continuity event and derive impact."""

        person = await db.get(Employee, person_id)
        if not person or person.organization_id != caller.organization_id:
            raise ValueError("Person not found")

        # Derive responsibilities at risk
        at_time = effective_from
        responsibilities = await self._derive_responsibilities_context(db, caller, person, at_time)
        commitments = await self._derive_commitments_context(db, caller, person, at_time)

        # Get process ownership
        process_ownerships = await db.execute(
            select(CanonicalBusinessProcess).where(
                CanonicalBusinessProcess.organization_id == caller.organization_id,
                # Process ownership would be tracked via responsibilities
            )
        )

        # Get knowledge ownership
        knowledge_ownership = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                or_(
                    CanonicalKnowledgeArtifact.owner_id == person_id,
                    CanonicalKnowledgeArtifact.author_id == person_id,
                ),
            )
        )

        # Customer impact
        from app.models.customer import Customer
        customer_impact = await db.execute(
            select(Customer).where(
                Customer.organization_id == caller.organization_id,
                # Would need account ownership link
            )
        )

        fp = _compute_fingerprint({
            "org": caller.organization_id,
            "person": person_id,
            "type": event_type,
            "trigger": f"{trigger_source}:{trigger_id}",
            "effective": effective_from.isoformat(),
        })

        existing_result = await db.execute(
            select(WorkforceContinuityEvent).where(
                WorkforceContinuityEvent.organization_id == caller.organization_id,
                WorkforceContinuityEvent.fingerprint == fp,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing

        event = WorkforceContinuityEvent(
            organization_id=caller.organization_id,
            person_id=person_id,
            event_type=event_type,
            trigger_source=trigger_source,
            trigger_id=trigger_id,
            effective_from=effective_from,
            effective_to=effective_to,
            notice_period_days=notice_period_days,
            severity="critical" if len(responsibilities["accountable"]) > 0 else "warning",
            impact_summary=f"Person {person.full_name} ({person.employee_number}) {event_type}. "
                          f"{len(responsibilities['accountable'])} accountable responsibilities, "
                          f"{len(commitments['commitments'])} commitments at risk.",
            responsibilities_affected_json=[r["responsibility_id"] for r in responsibilities["accountable"] + responsibilities["responsible"]],
            commitments_affected_json=[c["commitment_id"] for c in commitments["commitments"]],
            knowledge_artifacts_affected_json=[],
            capacity_units_lost=1,
            detected_at=utcnow(),
            detected_by="system",
            detection_method="derived",
            fingerprint=fp,
        )
        db.add(event)
        await db.flush()
        return event

    # -------------------------------------------------------------------------
    # 7. DEVELOPMENT NEED CREATION
    # -------------------------------------------------------------------------

    async def create_development_need(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        person_id: str,
        skill_id: str,
        target_proficiency: str,
        source_type: str,
        source_id: str,
        current_proficiency: Optional[str] = None,
        planned_actions: Optional[List[dict]] = None,
    ) -> WorkforceDevelopmentNeed:
        """Create a development need from a capability gap or other source."""

        person = await db.get(Employee, person_id)
        if not person or person.organization_id != caller.organization_id:
            raise ValueError("Person not found")

        skill = await db.get(CanonicalSkill, skill_id)
        if not skill or skill.organization_id != caller.organization_id:
            raise ValueError("Skill not found")

        if target_proficiency not in ("high", "expert"):
            raise ValueError("target_proficiency must be 'high' or 'expert'")

        # Check current proficiency from expertise
        expertise = await db.execute(
            select(Expertise).where(
                Expertise.organization_id == caller.organization_id,
                Expertise.person_id == person_id,
                Expertise.skill_id == skill_id,
            )
        )
        exp = expertise.scalar_one_or_none()
        current = current_proficiency or ("expert" if exp and exp.score >= 70 else "high" if exp and exp.score >= 50 else "developing")

        fp = _compute_fingerprint({
            "org": caller.organization_id,
            "person": person_id,
            "skill": skill_id,
            "source": f"{source_type}:{source_id}",
        })

        existing_result = await db.execute(
            select(WorkforceDevelopmentNeed).where(
                WorkforceDevelopmentNeed.organization_id == caller.organization_id,
                WorkforceDevelopmentNeed.fingerprint == fp,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing

        need = WorkforceDevelopmentNeed(
            organization_id=caller.organization_id,
            person_id=person_id,
            skill_id=skill_id,
            target_proficiency=target_proficiency,
            current_proficiency=current,
            source_type=source_type,
            source_id=source_id,
            planned_actions_json=planned_actions or [],
            source_event_id=f"dev-need-{uuid.uuid4().hex[:16]}",
            created_by=caller.employee_id or caller.user_id,
            fingerprint=fp,
        )
        db.add(need)
        await db.flush()
        return need

    # -------------------------------------------------------------------------
    # 8. GOVERNANCE & ACCESS
    # -------------------------------------------------------------------------

    async def _verify_person_access(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
    ) -> bool:
        """Verify caller has access to person's workforce context."""
        # In production, this would check governance scopes, permissions, etc.
        # For now, allow org-wide access
        person = await db.get(Employee, person_id)
        if not person:
            return False
        return person.organization_id == caller.organization_id

    async def verify_workforce_access(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        person_id: str,
    ) -> bool:
        """Public method to verify workforce access."""
        return await self._verify_person_access(db, caller, person_id)

    # -------------------------------------------------------------------------
    # 9. QUERY LOGGING
    # -------------------------------------------------------------------------

    async def _log_context_query(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        person_id: str,
        context: dict,
        at_time: datetime,
    ) -> None:
        """Log context query for audit trail."""
        # In production, would create a KnowledgeContextQuery or similar
        # For now, just ensure the query is traceable through the company brain
        pass


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

canonical_workforce_service = CanonicalWorkforceService()