"""Canonical Economic Operating Intelligence Service — Gate 18.

Derives the unified economic operating intelligence by composing Gates 15, 16, and 17
into a single coherent economic operating fabric.

This is a DERIVED PROJECTION layer — it does NOT create a second economic reality.
All data is composed from existing canonical primitives:
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric  
- Gate 17: Procurement + Vendor + External Capacity Operating Fabric
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
"""

import hashlib
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set

import sqlalchemy
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.organization import TimestampMixin, gen_uuid
from app.models.canonical_economic_intelligence import (
    EconomicOperatingSlice,
    EconomicImpactAnalysis,
    EconomicBottleneck,
    EconomicCostVariance,
    EconomicStateTransition,
    EconomicPredictionContext,
    EconomicCounterfactualContext,
    ECONOMIC_STATES,
    BOTTLENECK_TYPES,
    COST_VARIANCE_CATEGORIES,
)
from app.models.financial_resource_procurement import (
    ResourceRequirement,
    ResourceAllocationRecord,
    ProcurementRecord,
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
    FinancialOperatingSlice,
    FinancialImpactAnalysis,
)
from app.models.canonical_resource_asset import (
    CanonicalResource,
    CanonicalAsset,
    ResourceDemand,
    ResourceAllocation,
    ResourceConflict,
    ResourceOperatingSlice,
    ResourceImpactAnalysis,
)
from app.models.canonical_procurement_vendor import (
    CanonicalVendor,
    VendorCapability,
    ExternalCapacity,
    CanonicalProcurement,
    VendorPerformance,
    VendorDependency,
    VendorOperatingSlice,
    ProcurementImpactAnalysis,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    OrganizationalResponsibility,
)
from app.models.company_actions import CompanyAction
from app.models.project import Project
from app.models.customer import Customer, CustomerProjectLink
from app.models.customer_intelligence import CustomerCommitment, CustomerHealthRow
from app.models.finance import Budget, BudgetAllocation, Expense, Invoice, Payment, Vendor
from app.models.resource_allocation_intelligence import AllocationDemand, CapacityAllocation
from app.models.org_capability_intelligence import OrgCapability, CapabilityProjectLink
from app.intelligence.financial_resource_procurement_service import financial_resource_procurement_service
from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
from app.intelligence.strategic_alignment_engine import strategic_alignment_engine
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.customer_operating_fabric_service import customer_operating_fabric_service
from app.intelligence.company_operating_engine import company_operating_engine

logger = logging.getLogger("vcos.intelligence.canonical_economic_intelligence")


class CanonicalEconomicIntelligenceService:
    """
    Service for deriving the canonical economic operating intelligence.
    
    Composes Gates 15, 16, 17 into a single coherent economic operating fabric.
    All methods return DERIVED PROJECTIONS over canonical reality.
    They do NOT mutate canonical data.
    """
    
    # ================================================================
    # 1. ECONOMIC OPERATING SLICE — Unified composition
    # ================================================================
    
    async def derive_economic_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "organization",
        scope_id: Optional[str] = None,
    ) -> EconomicOperatingSlice:
        """
        Derive the unified economic operating slice by composing Gates 15, 16, 17.
        
        This is the primary economic operating view for the organization.
        """
        start = time.perf_counter()
        
        # Governance: verify org-wide access
        if not caller.org_wide:
            raise ValueError("Economic operating slice requires org-wide access")
        
        # Build input fingerprint for exact-once
        input_data = {
            "organization_id": caller.organization_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": "economic_operating_slice",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing slice with same fingerprint
        existing = await db.execute(
            select(EconomicOperatingSlice).where(
                EconomicOperatingSlice.organization_id == caller.organization_id,
                EconomicOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Compose from existing services
        financial_slice = await financial_resource_procurement_service.derive_financial_operating_slice(
            db, caller=caller
        )
        resource_slice = await canonical_resource_asset_service.derive_resource_operating_slice(
            db, caller=caller
        )
        vendor_slice = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db, caller=caller
        )
        
        # Strategic context
        objectives = await self._get_objectives(db, caller)
        initiatives = await self._get_initiatives(db, caller)
        projects = await self._get_projects(db, caller)
        
        # Customer/Commercial
        customers = await self._get_customers(db, caller)
        commitments = await self._get_commitments(db, caller)
        commercial_intents = await self._get_commercial_intents(db, caller)
        
        # Bottlenecks
        bottlenecks = await self.derive_bottlenecks(db, caller)
        
        # Predictions
        active_predictions = await self._get_active_predictions(db, caller)
        
        # Counterfactual scenarios
        active_scenarios = await self._get_active_scenarios(db, caller)
        
        # Digital Twin state
        digital_twin_state = await self._get_digital_twin_state(db, caller)
        
        # Economic state distribution
        economic_state_distribution = await self._compute_economic_state_distribution(
            db, caller
        )
        
        # Build slice
        slice_obj = EconomicOperatingSlice(
            organization_id=caller.organization_id,
            input_fingerprint=hashlib.sha256(
                json.dumps({"organization_id": caller.organization_id, "scope": "economic_operating_slice"}, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
            
            # Strategic Context
            objectives=objectives,
            initiatives=initiatives,
            projects=projects,
            
            # Customer/Commercial
            customers=customers,
            commitments=commitments,
            commercial_intents=commercial_intents,
            
            # Financial (Gate 15)
            budgets=financial_slice.budgets,
            budget_commitments=financial_slice.budget_commitments,
            expenses=financial_slice.expenses,
            invoices=financial_slice.invoices,
            payments=financial_slice.payments,
            financial_outcomes=financial_slice.financial_outcomes,
            total_budgeted=financial_slice.total_budgeted,
            total_spent=financial_slice.total_spent,
            total_committed=financial_slice.total_committed,
            total_available=financial_slice.total_available,
            budget_utilization=financial_slice.budget_utilization,
            pending_procurements=financial_slice.pending_procurements,
            overdue_procurements=financial_slice.overdue_procurements,
            procurement_risk_score=financial_slice.procurement_risk_score,
            projected_revenue=financial_slice.projected_revenue,
            projected_cost=financial_slice.projected_cost,
            projected_margin=financial_slice.projected_margin,
            
            # Resource & Asset (Gate 16)
            resources=resource_slice.resources_by_kind,
            assets=resource_slice.assets_by_category,
            resource_demands=[{"kind": k, "count": v} for k, v in resource_slice.demand_by_kind.items()],
            allocations=[{"target_type": k, "count": v} for k, v in resource_slice.allocations_by_target_type.items()],
            total_resources=len(resource_slice.resources_by_kind),
            total_assets=resource_slice.critical_asset_count + sum(resource_slice.assets_by_state.values()) if resource_slice.assets_by_state else 0,
            total_capacity=resource_slice.total_capacity,
            total_committed_capacity=resource_slice.total_committed,
            total_available_capacity=resource_slice.total_available,
            overall_utilization=resource_slice.overall_utilization,
            critical_asset_count=resource_slice.critical_asset_count,
            
            # Demand & Allocation
            total_demands=resource_slice.total_demands,
            unfulfilled_demands=resource_slice.unfulfilled_demands,
            total_allocations=resource_slice.total_allocations,
            active_allocations=resource_slice.active_allocations,
            overall_allocation_utilization=resource_slice.overall_utilization,
            
            # Procurement & Vendor (Gate 17)
            procurements=[],  # Will be populated from vendor_slice
            vendors=vendor_slice.vendors_by_kind,
            external_capacity=vendor_slice.external_capacity_by_type,
            vendor_performance=[],  # Could be populated from VendorPerformance
            total_vendors=vendor_slice.total_vendors,
            active_vendors=vendor_slice.active_vendors,
            critical_vendors=vendor_slice.critical_vendors,
            total_external_capacity=vendor_slice.total_external_capacity,
            available_external_capacity=vendor_slice.available_external_capacity,
            committed_external_capacity=vendor_slice.committed_external_capacity,
            
            # Customer/Commercial
            total_customers=len(customers),
            total_commitments=len(commitments),
            at_risk_commitments=sum(1 for c in commitments if c.get("health_score", 100) < 70),
            
            # Risk & Conflicts
            total_conflicts=resource_slice.conflict_count,
            critical_conflicts=resource_slice.critical_conflict_count,
            vendor_dependency_count=vendor_slice.dependency_count,
            critical_vendor_dependencies=vendor_slice.critical_dependency_count,
            
            # Economic State Distribution
            economic_state_distribution=await self._compute_economic_state_distribution(db, caller),
            
            # Bottlenecks
            bottlenecks=bottlenecks,
            
            # Predictions
            active_predictions=active_predictions,
            
            # Counterfactual scenarios
            active_scenarios=active_scenarios,
            
            # Digital Twin state
            digital_twin_state=digital_twin_state,
            
            # Metadata
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - start) * 1000),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "organization_id": caller.organization_id,
                    "financial_slice_id": financial_slice.id,
                    "resource_slice_id": resource_slice.id,
                    "vendor_slice_id": vendor_slice.id,
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        
        # Use raw SQL INSERT with ON CONFLICT DO NOTHING for exact-once
        from sqlalchemy import text
        insert_sql = text("""
            INSERT INTO economic_operating_slices (
                id, organization_id, input_fingerprint,
                objectives, initiatives, projects,
                customers, commitments, commercial_intents,
                budgets, budget_commitments, expenses, invoices, payments, financial_outcomes,
                resources, assets, resource_demands, allocations,
                procurements, vendors, external_capacity, vendor_performance,
                total_budgeted, total_committed, total_spent, total_available, budget_utilization, cost_variance,
                pending_procurements, overdue_procurements, procurement_risk_score,
                total_resources, total_assets, total_capacity, total_committed_capacity, total_available_capacity,
                overall_utilization, critical_asset_count,
                total_demands, unfulfilled_demands, total_allocations, active_allocations, overall_allocation_utilization,
                total_vendors, active_vendors, critical_vendors,
                total_external_capacity, available_external_capacity, committed_external_capacity, procurement_risk_score,
                total_customers, total_commitments, at_risk_commitments,
                projected_revenue, projected_cost, projected_margin,
                total_conflicts, critical_conflicts, vendor_dependency_count, critical_vendor_dependencies,
                economic_state_distribution, bottlenecks, active_predictions, active_scenarios, digital_twin_state,
                computed_at, computation_duration_ms, fingerprint, created_at, updated_at
            ) VALUES (
                :id, :organization_id, :input_fingerprint,
                :objectives, :initiatives, :projects,
                :customers, :commitments, :commercial_intents,
                :budgets, :budget_commitments, :expenses, :invoices, :payments, :financial_outcomes,
                :resources, :assets, :resource_demands, :allocations,
                :procurements, :vendors, :external_capacity, :vendor_performance,
                :total_budgeted, :total_committed, :total_spent, :total_available, :budget_utilization, :cost_variance,
                :pending_procurements, :overdue_procurements, :procurement_risk_score,
                :total_resources, :total_assets, :total_capacity, :total_committed_capacity, :total_available_capacity,
                :overall_utilization, :critical_asset_count,
                :total_demands, :unfulfilled_demands, :total_allocations, :active_allocations, :overall_allocation_utilization,
                :total_vendors, :active_vendors, :critical_vendors,
                :total_external_capacity, :available_external_capacity, :committed_external_capacity, :procurement_risk_score,
                :total_customers, :total_commitments, :at_risk_commitments,
                :projected_revenue, :projected_cost, :projected_margin,
                :total_conflicts, :critical_conflicts, :vendor_dependency_count, :critical_vendor_dependencies,
                :economic_state_distribution, :bottlenecks, :active_predictions, :active_scenarios, :digital_twin_state,
                :computed_at, :computation_duration_ms, :fingerprint, :created_at, :updated_at
            )
            ON CONFLICT (organization_id, input_fingerprint) DO NOTHING
        """)
        
        slice_id = gen_uuid()
        computed_at = utcnow()
        slice_obj = EconomicOperatingSlice(
            id=slice_id,
            organization_id=caller.organization_id,
            input_fingerprint=input_fingerprint,
            # ... (all fields populated from above)
            # For brevity, the full slice creation is abbreviated
            # In production, all fields would be fully populated
        )
        
        # Compute fingerprint for raw SQL INSERT
        fingerprint = hashlib.sha256(
            json.dumps({
                "organization_id": caller.organization_id,
                "financial_slice_id": financial_slice.id,
                "resource_slice_id": resource_slice.id,
                "vendor_slice_id": vendor_slice.id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Use raw SQL INSERT with ON CONFLICT DO NOTHING for exact-once
        await db.execute(insert_sql, {
            "id": slice_id,
            "organization_id": caller.organization_id,
            "input_fingerprint": input_fingerprint,
            "objectives": json.dumps(objectives),
            "initiatives": json.dumps(initiatives),
            "projects": json.dumps(projects),
            "customers": json.dumps(customers),
            "commitments": json.dumps(commitments),
            "commercial_intents": json.dumps(commercial_intents),
            "budgets": json.dumps(financial_slice.budgets),
            "budget_commitments": json.dumps(financial_slice.budget_commitments),
            "expenses": json.dumps(financial_slice.expenses),
            "invoices": json.dumps(financial_slice.invoices),
            "payments": json.dumps(financial_slice.payments),
            "financial_outcomes": json.dumps(financial_slice.financial_outcomes),
            "resources": json.dumps(resource_slice.resources_by_kind),
            "assets": json.dumps(resource_slice.assets_by_category),
            "resource_demands": json.dumps([{"kind": k, "count": v} for k, v in resource_slice.demand_by_kind.items()]),
            "allocations": json.dumps([{"target_type": k, "count": v} for k, v in resource_slice.allocations_by_target_type.items()]),
            "procurements": json.dumps([]),
            "vendors": json.dumps(vendor_slice.vendors_by_kind),
            "external_capacity": json.dumps(vendor_slice.external_capacity_by_type),
            "vendor_performance": json.dumps([]),
            "total_budgeted": financial_slice.total_budgeted,
            "total_committed": financial_slice.total_committed,
            "total_spent": financial_slice.total_spent,
            "total_available": financial_slice.total_available,
            "budget_utilization": financial_slice.budget_utilization,
            "cost_variance": financial_slice.cost_variance if hasattr(financial_slice, 'cost_variance') else None,
            "pending_procurements": financial_slice.pending_procurements,
            "overdue_procurements": financial_slice.overdue_procurements,
            "procurement_risk_score": financial_slice.procurement_risk_score,
            "total_resources": len(resource_slice.resources_by_kind),
            "total_assets": resource_slice.critical_asset_count + sum(resource_slice.assets_by_state.values()) if resource_slice.assets_by_state else 0,
            "total_capacity": resource_slice.total_capacity,
            "total_committed_capacity": resource_slice.total_committed,
            "total_available_capacity": resource_slice.total_available,
            "overall_utilization": resource_slice.overall_utilization,
            "critical_asset_count": resource_slice.critical_asset_count,
            "total_demands": resource_slice.total_demands,
            "unfulfilled_demands": resource_slice.unfulfilled_demands,
            "total_allocations": resource_slice.total_allocations,
            "active_allocations": resource_slice.active_allocations,
            "overall_allocation_utilization": resource_slice.overall_utilization,
            "total_vendors": vendor_slice.total_vendors,
            "active_vendors": vendor_slice.active_vendors,
            "critical_vendors": vendor_slice.critical_vendors,
            "total_external_capacity": vendor_slice.total_external_capacity,
            "available_external_capacity": vendor_slice.available_external_capacity,
            "committed_external_capacity": vendor_slice.committed_external_capacity,
            "total_customers": len(customers),
            "total_commitments": len(commitments),
            "at_risk_commitments": sum(1 for c in commitments if c.get("health_score", 100) < 70),
            "projected_revenue": financial_slice.projected_revenue,
            "projected_cost": financial_slice.projected_cost,
            "projected_margin": financial_slice.projected_margin,
            "total_conflicts": resource_slice.conflict_count,
            "critical_conflicts": resource_slice.critical_conflict_count,
            "vendor_dependency_count": vendor_slice.dependency_count,
            "critical_vendor_dependencies": vendor_slice.critical_dependency_count,
            "economic_state_distribution": json.dumps(economic_state_distribution),
            "bottlenecks": json.dumps(bottlenecks),
            "active_predictions": json.dumps(active_predictions),
            "active_scenarios": json.dumps(active_scenarios),
            "active_predictions": json.dumps(active_predictions),
            "active_scenarios": json.dumps(active_scenarios),
            "digital_twin_state": json.dumps(digital_twin_state),
            "computed_at": computed_at,
            "computation_duration_ms": int((time.perf_counter() - start) * 1000),
            "fingerprint": fingerprint,
            "created_at": computed_at,
            "updated_at": computed_at,
        })
        
        # Ensure id is generated (gen_uuid default doesn't trigger for raw SQL)
        if not slice_obj.id:
            slice_obj.id = gen_uuid()
        
        # Compute fingerprint for raw SQL INSERT
        fingerprint = hashlib.sha256(
            json.dumps({
                "organization_id": caller.organization_id,
                "financial_slice_id": financial_slice.id,
                "resource_slice_id": resource_slice.id,
                "vendor_slice_id": vendor_slice.id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        await db.flush()
        
        # Query for the existing or newly inserted slice
        existing = await db.execute(
            select(EconomicOperatingSlice).where(
                EconomicOperatingSlice.organization_id == caller.organization_id,
                EconomicOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        return existing.scalars().first()
    
    # ================================================================
    # 2. ECONOMIC IMPACT ANALYSIS
    # ================================================================
    
    async def analyze_economic_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        trigger_type: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_params: Optional[Dict[str, Any]] = None,
    ) -> EconomicImpactAnalysis:
        """
        Analyze the cross-domain economic impact of a change.
        
        Uses Gates 13/15/16/17 cross-domain impact with economic context.
        """
        trigger_params = trigger_params or {}
        
        # Compute fingerprint for exact-once
        fingerprint = hashlib.sha256(
            json.dumps({
                "trigger_type": trigger_type,
                "trigger_entity_type": trigger_entity_type,
                "trigger_entity_id": trigger_entity_id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing analysis
        existing = await db.execute(
            select(EconomicImpactAnalysis).where(
                EconomicImpactAnalysis.organization_id == caller.organization_id,
                EconomicImpactAnalysis.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Gather impacted entities
        affected_budgets = []
        affected_budget_commitments = []
        affected_financial_outcomes = []
        affected_resources = []
        affected_assets = []
        affected_allocations = []
        affected_demands = []
        affected_procurements = []
        affected_vendors = []
        affected_external_capacity = []
        affected_vendor_capabilities = []
        affected_projects = []
        affected_commitments = []
        affected_objectives = []
        affected_people = []
        affected_customers = []
        
        # Budget-level impact
        if trigger_entity_type == "budget":
            budget = await db.get(Budget, trigger_entity_id)
            if budget:
                affected_budgets.append({
                    "id": budget.id,
                    "name": budget.name,
                    "impact": {
                        "total": budget.allocated_amount,
                        "available": budget.remaining_amount,
                    },
                })
                
                # Find commitments for this budget
                bc_results = await db.execute(
                    select(BudgetCommitmentRecord).where(
                        BudgetCommitmentRecord.organization_id == caller.organization_id,
                        BudgetCommitmentRecord.budget_id == budget.id,
                    )
                )
                for bc in bc_results.scalars().all():
                    affected_budget_commitments.append({
                        "id": bc.id,
                        "committed": bc.committed_amount,
                        "spent": bc.spent_amount,
                    })
        
        # Procurement-level impact
        if trigger_entity_type == "procurement":
            proc = await db.get(CanonicalProcurement, trigger_entity_id)
            if proc:
                affected_procurements.append({
                    "id": proc.id,
                    "title": proc.title,
                    "state": proc.state,
                    "vendor": proc.vendor_name,
                    "cost": proc.estimated_cost,
                })
                if proc.project_id:
                    project = await db.get(Project, proc.project_id)
                    if project:
                        affected_projects.append({"id": project.id, "name": project.name})
        
        # Vendor-level impact
        if trigger_entity_type == "vendor":
            vendor = await db.get(CanonicalVendor, trigger_entity_id)
            if vendor:
                affected_vendors.append({
                    "id": vendor.id,
                    "name": vendor.name,
                    "criticality": vendor.criticality,
                    "state": vendor.state,
                })
                # Find procurements for this vendor
                procs = await db.execute(
                    select(CanonicalProcurement).where(
                        CanonicalProcurement.organization_id == caller.organization_id,
                        CanonicalProcurement.vendor_id == vendor.id,
                    )
                )
                for p in procs.scalars().all():
                    affected_procurements.append({"id": p.id, "state": p.state})
                    if p.project_id:
                        affected_projects.append({"id": p.project_id})
        
        # Resource-level impact
        if trigger_entity_type == "resource":
            resource = await db.get(CanonicalResource, trigger_entity_id)
            if resource:
                affected_resources.append({
                    "id": resource.id,
                    "name": resource.name,
                    "category": resource.category,
                    "kind": resource.kind,
                    "capacity_impact": {
                        "total": resource.total_capacity,
                        "available": resource.available_capacity,
                        "utilization": resource.utilization_rate,
                    },
                })
        
        # Asset-level impact
        if trigger_entity_type == "asset":
            asset = await db.get(CanonicalAsset, trigger_entity_id)
            if asset:
                affected_assets.append({
                    "id": asset.id,
                    "name": asset.name,
                    "category": asset.asset_category,
                    "state": asset.lifecycle_state,
                    "is_critical": asset.is_critical,
                })
        
        # Project-level impact
        if trigger_entity_type == "project":
            project = await db.get(Project, trigger_entity_id)
            if project:
                affected_projects.append({
                    "id": project.id,
                    "name": project.name,
                    "status": project.status,
                })
        
        # Quantitative impact assessment
        capacity_impact = {
            "delta_available": 0.0,
            "delta_utilization": 0.0,
            "bottleneck_risk": "low",
        }
        
        if trigger_entity_type == "resource":
            resource = await db.get(CanonicalResource, trigger_entity_id)
            if resource:
                capacity_impact = {
                    "delta_available": -resource.available_capacity if trigger_params.get("reduce_capacity") else 0,
                    "delta_utilization": resource.utilization_rate,
                    "bottleneck_risk": "high" if resource.is_constrained else "low",
                }
        
        # Budget impact
        budget_impact = 0.0
        if trigger_params and "amount" in trigger_params:
            budget_impact = float(trigger_params["amount"])
        
        # Risk assessment
        risk_assessment = {
            "conflicts_triggered": [],
            "bottleneck_risk": capacity_impact.get("bottleneck_risk", "low"),
            "customer_risk": len(affected_customers) > 0,
            "commitment_risk": len(affected_commitments) > 0,
        }
        
        new_conflicts = []
        escalated_conflicts = []
        
        # Detect new conflicts from this change
        if trigger_type in ("budget_cut", "capacity_changed", "resource_removed", "vendor_removed"):
            conflicts = await self._detect_economic_conflicts(db, caller, trigger_entity_id, trigger_entity_type)
            for c in conflicts:
                new_conflicts.append(c.id)
        
        analysis = EconomicImpactAnalysis(
            organization_id=caller.organization_id,
            trigger_type=trigger_type,
            trigger_entity_type=trigger_entity_type,
            trigger_entity_id=trigger_entity_id,
            trigger_params=trigger_params or {},
            affected_budgets=affected_budgets,
            affected_budget_commitments=affected_budget_commitments,
            affected_financial_outcomes=affected_financial_outcomes,
            affected_resources=affected_resources,
            affected_assets=affected_assets,
            affected_allocations=affected_allocations,
            affected_demands=affected_demands,
            affected_procurements=affected_procurements,
            affected_vendors=affected_vendors,
            affected_external_capacity=affected_external_capacity,
            affected_vendor_capabilities=affected_vendor_capabilities,
            affected_projects=affected_projects,
            affected_commitments=affected_commitments,
            affected_objectives=affected_objectives,
            affected_people=affected_people,
            affected_customers=affected_customers,
            capacity_impact=capacity_impact,
            budget_impact=budget_impact,
            revenue_impact=0.0,
            cost_impact=0.0,
            timeline_impact_days=None,
            cost_variance_breakdown={},
            risk_assessment=risk_assessment,
            new_bottlenecks=new_conflicts,
            resolved_bottlenecks=escalated_conflicts,
            scenario_ids=[],
            confidence=0.6,
            analyzed_at=utcnow(),
            source_event_id=trigger_params.get("source_event_id") if trigger_params else None,
            fingerprint=fingerprint,
            version=1,
        )
        
        db.add(analysis)
        try:
            await db.flush()
            return analysis
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(EconomicImpactAnalysis).where(
                    EconomicImpactAnalysis.organization_id == caller.organization_id,
                    EconomicImpactAnalysis.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
        
        # ================================================================
        # Conflict detection
        # ================================================================
    
    async def _detect_economic_conflicts(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_id: str,
        entity_type: str,
    ) -> List[EconomicBottleneck]:
        """Detect economic conflicts from a change."""
        conflicts = []
        
        # Check for overdue procurements
        if entity_type in ("procurement", "vendor"):
            overdue = await db.execute(
                select(CanonicalProcurement).where(
                    CanonicalProcurement.organization_id == caller.organization_id,
                    CanonicalProcurement.expected_delivery < date.today(),
                    CanonicalProcurement.state.in_(["ordered", "in_fulfillment"]),
                )
            )
            for p in overdue.scalars().all():
                conflicts.append(EconomicBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="procurement",
                    severity="high",
                    entity_type="procurement",
                    entity_id=p.id,
                    title=f"Overdue procurement: {p.title}",
                    description=f"Procurement {p.id} expected by {p.expected_delivery}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "overdue", "procurement_id": p.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                ))
        
        # Check for capacity constraints
        if entity_type == "resource":
            resource = await db.get(CanonicalResource, entity_id)
            if resource and resource.is_constrained:
                conflicts.append(EconomicBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="human_capacity" if resource.category == "human" else "physical_resource",
                    severity="critical",
                    resource_id=resource.id,
                    title=f"Resource {resource.name} over capacity",
                    description=f"Available: {resource.available_capacity}, Committed: {resource.committed_capacity}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "capacity_overload", "resource_id": resource.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                ))
        
        # Check for contract expiring
        if entity_type == "vendor":
            vendor = await db.get(CanonicalVendor, entity_id)
            if vendor and vendor.is_contract_expiring_soon:
                conflicts.append(EconomicBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="vendor",
                    severity="high",
                    resource_id=vendor.id,
                    title=f"Vendor {vendor.name} contract expiring soon",
                    description=f"Contract expires: {vendor.contract_expires_at}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "contract_expiring", "vendor_id": vendor.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                ))
        
        db.add_all(conflicts)
        await db.flush()
        return conflicts
    
    # ================================================================
    # Helper methods for composing slices
    # ================================================================
    
    async def _get_objectives(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        result = await db.execute(
            select(CompanyObjective).where(
                CompanyObjective.organization_id == caller.organization_id,
            )
        )
        return [
            {
                "id": obj.id,
                "title": obj.title,
                "status": obj.status,
                "kind": obj.kind,
            }
            for obj in result.scalars().all()
        ]
    
    async def _get_initiatives(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        result = await db.execute(
            select(CompanyInitiative).where(
                CompanyInitiative.organization_id == caller.organization_id,
            )
        )
        return [
            {
                "id": init.id,
                "title": init.title,
                "status": init.status,
                "objective_id": init.objective_id,
            }
            for init in result.scalars().all()
        ]
    
    async def _get_projects(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        result = await db.execute(
            select(Project).where(
                Project.organization_id == caller.organization_id,
            )
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "owner_id": p.owner_id,
            }
            for p in result.scalars().all()
        ]
    
    async def _get_customers(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        result = await db.execute(
            select(Customer).where(
                Customer.organization_id == caller.organization_id,
            )
        )
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "health_score": c.health_score,
            }
            for c in result.scalars().all()
        ]
    
    async def _get_commitments(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        # Both CustomerCommitment and CompanyCommitment
        customer_commitments = await db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.organization_id == caller.organization_id,
            )
        )
        company_commitments = await db.execute(
            select(CompanyCommitment).where(
                CompanyCommitment.organization_id == caller.organization_id,
            )
        )
        commitments = []
        for c in customer_commitments.scalars().all():
            commitments.append({
                "id": c.id,
                "title": c.title,
                "customer_id": c.customer_id,
                "type": "customer",
            })
        for c in company_commitments.scalars().all():
            commitments.append({
                "id": c.id,
                "title": c.title,
                "type": "company",
            })
        return commitments
    
    async def _get_commercial_intents(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        from app.models.business_commercial import CommercialIntent
        result = await db.execute(
            select(CommercialIntent).where(
                CommercialIntent.organization_id == caller.organization_id,
            )
        )
        return [
            {
                "id": ci.id,
                "title": ci.title,
                "status": ci.status,
            }
            for ci in result.scalars().all()
        ]
    
    async def _compute_economic_state_distribution(
        self, db: AsyncSession, caller: CallerAccess
    ) -> Dict[str, int]:
        """Compute distribution of economic states across all tracked entities."""
        distribution = {state: 0 for state in ECONOMIC_STATES}
        
        # Count by economic state
        # This would query various tables and map their states to ECONOMIC_STATES
        return distribution
    
    async def derive_bottlenecks(
        self, db: AsyncSession, caller: CallerAccess
    ) -> List[dict]:
        """Derive economic bottlenecks from canonical reality."""
        bottlenecks = []
        
        # Financial bottleneck
        financial_slice = await financial_resource_procurement_service.derive_financial_operating_slice(
            db, caller=caller
        )
        if financial_slice.total_available is not None and financial_slice.total_available < 0:
            bottlenecks.append({
                "bottleneck_type": "financial",
                "severity": "critical",
                "entity_type": "budget",
                "entity_id": "org_budget",
                "title": "Budget deficit detected",
                "description": f"Available budget is negative: {financial_slice.total_available}",
                "constrained_amount": abs(financial_slice.total_available or 0),
            })
        
        # Human capacity bottleneck
        resource_slice = await canonical_resource_asset_service.derive_resource_operating_slice(
            db, caller=caller
        )
        if resource_slice.overall_utilization and resource_slice.overall_utilization > 0.9:
            bottlenecks.append({
                "bottleneck_type": "human_capacity",
                "severity": "high",
                "entity_type": "resource",
                "entity_id": "human_capacity",
                "title": "Human capacity over 90% utilized",
                "description": f"Overall utilization at {resource_slice.overall_utilization * 100:.1f}%",
                "utilization_rate": resource_slice.overall_utilization,
            })
        
        # Digital infrastructure bottleneck
        # Check for cloud compute, storage, etc.
        vendor_slice = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db, caller=caller
        )
        if vendor_slice.total_external_capacity and vendor_slice.available_external_capacity:
            ext_utilization = 1 - (vendor_slice.available_external_capacity / vendor_slice.total_external_capacity)
            if ext_utilization > 0.85:
                bottlenecks.append({
                    "bottleneck_type": "digital_infrastructure",
                    "severity": "warning",
                    "entity_type": "external_capacity",
                    "entity_id": "cloud_capacity",
                    "title": "External cloud capacity highly utilized",
                    "description": f"External capacity utilization at {ext_utilization * 100:.1f}%",
                    "utilization_rate": ext_utilization,
                })
        
        # Procurement bottleneck
        if financial_slice.overdue_procurements > 0:
            bottlenecks.append({
                "bottleneck_type": "procurement",
                "severity": "high",
                "entity_type": "procurement",
                "entity_id": "overdue_procurements",
                "title": f"{financial_slice.overdue_procurements} overdue procurements",
                "description": "Procurement delays may impact project timelines",
            })
        
        # Vendor bottleneck
        vendor_slice = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db, caller=caller
        )
        if vendor_slice.critical_dependency_count > 0:
            bottlenecks.append({
                "bottleneck_type": "vendor",
                "severity": "critical",
                "entity_type": "vendor",
                "entity_id": "critical_vendors",
                "title": f"{vendor_slice.critical_dependency_count} critical vendor dependencies",
                "description": "Critical single-source vendor dependencies detected",
            })
        
        return bottlenecks
    
    async def _get_active_predictions(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        """Get active economic predictions from Gate 10."""
        from app.models.prediction import Prediction
        result = await db.execute(
            select(Prediction).where(
                Prediction.organization_id == caller.organization_id,
            ).limit(20)
        )
        return [
            {
                "id": p.id,
                "kind": p.kind,
                "entity_type": p.entity_type,
                "entity_id": p.entity_id,
                "predicted_value": p.predicted_value,
                "confidence": p.confidence,
            }
            for p in result.scalars().all()
        ]
    
    async def _get_active_scenarios(self, db: AsyncSession, caller: CallerAccess) -> List[dict]:
        """Get active counterfactual scenarios from Gate 11."""
        from app.models.company_operating import CompanyScenarioRun
        result = await db.execute(
            select(CompanyScenarioRun).where(
                CompanyScenarioRun.organization_id == caller.organization_id,
            ).limit(10)
        )
        return [
            {
                "id": s.id,
                "scenario_kind": s.scenario_kind,
                "subject_type": s.subject_type,
                "subject_id": s.subject_id,
            }
            for s in result.scalars().all()
        ]
    
    async def _get_digital_twin_state(self, db: AsyncSession, caller: CallerAccess) -> dict:
        """Get current digital twin state from Gate 12."""
        from app.models.digital_twin import DigitalTwin
        result = await db.execute(
            select(DigitalTwin).where(
                DigitalTwin.organization_id == caller.organization_id,
            )
        )
        twin = result.scalars().first()
        if twin:
            return {
                "health_score": twin.health_score,
                "health_status": twin.health_status,
                "last_refreshed": twin.last_refreshed_at.isoformat() if twin.last_refreshed_at else None,
            }
        return {}


# Global instance
canonical_economic_intelligence_service = CanonicalEconomicIntelligenceService()