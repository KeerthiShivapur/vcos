"""Canonical Financial + Resource + Procurement Operating Fabric Service — Gate 15.

Derives financial/resource/procurement operating slices, impact analyses, and contexts
from the canonical company reality (Gates 8-14).

This is a DERIVED PROJECTION layer — it does NOT create a second financial/resource reality.
All data is composed from existing canonical primitives:
- Gate 8: People, Work, Communication, Meetings, Organizational Intelligence, Capacity
- Gate 9: Institutional Learning
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
"""

import hashlib
import json
import logging
import time
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Set

import sqlalchemy
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.organization import TimestampMixin, gen_uuid
from app.models.financial_resource_procurement import (
    ResourceRequirement,
    ResourceAllocationRecord,
    ProcurementRecord,
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
    FinancialOperatingSlice,
    FinancialImpactAnalysis,
)
from app.models.finance import (
    Budget,
    BudgetAllocation,
    Expense,
    Invoice,
    Payment,
    PurchaseRequest,
    PurchaseOrder,
    Vendor,
)
from app.models.customer import (
    Customer,
    CustomerProjectLink,
)
from app.models.lead import Opportunity
from app.models.project import Project
from app.models.customer_intelligence import (
    CustomerCommitment,
    CustomerHealthRow,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    OrganizationalResponsibility,
)
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
from app.intelligence.customer_operating_fabric_service import (
    customer_operating_fabric_service,
)

logger = logging.getLogger("vcos.intelligence.financial_resource_procurement")


class FinancialResourceProcurementService:
    """
    Service for deriving the canonical financial/resource/procurement operating fabric.
    
    All methods return DERIVED PROJECTIONS over canonical reality.
    They do NOT mutate canonical data.
    """

    # Maximum depth for traversal
    MAX_TRAVERSAL_DEPTH = 5

    def __init__(self):
        pass

    # ================================================================
    # 1. FINANCIAL OPERATING SLICE
    # ================================================================

    async def derive_financial_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> FinancialOperatingSlice:
        """
        Derive a governed, point-in-time financial operating slice for the organization.
        
        Composes all canonical financial reality:
        - Budgets, allocations, expenses, invoices, payments
        - Procurements, resource allocations, requirements
        - Financial outcomes
        """
        start = time.perf_counter()

        # Governance: verify org-wide access
        if not caller.org_wide:
            raise ValueError("Financial operating slice requires org-wide access")

        # Build input fingerprint for exact-once
        input_data = {
            "organization_id": caller.organization_id,
            "scope": "financial_operating_slice",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]

        # Check for existing slice with same fingerprint
        existing = await db.execute(
            select(FinancialOperatingSlice).where(
                FinancialOperatingSlice.organization_id == caller.organization_id,
                FinancialOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing

        # 1. Budgets
        budgets = await self._get_budgets(db, caller)

        # 2. Budget Commitments
        budget_commitments = await self._get_budget_commitments(db, caller)

        # 3. Expenses
        expenses = await self._get_expenses(db, caller)

        # 4. Invoices
        invoices = await self._get_invoices(db, caller)

        # 5. Payments
        payments = await self._get_payments(db, caller)

        # 6. Procurements
        procurements = await self._get_procurements(db, caller)

        # 6. Resource Allocations (from Gate 8.6/4G.4)
        resource_allocations = await self._get_resource_allocations(db, caller)

        # 7. Resource Requirements (from Gate 15)
        resource_requirements = await self._get_resource_requirements(db, caller)

        # 8. Financial Outcomes (from Gate 15)
        financial_outcomes = await self._get_financial_outcomes(db, caller)

        # Summary metrics
        total_budgeted = sum(b.get("allocated_amount", 0) for b in budgets)
        total_spent = sum(e.get("amount", 0) for e in expenses)
        total_committed = sum(bc.committed_amount for bc in await self._get_budget_commitment_records(db, caller))
        total_available = max(0, total_budgeted - total_spent - total_committed)
        budget_utilization = (total_spent / total_budgeted * 100) if total_budgeted > 0 else 0

        # Procurement
        pending_procurements = sum(1 for p in procurements if p.get("state") in ("requested", "quoted", "approved"))
        overdue_procurements = sum(1 for p in procurements if p.get("state") == "overdue")
        procurement_risk_score = overdue_procurements / max(1, len(procurements)) * 100 if procurements else 0

        # Financial projections
        projected_revenue = sum(fo.get("revenue_impact", 0) for fo in financial_outcomes if fo.get("revenue_impact"))
        projected_cost = sum(fo.get("cost_impact", 0) for fo in financial_outcomes if fo.get("cost_impact"))
        projected_margin = projected_revenue - projected_cost if projected_revenue and projected_cost else None

# Build slice
        slice_id = gen_uuid()
        computed_at = utcnow()
        slice_obj = FinancialOperatingSlice(
            id=slice_id,
            organization_id=caller.organization_id,
            input_fingerprint=input_fingerprint,
            budgets=budgets,
            budget_commitments=budget_commitments,
            expenses=expenses,
            invoices=invoices,
            payments=payments,
            procurements=procurements,
            resource_allocations=resource_allocations,
            resource_requirements=resource_requirements,
            financial_outcomes=financial_outcomes,
            total_budgeted=total_budgeted,
            total_spent=total_spent,
            total_committed=total_committed,
            total_available=total_available,
            budget_utilization=budget_utilization,
            pending_procurements=pending_procurements,
            overdue_procurements=overdue_procurements,
            procurement_risk_score=procurement_risk_score,
            projected_revenue=projected_revenue,
            projected_cost=projected_cost,
            projected_margin=projected_margin,
            computed_at=computed_at,
            computation_duration_ms=int((time.perf_counter() - start) * 1000),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "organization_id": caller.organization_id,
                    "budget_count": len(budgets),
                    "expense_count": len(expenses),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
            created_at=computed_at,
            updated_at=computed_at,
        )

        db.add(slice_obj)
        try:
            await db.flush()
            return slice_obj
        except BaseException as e:
            # Check if it's an integrity error (race condition)
            is_integrity_error = (
                isinstance(e, sqlalchemy.exc.IntegrityError) or
                (hasattr(e, '__class__') and e.__class__.__name__ == 'IntegrityError') or
                'integrity' in str(e).lower() or
                'unique' in str(e).lower() or
                'duplicate' in str(e).lower()
            )
            if is_integrity_error:
                # Handle race condition: another session already created this slice
                await db.rollback()
                # Query in a new transaction to get the existing slice
                existing = await db.execute(
                    select(FinancialOperatingSlice).where(
                        FinancialOperatingSlice.organization_id == caller.organization_id,
                        FinancialOperatingSlice.input_fingerprint == input_fingerprint,
                    )
                )
                existing = existing.scalars().first()
                if existing:
                    return existing
                # If still not found (unlikely), re-raise
                raise
            # Re-raise other exceptions
            raise

    # ================================================================
    # 2. FINANCIAL IMPACT ANALYSIS
    # ================================================================

    async def analyze_financial_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        trigger_type: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_params: Optional[Dict[str, Any]] = None,
    ) -> FinancialImpactAnalysis:
        """
        Analyze the cross-domain financial impact of a change.
        
        Uses Gate 13 Strategic Alignment for propagation.
        """
        trigger_params = trigger_params or {}

        # Build input fingerprint for exact-once
        input_data = {
            "trigger_type": trigger_type,
            "trigger_entity_type": trigger_entity_type,
            "trigger_entity_id": trigger_entity_id,
            "trigger_params": trigger_params,
            "organization_id": caller.organization_id,
        }
        fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]

        # Check existing
        existing = await db.execute(
            select(FinancialImpactAnalysis).where(
                FinancialImpactAnalysis.organization_id == caller.organization_id,
                FinancialImpactAnalysis.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing

        # Use Gate 13 strategic alignment for propagation
        impact = await self._propagate_financial_impact(
            db, caller, trigger_entity_type, trigger_entity_id, trigger_type
        )

        # Assess financial outcome impact
        outcome_impact = await self._assess_financial_outcome_impact(
            db, caller, impact
        )

        # Financial impact
        revenue_impact = outcome_impact.get("revenue_impact")
        cost_impact = outcome_impact.get("cost_impact")
        margin_impact = outcome_impact.get("margin_impact")
        cash_flow_impact = outcome_impact.get("cash_flow_impact")

        # Risk assessment
        risk_assessment = await self._assess_financial_impact_risks(db, caller, impact)
        new_risks = risk_assessment.get("new_risks", [])
        escalated_risks = risk_assessment.get("escalated_risks", [])

        # Find relevant counterfactual scenarios
        scenarios = await self._get_relevant_scenarios(db, caller, impact)

        # Use raw SQL INSERT with ON CONFLICT DO NOTHING for exact-once
        from sqlalchemy import text
        import uuid as uuid_module
        analysis_id = uuid_module.uuid4().hex[:32]
        insert_sql = text("""
            INSERT INTO financial_impact_analyses (
                id, organization_id, trigger_type, trigger_entity_type, trigger_entity_id,
                trigger_params, affected_budgets, affected_commitments, affected_projects,
                affected_objectives, affected_people, affected_capacity, affected_procurements,
                budget_impact, revenue_impact, cost_impact, margin_impact, cash_flow_impact,
                risk_assessment, new_risks, escalated_risks, scenario_ids, confidence,
                analyzed_at, source_event_id, fingerprint, version, created_at, updated_at
            ) VALUES (
                :id, :organization_id, :trigger_type, :trigger_entity_type, :trigger_entity_id,
                :trigger_params, :affected_budgets, :affected_commitments, :affected_projects,
                :affected_objectives, :affected_people, :affected_capacity, :affected_procurements,
                :budget_impact, :revenue_impact, :cost_impact, :margin_impact, :cash_flow_impact,
                :risk_assessment, :new_risks, :escalated_risks, :scenario_ids, :confidence,
                :analyzed_at, :source_event_id, :fingerprint, :version, :created_at, :updated_at
            )
            ON CONFLICT (organization_id, fingerprint) DO NOTHING
        """)

        now = utcnow()
        await db.execute(insert_sql, {
            "id": analysis_id,
            "organization_id": caller.organization_id,
            "trigger_type": trigger_type,
            "trigger_entity_type": trigger_entity_type,
            "trigger_entity_id": trigger_entity_id,
            "trigger_params": json.dumps(trigger_params or {}),
            "affected_budgets": json.dumps(impact.get("affected_budgets", [])),
            "affected_commitments": json.dumps(impact.get("affected_commitments", [])),
            "affected_projects": json.dumps(impact.get("affected_projects", [])),
            "affected_objectives": json.dumps(impact.get("affected_objectives", [])),
            "affected_people": json.dumps(impact.get("affected_people", [])),
            "affected_capacity": json.dumps(impact.get("affected_capacity", [])),
            "affected_procurements": json.dumps(impact.get("affected_procurements", [])),
            "budget_impact": json.dumps(impact.get("budget_impact", {})),
            "revenue_impact": revenue_impact,
            "cost_impact": cost_impact,
            "margin_impact": margin_impact,
            "cash_flow_impact": cash_flow_impact,
            "risk_assessment": json.dumps(risk_assessment),
            "new_risks": json.dumps(new_risks),
            "escalated_risks": json.dumps(escalated_risks),
            "scenario_ids": json.dumps(scenarios),
            "confidence": 0.6,
            "analyzed_at": now,
            "source_event_id": input_data.get("source_event_id"),
            "fingerprint": fingerprint,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        })
        await db.flush()

        # Query for the existing or newly inserted analysis
        existing = await db.execute(
            select(FinancialImpactAnalysis).where(
                FinancialImpactAnalysis.organization_id == caller.organization_id,
                FinancialImpactAnalysis.fingerprint == fingerprint,
            )
        )
        return existing.scalars().first()

    # ================================================================
    # HELPER METHODS
    # ================================================================

    async def _get_budgets(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Budget).where(
                Budget.organization_id == caller.organization_id,
            ).order_by(desc(Budget.fiscal_year))
        )
        return [
            {
                "id": b.id,
                "name": b.name,
                "budget_type": b.budget_type,
                "status": b.status,
                "fiscal_year": b.fiscal_year,
                "allocated_amount": b.allocated_amount,
                "used_amount": b.used_amount,
                "remaining_amount": b.remaining_amount,
                "currency": b.currency,
                "department_id": b.department_id,
                "project_id": b.project_id,
            }
            for b in result.scalars().all()
        ]

    async def _get_budget_commitments(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(BudgetCommitmentRecord).where(
                BudgetCommitmentRecord.organization_id == caller.organization_id,
            )
        )
        return [
            {
                "id": bc.id,
                "budget_id": bc.budget_id,
                "commitment_id": bc.commitment_id,
                "committed_amount": bc.committed_amount,
                "spent_amount": bc.spent_amount,
                "currency": bc.currency,
            }
            for bc in result.scalars().all()
        ]

    async def _get_budget_commitment_records(self, db: AsyncSession, caller: CallerAccess):
        result = await db.execute(
            select(BudgetCommitmentRecord).where(
                BudgetCommitmentRecord.organization_id == caller.organization_id,
            )
        )
        return result.scalars().all()

    async def _get_expenses(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Expense).where(
                Expense.organization_id == caller.organization_id,
            ).order_by(desc(Expense.incurred_at)).limit(100)
        )
        return [
            {
                "id": e.id,
                "expense_type": e.expense_type,
                "amount": e.amount,
                "currency": e.currency,
                "incurred_at": e.incurred_at.isoformat() if e.incurred_at else None,
                "merchant": e.merchant,
                "project_id": e.project_id,
                "status": e.status,
            }
            for e in result.scalars().all()
        ]

    async def _get_invoices(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Invoice).where(
                Invoice.organization_id == caller.organization_id,
            ).order_by(desc(Invoice.issued_at)).limit(100)
        )
        return [
            {
                "id": i.id,
                "direction": i.direction,
                "title": i.title,
                "amount": i.amount,
                "tax_amount": i.tax_amount,
                "currency": i.currency,
                "issued_at": i.issued_at.isoformat() if i.issued_at else None,
                "due_at": i.due_at.isoformat() if i.due_at else None,
                "status": i.status,
                "vendor_id": i.vendor_id,
                "customer_id": i.customer_id,
            }
            for i in result.scalars().all()
        ]

    async def _get_payments(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Payment).where(
                Payment.organization_id == caller.organization_id,
            ).order_by(desc(Payment.paid_at)).limit(100)
        )
        return [
            {
                "id": p.id,
                "invoice_id": p.invoice_id,
                "amount": p.amount,
                "currency": p.currency,
                "status": p.status,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in result.scalars().all()
        ]

    async def _get_procurements(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(ProcurementRecord).where(
                ProcurementRecord.organization_id == caller.organization_id,
            ).order_by(desc(ProcurementRecord.created_at)).limit(100)
        )
        return [
            {
                "id": p.id,
                "kind": p.kind,
                "title": p.title,
                "state": p.state,
                "estimated_cost": p.estimated_cost,
                "actual_cost": p.actual_cost,
                "currency": p.currency,
                "vendor_id": p.vendor_id,
                "expected_delivery": p.expected_delivery.isoformat() if p.expected_delivery else None,
                "delivered_at": p.delivered_at.isoformat() if p.delivered_at else None,
            }
            for p in result.scalars().all()
        ]

    async def _get_resource_allocations(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(CapacityAllocation).where(
                CapacityAllocation.organization_id == caller.organization_id,
            ).limit(100)
        )
        return [
            {
                "id": ca.id,
                "project_id": ca.project_id,
                "capability": ca.capability,
                "units": ca.units,
                "window_start": ca.window_start.isoformat() if ca.window_start else None,
                "window_end": ca.window_end.isoformat() if ca.window_end else None,
                "status": ca.status,
            }
            for ca in result.scalars().all()
        ]

    async def _get_resource_requirements(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(ResourceRequirement).where(
                ResourceRequirement.organization_id == caller.organization_id,
            ).limit(100)
        )
        return [
            {
                "id": rr.id,
                "resource_kind": rr.resource_kind,
                "quantity": rr.quantity,
                "unit": rr.unit,
                "state": rr.state,
                "commitment_id": rr.commitment_id,
            }
            for r in result.scalars().all()
        ]

    async def _get_financial_outcomes(self, db: AsyncSession, caller: CallerAccess) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(FinancialOutcomeRecord).where(
                FinancialOutcomeRecord.organization_id == caller.organization_id,
            ).order_by(desc(FinancialOutcomeRecord.projected_at)).limit(100)
        )
        return [
            {
                "id": fo.id,
                "kind": fo.kind,
                "title": fo.title,
                "state": fo.state,
                "target_value": fo.target_value,
                "actual_value": fo.actual_value,
                "revenue_impact": fo.revenue_impact,
                "cost_impact": fo.cost_impact,
                "margin_impact": fo.margin_impact,
            }
            for fo in result.scalars().all()
        ]

    async def _propagate_financial_impact(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_type: str,
    ) -> Dict[str, Any]:
        """Use Gate 13 strategic alignment to propagate financial impact."""
        
        # Trace forward from trigger to affected entities
        trace = await strategic_alignment_engine.trace_forward(
            db, caller=caller,
            entity_type=trigger_entity_type,
            entity_id=trigger_entity_id,
            max_depth=5,
        )

        affected_budgets = []
        affected_commitments = []
        affected_projects = []
        affected_objectives = []
        affected_people = []
        affected_capacity = []
        affected_procurements = []

        for item in trace.get("chain", []):
            target = item.get("target", {})
            if target.get("type") == "budget":
                affected_budgets.append({
                    "budget_id": target["id"],
                    "impact": item["alignment_type"],
                })
            elif target.get("type") == "commitment":
                affected_commitments.append({
                    "commitment_id": target["id"],
                    "impact": item["alignment_type"],
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

        # Get affected capacity
        from app.intelligence.organizational_capacity_service import organizational_capacity_service
        # (Would integrate with capacity service)

        return {
            "trigger_type": "financial_change",
            "trigger_entity_type": trigger_entity_type,
            "trigger_entity_id": trigger_entity_id,
            "affected_budgets": affected_budgets,
            "affected_commitments": affected_commitments,
            "affected_projects": affected_projects,
            "affected_objectives": affected_objectives,
            "affected_people": affected_people,
            "affected_capacity": affected_capacity,
            "affected_procurements": affected_procurements,
        }

    async def _assess_financial_outcome_impact(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        impact: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assess financial impact on outcomes."""
        
        # Get financial outcomes for affected commitments
        revenue_impact = 0.0
        cost_impact = 0.0

        for commit in impact.get("affected_commitments", []):
            # Would query financial outcomes linked to commitment
            pass

        return {
            "revenue_impact": revenue_impact,
            "cost_impact": cost_impact,
            "margin_impact": (revenue_impact or 0) - (cost_impact or 0),
            "cash_flow_impact": cost_impact * 0.5,  # Simplified
        }

    async def _assess_financial_impact_risks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        impact: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assess risks from financial impact."""
        new_risks = []
        escalated_risks = []

        for commit in impact.get("affected_commitments", []):
            new_risks.append({
                "kind": "financial",
                "level": "high",
                "title": f"Financial impact on commitment {commit.get('commitment_id')}",
            })

        return {
            "new_risks": new_risks,
            "escalated_risks": escalated_risks,
        }

    async def _get_relevant_scenarios(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        impact: Dict[str, Any],
    ) -> List[str]:
        history = await counterfactual_intelligence_service.get_scenario_history(
            db, caller=caller, scope_type="organization", limit=10
        )
        return [s.get("scenario_id") for s in history if s.get("scenario_id")]


# Global instance
financial_resource_procurement_service = FinancialResourceProcurementService()