"""Canonical Customer & Commercial Operating Fabric Service.

Derives customer/business operating slices, impact analyses, risks, and contexts
from the canonical company reality (Gates 8-13).

This is a DERIVED PROJECTION layer — it does NOT create a second customer reality.
All data is composed from existing canonical primitives:
- Gate 8: People, Work, Communication, Meetings, Organizational Intelligence
- Gate 9: Institutional Learning
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
"""

import hashlib
import json
import logging
import time
import asyncio
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.organization import gen_uuid

# Lock for exact-once operations per (org_id, customer_id)
_SLICE_LOCKS: Dict[str, asyncio.Lock] = {}
_SLICE_LOCKS_LOCK = asyncio.Lock()
from app.models.business_commercial import (
    BusinessNeed,
    CommercialIntent,
    BusinessOutcome,
    CustomerRisk,
    CustomerOperatingSlice,
    CustomerImpactAnalysis,
    CustomerOperatingContext,
)
from app.models.customer import (
    Customer,
    CustomerContact,
    CustomerProjectLink,
    CustomerMeetingLink,
)
from app.models.lead import Opportunity
from app.models.customer_intelligence import (
    CustomerSignal,
    CustomerTheme,
    CustomerCommitment,
    CustomerHealthRow,
    CustomerOutcome as CustomerOutcomeModel,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
)
from app.models.project import Project
from app.models.task import Task
from app.models.company_actions import CompanyAction, CompanyActionOutcome
from app.models.company_operating import (
    CompanyDecision,
    CompanyScenarioRun,
)
from app.models.organizational_learning import OrganizationalLearning
from app.models.intelligence import PatternDetection
from app.intelligence.strategic_alignment_engine import (
    strategic_alignment_engine,
)
from app.intelligence.canonical_digital_twin_service import (
    canonical_digital_twin_service,
)
from app.intelligence.counterfactual_intelligence_service import (
    counterfactual_intelligence_service,
)
from app.intelligence.predictive_intelligence_service import (
    predictive_intelligence_service,
)
from app.intelligence.company_operating_engine import (
    company_operating_engine,
)

logger = logging.getLogger("vcos.intelligence.customer_operating_fabric")


class CustomerOperatingFabricService:
    """
    Service for deriving the canonical customer operating fabric.

    All methods return DERIVED PROJECTIONS over canonical reality.
    They do NOT mutate canonical data.
    """

    # Maximum depth for traversal
    MAX_TRAVERSAL_DEPTH = 5

    def __init__(self):
        pass

    # ================================================================
    # 1. CUSTOMER OPERATING SLICE
    # ================================================================

    async def derive_customer_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        customer_id: str,
    ) -> CustomerOperatingSlice:
        """
        Derive a governed, point-in-time operating slice for a customer.

        Composes all canonical reality relevant to the customer:
        - Business needs, opportunities, commercial intents
        - Commitments, projects, responsible people
        - Tasks, dependencies, meetings, communication
        - Outcomes, predictions, risks
        - Institutional learning
        """
        start = time.perf_counter()

        # Governance: verify access to customer
        await self._verify_customer_access(db, caller, customer_id)

        # Build input fingerprint for exact-once
        input_data = {
            "customer_id": customer_id,
            "organization_id": caller.organization_id,
            "scope": "customer_operating_slice",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]

        # Acquire lock for exact-once semantics
        lock_key = f"{caller.organization_id}:{customer_id}"
        async with _SLICE_LOCKS_LOCK:
            if lock_key not in _SLICE_LOCKS:
                _SLICE_LOCKS[lock_key] = asyncio.Lock()
            lock = _SLICE_LOCKS[lock_key]

        async with lock:
            # Check for existing slice with same fingerprint
            existing = await db.execute(
                select(CustomerOperatingSlice).where(
                    CustomerOperatingSlice.organization_id == caller.organization_id,
                    CustomerOperatingSlice.customer_id == customer_id,
                    CustomerOperatingSlice.input_fingerprint == input_fingerprint,
                )
            )
            existing = existing.scalars().first()
            if existing:
                return existing

            # Get customer
            customer = await db.get(Customer, customer_id)
            if not customer:
                raise ValueError(f"Customer not found: {customer_id}")

            # 1. Business Needs
            business_needs = await self._get_customer_business_needs(db, caller, customer_id)

            # 2. Opportunities
            opportunities = await self._get_customer_opportunities(db, caller, customer_id)

            # 3. Commercial Intents
            commercial_intents = await self._get_customer_commercial_intents(db, caller, customer_id)

            # 4. Commitments (Customer + Company)
            commitments = await self._get_customer_commitments(db, caller, customer_id)

            # 5. Projects (via CustomerProjectLink)
            projects = await self._get_customer_projects(db, caller, customer_id)

            # 6. Responsible People (via CompanyCommitment → Responsibility)
            responsible_people = await self._get_customer_responsible_people(db, caller, customer_id)

            # 7. Tasks (via Project → Task)
            tasks = await self._get_customer_tasks(db, caller, customer_id)

            # 8. Dependencies (via TaskDependency)
            dependencies = await self._get_customer_dependencies(db, caller, customer_id)

            # 9. Meetings
            meetings = await self._get_customer_meetings(db, caller, customer_id)

            # 10. Communication Threads
            comm_threads = await self._get_customer_communication(db, caller, customer_id)

            # 11. Outcomes
            outcomes = await self._get_customer_outcomes(db, caller, customer_id)

            # 12. Predictions (Gate 10)
            predictions = await self._get_customer_predictions(db, caller, customer_id)

            # 13. Risks
            risks = await self._get_customer_risks(db, caller, customer_id)

            # 14. Institutional Lessons (Gate 9)
            lessons = await self._get_customer_institutional_lessons(db, caller, customer_id)

            # 14. Capacity Health
            capacity_health, capacity_gap = await self._assess_customer_capacity(db, caller, customer_id)

            # 15. Risk Assessment
            risk_level, risk_count = self._assess_overall_risk(risks)

            # 16. Financial Projections
            proj_revenue, proj_cost, proj_margin = self._project_customer_financials(
                commitments, commercial_intents
            )

# Build slice
            slice_id = gen_uuid()
            computed_at = utcnow()
            slice_obj = CustomerOperatingSlice(
                id=slice_id,
                organization_id=caller.organization_id,
                customer_id=customer_id,
                input_fingerprint=input_fingerprint,
                business_needs=business_needs,
                opportunities=opportunities,
                commercial_intents=commercial_intents,
                commitments=commitments,
                projects=projects,
                responsible_people=responsible_people,
                tasks=tasks,
                dependencies=dependencies,
                meetings=meetings,
                communication_threads=comm_threads,
                outcomes=outcomes,
                predictions=predictions,
                risks=[self._risk_to_dict(r) for r in risks],
                institutional_lessons=lessons,
                open_commitments=sum(1 for c in commitments if c.get("status") in ("active", "on_track", "pending", "at_risk")),
                at_risk_commitments=sum(1 for c in commitments if c.get("status") == "at_risk"),
                open_dependencies=len(dependencies),
                blocked_tasks=sum(1 for t in tasks if t.get("status") == "blocked"),
                overdue_meetings=sum(1 for m in meetings if m.get("status") == "overdue"),
                capacity_health=capacity_health,
                capacity_gap=capacity_gap,
                overall_risk_level=risk_level,
                risk_count=risk_count,
                projected_revenue=proj_revenue,
                projected_cost=proj_cost,
                projected_margin=proj_margin,
                computed_at=computed_at,
                computation_duration_ms=int((time.perf_counter() - start) * 1000),
                fingerprint=hashlib.sha256(
                    json.dumps({
                        "customer_id": customer_id,
                        "commitment_count": len(commitments),
                        "project_count": len(projects),
                    }, sort_keys=True, default=str).encode()
                ).hexdigest()[:64],
                created_at=computed_at,
                updated_at=computed_at,
            )

            # Use raw SQL INSERT with ON CONFLICT DO NOTHING for exact-once
            from sqlalchemy import text
            insert_sql = text("""
                INSERT INTO customer_operating_slices (
                    id, organization_id, customer_id, input_fingerprint,
                    business_needs, opportunities, commercial_intents, commitments,
                    projects, responsible_people, tasks, dependencies,
                    meetings, communication_threads, outcomes, predictions,
                    risks, institutional_lessons,
                    open_commitments, at_risk_commitments, open_dependencies,
                    blocked_tasks, overdue_meetings,
                    capacity_health, capacity_gap, overall_risk_level, risk_count,
                    projected_revenue, projected_cost, projected_margin,
                    computed_at, computation_duration_ms, fingerprint,
                    created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :customer_id, :input_fingerprint,
                    :business_needs, :opportunities, :commercial_intents, :commitments,
                    :projects, :responsible_people, :tasks, :dependencies,
                    :meetings, :communication_threads, :outcomes, :predictions,
                    :risks, :institutional_lessons,
                    :open_commitments, :at_risk_commitments, :open_dependencies,
                    :blocked_tasks, :overdue_meetings,
                    :capacity_health, :capacity_gap, :overall_risk_level, :risk_count,
                    :projected_revenue, :projected_cost, :projected_margin,
                    :computed_at, :computation_duration_ms, :fingerprint,
                    :created_at, :updated_at
                )
                ON CONFLICT (organization_id, customer_id, input_fingerprint) DO NOTHING
            """)

            await db.execute(insert_sql, {
                "id": slice_id,
                "organization_id": slice_obj.organization_id,
                "customer_id": slice_obj.customer_id,
                "input_fingerprint": slice_obj.input_fingerprint,
                "business_needs": json.dumps(slice_obj.business_needs),
                "opportunities": json.dumps(slice_obj.opportunities),
                "commercial_intents": json.dumps(slice_obj.commercial_intents),
                "commitments": json.dumps(slice_obj.commitments),
                "projects": json.dumps(slice_obj.projects),
                "responsible_people": json.dumps(slice_obj.responsible_people),
                "tasks": json.dumps(slice_obj.tasks),
                "dependencies": json.dumps(slice_obj.dependencies),
                "meetings": json.dumps(slice_obj.meetings),
                "communication_threads": json.dumps(slice_obj.communication_threads),
                "outcomes": json.dumps(slice_obj.outcomes),
                "predictions": json.dumps(slice_obj.predictions),
                "risks": json.dumps(slice_obj.risks),
                "institutional_lessons": json.dumps(slice_obj.institutional_lessons),
                "open_commitments": slice_obj.open_commitments,
                "at_risk_commitments": slice_obj.at_risk_commitments,
                "open_dependencies": slice_obj.open_dependencies,
                "blocked_tasks": slice_obj.blocked_tasks,
                "overdue_meetings": slice_obj.overdue_meetings,
                "capacity_health": slice_obj.capacity_health,
                "capacity_gap": slice_obj.capacity_gap,
                "overall_risk_level": slice_obj.overall_risk_level,
                "risk_count": slice_obj.risk_count,
                "projected_revenue": slice_obj.projected_revenue,
                "projected_cost": slice_obj.projected_cost,
                "projected_margin": slice_obj.projected_margin,
                "computed_at": slice_obj.computed_at,
                "computation_duration_ms": slice_obj.computation_duration_ms,
                "fingerprint": slice_obj.fingerprint,
                "created_at": slice_obj.created_at,
                "updated_at": slice_obj.updated_at,
            })

            # Query the inserted/upserted record
            result = await db.execute(
                select(CustomerOperatingSlice).where(
                    CustomerOperatingSlice.organization_id == caller.organization_id,
                    CustomerOperatingSlice.customer_id == customer_id,
                    CustomerOperatingSlice.input_fingerprint == input_fingerprint,
                )
            )
            inserted = result.scalars().first()
            if inserted:
                return inserted

            # Should not reach here
            raise RuntimeError("Failed to insert or find customer operating slice")

    # ================================================================
    # 2. CUSTOMER IMPACT ANALYSIS
    # ================================================================

    async def analyze_customer_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        customer_id: str,
        trigger_type: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_params: Optional[Dict[str, Any]] = None,
    ) -> CustomerImpactAnalysis:
        """
        Analyze the cross-domain impact of a change on a customer.

        Uses Gate 13 Strategic Alignment for propagation.
        """
        trigger_params = trigger_params or {}

        await self._verify_customer_access(db, caller, customer_id)

        input_data = {
            "customer_id": customer_id,
            "trigger_type": trigger_type,
            "trigger_entity_type": trigger_entity_type,
            "trigger_entity_id": trigger_entity_id,
            "trigger_params": trigger_params,
        }
        fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]

        # Check existing
        existing = await db.execute(
            select(CustomerImpactAnalysis).where(
                CustomerImpactAnalysis.organization_id == caller.organization_id,
                CustomerImpactAnalysis.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing

        # Use Gate 13 strategic alignment for propagation
        # Trace from trigger entity to customer commitments
        impact = await self._propagate_impact_to_customer(
            db, caller, customer_id, trigger_entity_type, trigger_entity_id, trigger_type
        )

        # Assess customer outcome impact
        outcome_impact = await self._assess_customer_outcome_impact(
            db, caller, customer_id, impact
        )

        # Financial impact
        revenue_impact = outcome_impact.get("revenue_impact")
        margin_impact = outcome_impact.get("margin_impact")

        # Relationship risk change
        relationship_risk = outcome_impact.get("relationship_risk_change", 0.0)

        # Risk assessment
        risk_assessment = await self._assess_impact_risks(db, caller, impact)
        new_risks = risk_assessment.get("new_risks", [])
        escalated_risks = risk_assessment.get("escalated_risks", [])

        # Find relevant counterfactual scenarios
        scenarios = await self._get_relevant_scenarios(db, caller, customer_id, impact)

        analysis = CustomerImpactAnalysis(
            organization_id=caller.organization_id,
            customer_id=customer_id,
            trigger_type=impact.get("trigger_type", trigger_type),
            trigger_entity_type=impact.get("trigger_entity_type", trigger_entity_type),
            trigger_entity_id=impact.get("trigger_entity_id", trigger_entity_id),
            trigger_params=trigger_params,
            affected_commitments=impact.get("affected_commitments", []),
            affected_projects=impact.get("affected_projects", []),
            affected_objectives=impact.get("affected_objectives", []),
            affected_people=impact.get("affected_people", []),
            affected_capacity=impact.get("affected_capacity", []),
            customer_outcome_impact=outcome_impact,
            revenue_impact=revenue_impact,
            margin_impact=margin_impact,
            relationship_risk_change=relationship_risk,
            risk_assessment=risk_assessment,
            new_risks=new_risks,
            escalated_risks=escalated_risks,
            scenario_ids=scenarios,
            confidence=0.6,
            source_event_id=input_data.get("source_event_id"),
            fingerprint=hashlib.sha256(
                json.dumps(input_data, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
        )

        db.add(analysis)
        await db.flush()

        return analysis

    # ================================================================
    # 3. CUSTOMER RISK DERIVATION
    # ================================================================

    async def derive_customer_risks(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        customer_id: str,
    ) -> List[CustomerRisk]:
        """
        Derive canonical customer risks from canonical company reality.

        Integrates:
        - Customer health (Gate 8.5/4G.5)
        - Commitment risks
        - Capacity risks
        - Dependency risks
        - Predictions (Gate 10)
        - Counterfactuals (Gate 11)
        """
        await self._verify_customer_access(db, caller, customer_id)

        risks = []

        # 1. Customer Health-based risks
        health_risks = await self._derive_health_risks(db, caller, customer_id)
        risks.extend(health_risks)

        # 2. Commitment risks
        commitment_risks = await self._derive_commitment_risks(db, caller, customer_id)
        risks.extend(commitment_risks)

        # 3. Capacity risks
        capacity_risks = await self._derive_capacity_risks(db, caller, customer_id)
        risks.extend(capacity_risks)

        # 4. Dependency risks
        dependency_risks = await self._derive_dependency_risks(db, caller, customer_id)
        risks.extend(dependency_risks)

        # 5. Prediction-based risks (Gate 10)
        prediction_risks = await self._derive_prediction_risks(db, caller, customer_id)
        risks.extend(prediction_risks)

        # 6. Counterfactual risks (Gate 11)
        counterfactual_risks = await self._derive_counterfactual_risks(db, caller, customer_id)
        risks.extend(counterfactual_risks)

        # 7. Counterparty/Financial risks
        financial_risks = await self._derive_financial_risks(db, caller, customer_id)
        risks.extend(financial_risks)

        # Persist new risks
        for risk in risks:
            # Check exact-once
            existing = await db.execute(
                select(CustomerRisk).where(
                    CustomerRisk.organization_id == caller.organization_id,
                    CustomerRisk.fingerprint == risk.fingerprint,
                )
            )
            if not existing.scalars().first():
                db.add(risk)

        await db.flush()

        return risks

    # ================================================================
    # 4. CUSTOMER OPERATING CONTEXT
    # ================================================================

    async def derive_customer_operating_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        customer_id: str,
        role_type: str,
        actor_person_id: Optional[str] = None,
    ) -> CustomerOperatingContext:
        """
        Derive role-appropriate operating context for a customer.

        Roles: account_manager, manager, executive, finance, delivery_lead
        """
        await self._verify_customer_access(db, caller, customer_id)

        input_data = {
            "customer_id": customer_id,
            "role_type": role_type,
            "actor_person_id": actor_person_id or caller.employee_id,
        }
        fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]

        # Check existing
        existing = await db.execute(
            select(CustomerOperatingContext).where(
                CustomerOperatingContext.organization_id == caller.organization_id,
                CustomerOperatingContext.customer_id == customer_id,
                CustomerOperatingContext.role_type == role_type,
                CustomerOperatingContext.input_fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing

        # Get slice first
        slice_obj = await self.derive_customer_operating_slice(db, caller=caller, customer_id=customer_id)

        # Filter/transform based on role
        context = await self._filter_context_for_role(db, caller, slice_obj, role_type, actor_person_id)

        context_obj = CustomerOperatingContext(
            organization_id=caller.organization_id,
            customer_id=customer_id,
            role_type=role_type,
            actor_person_id=actor_person_id or caller.employee_id,
            input_fingerprint=fingerprint,
            attention_items=context.get("attention_items", []),
            commitments=context.get("commitments", []),
            upcoming_meetings=context.get("upcoming_meetings", []),
            open_tasks=context.get("open_tasks", []),
            risks=context.get("risks", []),
            opportunities=context.get("opportunities", []),
            decisions_needed=context.get("decisions_needed", []),
            capacity_alerts=context.get("capacity_alerts", []),
            computation_duration_ms=0,
            fingerprint=hashlib.sha256(
                json.dumps({
                    "customer_id": customer_id,
                    "role_type": role_type,
                    "slice_fp": slice_obj.fingerprint,
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
        )

        db.add(context_obj)
        await db.flush()

        return context_obj

    # ================================================================
    # HELPER METHODS
    # ================================================================

    async def _verify_customer_access(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        customer_id: str,
    ) -> Customer:
        """Verify caller has access to customer."""
        customer = await db.get(Customer, customer_id)
        if not customer:
            raise ValueError(f"Customer not found: {customer_id}")
        if customer.organization_id != caller.organization_id:
            raise ValueError("Cross-tenant access denied")
        return customer

    async def _get_customer_business_needs(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(BusinessNeed).where(
                BusinessNeed.organization_id == caller.organization_id,
                BusinessNeed.customer_id == customer_id,
                BusinessNeed.state.in_(("discovered", "qualified", "prioritized", "addressed")),
            ).order_by(desc(BusinessNeed.discovered_at))
        )
        return [self._business_need_to_dict(bn) for bn in result.scalars().all()]

    async def _get_customer_opportunities(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Opportunity).where(
                Opportunity.organization_id == caller.organization_id,
                Opportunity.customer_id == customer_id,
                Opportunity.stage.in_(("qualified", "proposal", "negotiation")),
            ).order_by(desc(Opportunity.expected_close_date))
        )
        return [
            {
                "id": o.id,
                "title": o.title,
                "stage": o.stage,
                "value": o.value,
                "probability": o.probability,
                "expected_close_date": o.expected_close_date.isoformat() if o.expected_close_date else None,
                "owner_id": o.owner_id,
                "risk_level": o.risk_level,
            }
            for o in result.scalars().all()
        ]

    async def _get_customer_commercial_intents(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.business_commercial import CommercialIntent
        result = await db.execute(
            select(CommercialIntent).where(
                CommercialIntent.organization_id == caller.organization_id,
                CommercialIntent.customer_id == customer_id,
                CommercialIntent.state.in_(("proposed", "qualified", "committed", "in_progress")),
            ).order_by(desc(CommercialIntent.proposed_at))
        )
        return [
            {
                "id": ci.id,
                "kind": ci.kind,
                "title": ci.title,
                "state": ci.state,
                "estimated_value": ci.estimated_value,
                "probability": ci.probability,
                "expected_close_date": ci.expected_close_date.isoformat() if ci.expected_close_date else None,
                "owner_id": ci.owner_person_id,
            }
            for ci in result.scalars().all()
        ]

    async def _get_customer_commitments(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        # CustomerCommitments (Phase 12)
        cc_result = await db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.organization_id == caller.organization_id,
                CustomerCommitment.customer_id == customer_id,
                CustomerCommitment.status.in_(("pending", "on_track", "at_risk")),
            )
        )
        cc_commitments = [
            {
                "id": c.id,
                "type": "customer_commitment",
                "summary": c.summary,
                "expected_at": c.expected_at.isoformat() if c.expected_at else None,
                "status": c.status,
                "project_id": c.project_id,
                "capability": c.capability,
            }
            for c in cc_result.scalars().all()
        ]

        # CompanyCommitments linked to customer projects
        cc_links = await db.execute(
            select(CustomerProjectLink).where(
                CustomerProjectLink.organization_id == caller.organization_id,
                CustomerProjectLink.customer_id == customer_id,
                CustomerProjectLink.status == "active",
            )
        )
        project_ids = [l.project_id for l in cc_links.scalars().all()]

        company_commitments = []
        if project_ids:
            com_result = await db.execute(
                select(CompanyCommitment).where(
                    CompanyCommitment.organization_id == caller.organization_id,
                    CompanyCommitment.scope_type == "project",
                    CompanyCommitment.scope_id.in_(project_ids),
                    CompanyCommitment.state.in_(("active", "authorized", "pending")),
                )
            )
            company_commitments = [
                {
                    "id": c.id,
                    "type": "company_commitment",
                    "title": c.title,
                    "state": c.state,
                    "scope_type": c.scope_type,
                    "scope_id": c.scope_id,
                    "project_id": c.scope_id if c.scope_type == "project" else None,
                }
                for c in com_result.scalars().all()
            ]

        return cc_commitments + company_commitments

    async def _get_customer_projects(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        links = await db.execute(
            select(CustomerProjectLink).where(
                CustomerProjectLink.organization_id == caller.organization_id,
                CustomerProjectLink.customer_id == customer_id,
                CustomerProjectLink.status == "active",
            )
        )
        project_ids = [l.project_id for l in links.scalars().all()]

        if not project_ids:
            return []

        projects = await db.execute(
            select(Project).where(
                Project.organization_id == caller.organization_id,
                Project.id.in_(project_ids),
            )
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "code": p.code,
                "status": p.status,
                "owner_id": p.owner_id,
            }
            for p in projects.scalars().all()
        ]

    async def _get_customer_responsible_people(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        # Get people responsible for customer commitments/projects
        links = await db.execute(
            select(CustomerProjectLink).where(
                CustomerProjectLink.organization_id == caller.organization_id,
                CustomerProjectLink.customer_id == customer_id,
            )
        )
        project_ids = [l.project_id for l in links.scalars().all()]

        if not project_ids:
            return []

        # Get company commitments for these projects
        com_result = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
                CompanyCommitment.scope_type == "project",
                CompanyCommitment.scope_id.in_(project_ids),
                CompanyCommitment.state.in_(("active", "authorized")),
            )
        )
        commitment_ids = [c.id for c in com_result.scalars().all()]

        if not commitment_ids:
            return []

        # Get responsibilities
        from app.models.execution_strategy import OrganizationalResponsibility
        resp_result = await db.execute(
            select(OrganizationalResponsibility).where(
                OrganizationalResponsibility.organization_id == caller.organization_id,
                OrganizationalResponsibility.commitment_id.in_(commitment_ids),
                OrganizationalResponsibility.state == "active",
                OrganizationalResponsibility.raci_responsible == True,
            )
        )
        person_ids = list(set(r.person_id for r in resp_result.scalars().all()))

        if not person_ids:
            return []

        from app.models.employee import Employee
        emp_result = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.id.in_(person_ids),
            )
        )
        return [
            {
                "id": e.id,
                "name": f"{e.first_name} {e.last_name}",
                "email": e.email,
                "team_id": e.team_id,
                "designation": e.designation,
            }
            for e in emp_result.scalars().all()
        ]

    async def _get_customer_tasks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        links = await db.execute(
            select(CustomerProjectLink).where(
                CustomerProjectLink.organization_id == caller.organization_id,
                CustomerProjectLink.customer_id == customer_id,
            )
        )
        project_ids = [l.project_id for l in links.scalars().all()]

        if not project_ids:
            return []

        tasks = await db.execute(
            select(Task).where(
                Task.organization_id == caller.organization_id,
                Task.project_id.in_(project_ids),
                Task.status.in_(("backlog", "todo", "in_progress", "review", "blocked")),
            )
        )
        return [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "project_id": t.project_id,
                "assignee_id": t.assignee_id,
            }
            for t in tasks.scalars().all()
        ]

    async def _get_customer_dependencies(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        tasks = await self._get_customer_tasks(db, caller, customer_id)
        task_ids = [t["id"] for t in tasks]

        if not task_ids:
            return []

        deps = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == caller.organization_id,
                or_(
                    TaskDependency.task_id.in_(task_ids),
                    TaskDependency.depends_on_task_id.in_(task_ids),
                ),
            )
        )
        return [
            {
                "id": d.id,
                "task_id": d.task_id,
                "depends_on_task_id": d.depends_on_task_id,
                "kind": d.kind,
            }
            for d in deps.scalars().all()
        ]

    async def _get_customer_meetings(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        links = await db.execute(
            select(CustomerMeetingLink).where(
                CustomerMeetingLink.organization_id == caller.organization_id,
                CustomerMeetingLink.customer_id == customer_id,
            )
        )
        meeting_ids = [l.meeting_id for l in links.scalars().all()]

        if not meeting_ids:
            return []

        from app.models.meeting import Meeting
        meetings = await db.execute(
            select(Meeting).where(
                Meeting.organization_id == caller.organization_id,
                Meeting.id.in_(meeting_ids),
            ).order_by(Meeting.scheduled_at)
        )
        return [
            {
                "id": m.id,
                "title": m.title,
                "status": m.status,
                "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                "kind": m.kind,
            }
            for m in meetings.scalars().all()
        ]

    async def _get_customer_communication(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        from app.models.communication import CanonicalCommunicationThread
        # Find threads linked to customer via contacts or projects
        contacts = await db.execute(
            select(CustomerContact).where(
                CustomerContact.organization_id == caller.organization_id,
                CustomerContact.customer_id == customer_id,
            )
        )
        contact_ids = [c.id for c in contacts.scalars().all()]

        threads = await db.execute(
            select(CanonicalCommunicationThread).where(
                CanonicalCommunicationThread.organization_id == caller.organization_id,
                CanonicalCommunicationThread.status == "active",
            ).limit(20)
        )
        return [
            {
                "id": t.id,
                "title": t.title,
                "kind": t.kind,
                "status": t.state,
            }
            for t in threads.scalars().all()
        ]

    async def _get_customer_outcomes(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        # CustomerOutcomeModel from customer_intelligence
        cc_outcomes = await db.execute(
            select(CustomerOutcomeModel).where(
                CustomerOutcomeModel.organization_id == caller.organization_id,
                CustomerOutcomeModel.customer_id == customer_id,
            ).order_by(desc(CustomerOutcomeModel.recorded_at)).limit(20)
        )

        # BusinessOutcome from business_commercial
        from app.models.business_commercial import BusinessOutcome
        bo_outcomes = await db.execute(
            select(BusinessOutcome).where(
                BusinessOutcome.organization_id == caller.organization_id,
                BusinessOutcome.customer_id == customer_id,
            ).order_by(desc(BusinessOutcome.projected_at)).limit(20)
        )

        outcomes = []
        for o in cc_outcomes.scalars().all():
            outcomes.append({
                "id": o.id,
                "type": "customer_outcome",
                "metric_kind": o.metric_kind,
                "baseline": o.baseline,
                "target": o.target,
                "actual": o.actual,
                "unit": o.unit,
                "recorded_at": o.recorded_at.isoformat() if o.recorded_at else None,
            })

        for o in bo_outcomes.scalars().all():
            outcomes.append({
                "id": o.id,
                "type": "business_outcome",
                "kind": o.kind,
                "title": o.title,
                "state": o.state,
                "metric_kind": o.metric_kind,
                "target_value": o.target_value,
                "actual_value": o.actual_value,
                "revenue_impact": o.revenue_impact,
            })

        return outcomes

    async def _get_customer_predictions(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        # Get predictions from Gate 10
        pred_result = await predictive_intelligence_service.derive_predictions(
            db, caller=caller, scope_type="customer", scope_id=customer_id
        )
        predictions = pred_result if isinstance(pred_result, list) else pred_result.get("predictions", [])

        # Convert CompanyPrediction models to dicts if needed
        converted_predictions = []
        for p in predictions:
            if hasattr(p, '__dict__'):  # SQLAlchemy model
                converted_predictions.append({
                    "id": p.id,
                    "type": p.kind,
                    "title": p.title,
                    "probability": p.probability / 100.0 if p.probability > 1 else p.probability,
                    "confidence": p.confidence,
                    "horizon_days": p.horizon_days,
                    "basis": "predictive_intelligence",
                })
            else:
                converted_predictions.append(p)

        # Add customer-specific predictions
        from app.models.customer_intelligence import CustomerHealthRow
        health = await db.get(CustomerHealthRow, customer_id)
        if health and health.state in ("concerned", "at_risk"):
            converted_predictions.append({
                "type": "customer_health_risk",
                "title": f"Customer health is {health.state}",
                "probability": 0.7 if health.state == "at_risk" else 0.5,
                "confidence": 0.6,
                "horizon_days": 30,
                "basis": "customer_health",
            })

        return converted_predictions

    async def _get_customer_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        existing = await db.execute(
            select(CustomerRisk).where(
                CustomerRisk.organization_id == caller.organization_id,
                CustomerRisk.customer_id == customer_id,
                CustomerRisk.state.in_(("open", "acknowledged", "mitigating")),
            )
        )
        return existing.scalars().all()

    async def _get_customer_institutional_lessons(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[Dict[str, Any]]:
        # Get lessons related to this customer's projects/commitments
        links = await db.execute(
            select(CustomerProjectLink).where(
                CustomerProjectLink.organization_id == caller.organization_id,
                CustomerProjectLink.customer_id == customer_id,
            )
        )
        project_ids = [l.project_id for l in links.scalars().all()]

        lessons = []
        if project_ids:
            for pid in project_ids:
                result = await db.execute(
                    select(OrganizationalLearning).where(
                        OrganizationalLearning.organization_id == caller.organization_id,
                        OrganizationalLearning.lifecycle.in_(("supported", "authoritative", "confirmed")),
                        OrganizationalLearning.evidence_json.contains(f'"project_ids": [{pid}]'),
                    ).limit(5)
                )
                for l in result.scalars().all():
                    lessons.append({
                        "id": l.id,
                        "kind": l.kind,
                        "title": l.title,
                        "lesson": l.lesson,
                        "confidence": l.confidence,
                        "lifecycle": l.lifecycle,
                    })

        return lessons[:10]

    async def _assess_customer_capacity(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> tuple[str, Optional[float]]:
        """Assess capacity health for customer commitments."""
        # Get responsible people for customer projects
        people = await self._get_customer_responsible_people(db, caller, customer_id)
        if not people:
            return "healthy", None

        # Check capacity for each person
        from app.intelligence.organizational_capacity_service import organizational_capacity_service
        overloaded = 0
        total = 0
        for p in people:
            total += 1
            cap = await organizational_capacity_service.derive_capacity_context(
                db, caller=caller, scope_type="person", scope_id=p["id"]
            )
            if cap.capacity_state in ("overloaded", "critical"):
                overloaded += 1

        if overloaded == 0:
            return "healthy", None
        elif overloaded <= total * 0.3:
            return "concerned", overloaded / max(1, total)
        else:
            return "at_risk", overloaded / max(1, total)

    def _assess_overall_risk(self, risks: List[CustomerRisk]) -> tuple[str, int]:
        if not risks:
            return "low", 0

        critical = sum(1 for r in risks if r.level == "critical")
        high = sum(1 for r in risks if r.level == "high")

        if critical > 0:
            return "critical", len(risks)
        elif high > 0:
            return "high", len(risks)
        elif len(risks) >= 3:
            return "medium", len(risks)
        else:
            return "low", len(risks)

    def _project_customer_financials(
        self,
        commitments: List[Dict[str, Any]],
        commercial_intents: List[Dict[str, Any]],
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        revenue = sum(c.get("estimated_value", 0) or 0 for c in commercial_intents if c.get("estimated_value"))
        revenue += sum(c.get("expected_value", 0) or 0 for c in commercial_intents if c.get("expected_value"))

        # Simple projection
        cost = revenue * 0.6 if revenue else 0
        margin = revenue - cost if revenue else None

        return revenue if revenue else None, cost if cost else None, margin

    # ================================================================
    # IMPACT PROPAGATION
    # ================================================================

    async def _propagate_impact_to_customer(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        customer_id: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_type: str,
    ) -> Dict[str, Any]:
        """Use Gate 13 strategic alignment to propagate impact to customer."""

        # Get customer commitments
        commitments = await self._get_customer_commitments(db, caller, customer_id)
        commitment_ids = [c["id"] for c in commitments]

        # Trace from trigger to commitments using Gate 13
        affected_commitments = []
        affected_projects = []
        affected_objectives = []
        affected_people = []
        affected_capacity = []

        if commitment_ids:
            # Trace forward from trigger to commitments
            trace = await strategic_alignment_engine.trace_forward(
                db, caller=caller,
                entity_type=trigger_entity_type,
                entity_id=trigger_entity_id,
                max_depth=self.MAX_TRAVERSAL_DEPTH,
            )

            # Filter trace for customer-related entities
            for item in trace.get("chain", []):
                target = item.get("target", {})
                if target.get("type") == "commitment" and target.get("id") in commitment_ids:
                    affected_commitments.append({
                        "commitment_id": target["id"],
                        "alignment_type": item["alignment_type"],
                        "strength": item["strength"],
                        "impact": trigger_type,
                    })
                elif target.get("type") == "project":
                    affected_projects.append({
                        "project_id": target["id"],
                        "impact": item["alignment_type"],
                    })
                elif target.get("type") == "objective":
                    affected_objectives.append({
                        "objective_id": target["id"],
                        "impact": item["alignment_type"],
                    })
                elif target.get("type") == "person":
                    affected_people.append({
                        "person_id": target["id"],
                        "impact": item["alignment_type"],
                    })

        # Get affected capacity (people involved)
        people = await self._get_customer_responsible_people(
            db, caller, customer_id
        )
        for p in people:
            from app.intelligence.organizational_capacity_service import organizational_capacity_service
            cap = await organizational_capacity_service.derive_capacity_context(
                db, caller=caller, scope_type="person", scope_id=p["id"]
            )
            if cap.capacity_state != "healthy":
                affected_capacity.append({
                    "person_id": p["id"],
                    "capacity_state": cap.capacity_state,
                    "utilization": cap.utilization,
                })

        return {
            "trigger_type": trigger_type,
            "trigger_entity_type": trigger_entity_type,
            "trigger_entity_id": trigger_entity_id,
            "affected_commitments": affected_commitments,
            "affected_projects": affected_projects,
            "affected_objectives": affected_objectives,
            "affected_people": affected_people,
            "affected_capacity": affected_capacity,
        }

    async def _assess_customer_outcome_impact(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        customer_id: str,
        impact: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assess impact on customer outcomes and business value."""

        # Get commercial intents
        intents = await self._get_customer_commercial_intents(db, caller, customer_id)

        # Get business outcomes
        from app.models.business_commercial import BusinessOutcome
        outcomes = await db.execute(
            select(BusinessOutcome).where(
                BusinessOutcome.organization_id == caller.organization_id,
                BusinessOutcome.customer_id == customer_id,
            )
        )
        outcomes_list = outcomes.scalars().all()

        # Simple assessment
        at_risk_commitments = len([c for c in impact.get("affected_commitments", []) if c.get("impact") == "delay"])
        at_risk_projects = len(impact.get("affected_projects", []))

        revenue_impact = 0.0
        for intent in intents:
            if intent.get("probability", 50) < 50:
                revenue_impact -= intent.get("estimated_value", 0) or 0

        margin_impact = revenue_impact * 0.3 if revenue_impact else 0
        relationship_risk = min(1.0, (at_risk_commitments + at_risk_projects) * 0.1)

        return {
            "revenue_impact": revenue_impact,
            "margin_impact": margin_impact,
            "relationship_risk_change": relationship_risk,
            "at_risk_commitments": at_risk_commitments,
            "at_risk_projects": at_risk_projects,
        }

    async def _assess_impact_risks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        impact: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assess risks from impact analysis."""
        new_risks = []
        escalated_risks = []

        for commit in impact.get("affected_commitments", []):
            if commit.get("impact") == "delay":
                new_risks.append({
                    "kind": "delivery",
                    "level": "high",
                    "title": f"Commitment {commit['commitment_id']} at risk due to upstream delay",
                    "commitment_id": commit["commitment_id"],
                })

        for proj in impact.get("affected_projects", []):
            new_risks.append({
                "kind": "delivery",
                "level": "medium",
                "title": f"Project {proj['project_id']} impacted by upstream change",
                "project_id": proj["project_id"],
            })

        return {
            "new_risks": new_risks,
            "escalated_risks": escalated_risks,
        }

    async def _get_relevant_scenarios(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        customer_id: str,
        impact: Dict[str, Any],
    ) -> List[str]:
        """Find relevant counterfactual scenarios."""
        history = await counterfactual_intelligence_service.get_scenario_history(
            db, caller=caller, scope_type="project", scope_id=impact.get("trigger_entity_id"), limit=10
        )
        return [s.get("scenario_id") for s in history if s.get("scenario_id")]

    # ================================================================
    # RISK DERIVATION HELPERS
    # ================================================================

    async def _derive_health_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        from app.models.customer_intelligence import CustomerHealthRow
        health_result = await db.execute(
            select(CustomerHealthRow).where(
                CustomerHealthRow.organization_id == caller.organization_id,
                CustomerHealthRow.customer_id == customer_id,
            )
        )
        health = health_result.scalars().first()

        if not health or health.state == "healthy":
            return []

        risk = CustomerRisk(
            organization_id=caller.organization_id,
            customer_id=customer_id,
            kind="relationship",
            level="high" if health.state == "at_risk" else "medium",
            title=f"Customer health is {health.state}",
            description=f"Customer health score: {health.score}. Reasons: {', '.join(health.reasons_json or [])}",
            root_cause="; ".join(health.reasons_json or []),
            probability=0.8 if health.state == "at_risk" else 0.5,
            impact_score=80 if health.state == "at_risk" else 50,
            epistemic_status="measured" if health.state == "at_risk" else "evidence_backed",
            evidence_fingerprints=[f"health-{health.id}"],
            source_event_id=f"health-{health.id}",
            derived_from_customer_health=True,
            fingerprint=hashlib.sha256(f"health-risk-{customer_id}-{health.id}".encode()).hexdigest()[:64],
        )
        return [risk]

    async def _derive_commitment_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        commitments = await self._get_customer_commitments(db, caller, customer_id)
        risks = []

        for c in commitments:
            if c.get("status") == "at_risk":
                risk = CustomerRisk(
                    organization_id=caller.organization_id,
                    customer_id=customer_id,
                    commitment_id=c["id"],
                    kind="delivery",
                    level="high",
                    title=f"Commitment at risk: {c.get('summary', c.get('title', c['id']))}",
                    description=f"Customer commitment {c['id']} is at risk",
                    probability=0.7,
                    impact_score=70,
                    epistemic_status="observed",
                    evidence_fingerprints=[f"commitment-{c['id']}"],
                    source_event_id=f"commitment-risk-{c['id']}",
                    fingerprint=hashlib.sha256(f"commitment-risk-{customer_id}-{c['id']}".encode()).hexdigest()[:64],
                )
                risks.append(risk)

        return risks

    async def _derive_capacity_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        people = await self._get_customer_responsible_people(db, caller, customer_id)
        if not people:
            return []

        from app.intelligence.organizational_capacity_service import organizational_capacity_service
        risks = []

        for p in people:
            cap = await organizational_capacity_service.derive_capacity_context(
                db, caller=caller, scope_type="person", scope_id=p["id"]
            )
            if cap.capacity_state in ("overloaded", "critical"):
                risk = CustomerRisk(
                    organization_id=caller.organization_id,
                    customer_id=test_customer.id,
                    kind="capacity",
                    level="critical",
                    title=f"Critical capacity deficit for {p['name']} threatens customer delivery",
                    description=f"Person {p['name']} is {cap.capacity_state} (utilization: {cap.utilization:.0%})",
                    root_cause="Overcommitment relative to capacity",
                    causal_chain=[
                        {"type": "person", "id": p["id"], "label": p["name"], "impact": "capacity_deficit"},
                        {"type": "customer", "id": customer_id, "label": "customer delivery", "impact": "at_risk"},
                    ],
                    probability=0.9,
                    impact_score=85,
                    epistemic_status="observed",
                    evidence_fingerprints=[f"capacity-{p['id']}"],
                    source_event_id=f"capacity-{p['id']}",
                    fingerprint=hashlib.sha256(f"capacity-risk-{customer_id}-{p['id']}".encode()).hexdigest()[:64],
                )
                risks.append(risk)

        return risks

    async def _derive_dependency_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        deps = await self._get_customer_dependencies(db, caller, customer_id)
        blocked = [d for d in deps if d.get("kind") == "blocks"]

        if not blocked:
            return []

        risk = CustomerRisk(
            organization_id=caller.organization_id,
            customer_id=customer_id,
            kind="dependency",
            level="medium",
            title=f"{len(blocked)} blocking dependencies threaten customer delivery",
            description=f"Customer {customer_id} has {len(blocked)} blocking task dependencies",
            causal_chain=[
                {"type": "task", "label": "blocked dependencies", "impact": "blocks_execution"},
                {"type": "project", "label": "customer project", "impact": "delayed"},
                {"type": "customer", "id": customer_id, "label": "customer delivery", "impact": "at_risk"},
            ],
            probability=0.6,
            impact_score=60,
            epistemic_status="observed",
            evidence_fingerprints=[f"dep-{d['id']}" for d in blocked[:5]],
            source_event_id=f"dependency-risk-{customer_id}",
            fingerprint=hashlib.sha256(f"dependency-risk-{customer_id}".encode()).hexdigest()[:64],
        )
        return [risk]

    async def _derive_prediction_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        pred_result = await predictive_intelligence_service.derive_predictions(
            db, caller=caller, scope_type="customer", scope_id=customer_id
        )
        predictions = pred_result if isinstance(pred_result, list) else pred_result.get("predictions", [])

        risks = []
        for p in predictions:
            if p.get("probability", 0) > 0.6 and p.get("type") in ("commitment_risk", "customer_churn", "delivery_delay"):
                risk = CustomerRisk(
                    organization_id=caller.organization_id,
                    customer_id=customer_id,
                    kind="delivery" if p.get("type") != "customer_churn" else "churn",
                    level="high" if p.get("probability", 0) > 0.8 else "medium",
                    title=f"Predicted risk: {p.get('title', 'Elevated risk')}",
                    description=p.get("detail", "Predicted risk from predictive intelligence"),
                    probability=p.get("probability", 0.6),
                    impact_score=70,
                    epistemic_status="predicted",
                    prediction_ids=[p.get("id", "")],
                    source_event_id=f"prediction-{p.get('id', 'unknown')}",
                    fingerprint=hashlib.sha256(f"prediction-risk-{customer_id}-{p.get('id','')}".encode()).hexdigest()[:64],
                )
                risks.append(risk)

        return risks

    async def _derive_counterfactual_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        history = await counterfactual_intelligence_service.get_scenario_history(
            db, caller=caller, scope_type="project", scope_id=None, limit=20
        )

        risks = []
        for s in history:
            consequences = s.get("consequences", {})
            if consequences.get("risks_already_present"):
                risk = CustomerRisk(
                    organization_id=caller.organization_id,
                    customer_id=customer_id,
                    kind="delivery",
                    level="medium",
                    title=f"Counterfactual risk: {s.get('hypothetical_change', {}).get('scenario_kind', 'scenario')}",
                    description="Counterfactual scenario indicates elevated risk",
                    probability=0.5,
                    impact_score=50,
                    epistemic_status="counterfactual",
                    counterfactual_ids=[s.get("scenario_id")],
                    source_event_id=f"counterfactual-{s.get('scenario_id')}",
                    fingerprint=hashlib.sha256(f"counterfactual-risk-{customer_id}-{s.get('scenario_id')}".encode()).hexdigest()[:64],
                )
                risks.append(risk)

        return risks

    async def _derive_financial_risks(
        self, db: AsyncSession, caller: CallerAccess, customer_id: str
    ) -> List[CustomerRisk]:
        from app.models.finance import Invoice
        from datetime import date, timedelta

        overdue = await db.execute(
            select(Invoice).where(
                Invoice.organization_id == caller.organization_id,
                Invoice.customer_id == customer_id,
                Invoice.direction == "receivable",
                Invoice.due_at < date.today(),
                Invoice.status.in_(("sent", "overdue", "partial")),
            )
        )

        if not overdue.scalars().all():
            return []

        risk = CustomerRisk(
            organization_id=caller.organization_id,
            customer_id=customer_id,
            kind="financial",
            level="high",
            title=f"{len(overdue.scalars().all())} overdue invoices for customer",
            description="Customer has overdue receivables affecting cash flow",
            probability=0.8,
            impact_score=60,
            revenue_at_risk=sum(i.amount for i in overdue.scalars().all()),
            epistemic_status="observed",
            evidence_fingerprints=[f"invoice-{i.id}" for i in overdue.scalars().all()],
            source_event_id=f"financial-risk-{customer_id}",
            fingerprint=hashlib.sha256(f"financial-risk-{customer_id}".encode()).hexdigest()[:64],
        )
        return [risk]

    # ================================================================
    # CONTEXT FILTERING
    # ================================================================

    async def _filter_context_for_role(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        slice_obj: CustomerOperatingSlice,
        role_type: str,
        actor_person_id: Optional[str],
    ) -> Dict[str, Any]:
        """Filter operating slice based on role."""
        context = {}

        if role_type == "account_manager":
            context["attention_items"] = [
                a for a in slice_obj.attention_items or []
                if a.get("type") in ("commitment_risk", "meeting_overdue", "task_blocked")
            ][:10]
            context["commitments"] = slice_obj.commitments[:20]
            context["upcoming_meetings"] = slice_obj.meetings[:10]
            context["risks"] = [self._risk_to_dict(r) for r in slice_obj.risks if r.get("level") in ("high", "critical")][:10]

        elif role_type == "manager":
            context["attention_items"] = slice_obj.attention_items[:15]
            context["commitments"] = slice_obj.commitments
            context["capacity_alerts"] = slice_obj.capacity_alerts if hasattr(slice_obj, "capacity_alerts") else []

        elif role_type == "executive":
            context["attention_items"] = [
                a for a in slice_obj.attention_items or []
                if a.get("severity") in ("high", "critical")
            ][:5]
            context["opportunities"] = slice_obj.commercial_intents[:10]
            context["risks"] = [self._risk_to_dict(r) for r in slice_obj.risks if r.get("level") in ("critical", "high")][:5]

        elif role_type == "finance":
            context["commitments"] = [
                c for c in slice_obj.commitments
                if c.get("type") == "customer_commitment"
            ][:20]
            context["opportunities"] = slice_obj.commercial_intents

        elif role_type == "delivery_lead":
            context["commitments"] = slice_obj.commitments
            context["tasks"] = slice_obj.tasks
            context["dependencies"] = slice_obj.dependencies
            context["capacity_alerts"] = slice_obj.capacity_alerts if hasattr(slice_obj, "capacity_alerts") else []

        else:
            # Default
            context["commitments"] = slice_obj.commitments[:10]
            context["risks"] = [self._risk_to_dict(r) for r in slice_obj.risks][:10]

        return context

    def _risk_to_dict(self, risk: CustomerRisk) -> Dict[str, Any]:
        return {
            "id": risk.id,
            "kind": risk.kind,
            "level": risk.level,
            "title": risk.title,
            "description": risk.description,
            "probability": risk.probability,
            "impact_score": risk.impact_score,
            "epistemic_status": risk.epistemic_status,
        }

    def _business_need_to_dict(self, bn: BusinessNeed) -> Dict[str, Any]:
        return {
            "id": bn.id,
            "kind": bn.kind,
            "title": bn.title,
            "state": bn.state,
            "confidence": bn.confidence,
            "estimated_value": bn.estimated_value,
            "customer_id": bn.customer_id,
            "intent_id": bn.intent_id,
        }


# Global instance
customer_operating_fabric_service = CustomerOperatingFabricService()