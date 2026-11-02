"""Canonical Resource, Asset & Allocation Operating Fabric Service — Gate 16.

Derives resource/asset/allocation operating slices, impact analyses, and contexts
from the canonical company reality (Gates 8-15).

This is a DERIVED PROJECTION layer — it does NOT create a second resource/asset reality.
All data is composed from existing canonical primitives:
- Gate 8: People, Work, Communication, Meetings, Organizational Intelligence, Capacity
- Gate 9: Institutional Learning
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 15: Financial + Resource + Procurement Operating Fabric
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
from app.models.canonical_resource_asset import (
    CanonicalResource,
    CanonicalAsset,
    ResourceDemand,
    ResourceAllocation,
    ResourceConflict,
    ResourceOperatingSlice,
    ResourceImpactAnalysis,
    RESOURCE_CATEGORIES,
    RESOURCE_KINDS,
    ASSET_LIFECYCLE_STATES,
    ALLOCATION_STATES,
    ALLOCATION_TARGET_TYPES,
    DEMAND_SOURCES,
    SUPPLY_SOURCES,
)
from app.models.financial_resource_procurement import (
    ResourceRequirement,
    ResourceAllocationRecord,
    ProcurementRecord,
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilityProjectLink,
    CapabilitySignal,
)
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyObjective,
    CompanyInitiative,
    OrganizationalResponsibility,
)
from app.models.project import Project
from app.models.customer import Customer, CustomerProjectLink
from app.models.customer_intelligence import CustomerCommitment
from app.models.employee import Employee, EmployeeAvailability, EmployeeSkill
from app.models.skills_intelligence import CanonicalSkill, Expertise
from app.intelligence.strategic_alignment_engine import strategic_alignment_engine
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.company_operating_engine import company_operating_engine
from app.intelligence.customer_operating_fabric_service import customer_operating_fabric_service
from app.intelligence.financial_resource_procurement_service import financial_resource_procurement_service

logger = logging.getLogger("vcos.intelligence.canonical_resource_asset")


class CanonicalResourceAssetService:
    """
    Service for deriving the canonical resource/asset/allocation operating fabric.
    
    All methods return DERIVED PROJECTIONS over canonical reality.
    They do NOT mutate canonical data.
    """
    
    # ================================================================
    # 1. CANONICAL RESOURCE DERIVATION
    # ================================================================
    
    async def derive_resource_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "organization",
        scope_id: Optional[str] = None,
    ) -> ResourceOperatingSlice:
        """
        Derive a governed, point-in-time operating slice for resources.
        
        Composes all canonical reality relevant to resources:
        - Resources (capacity, state, allocation)
        - Assets (lifecycle, dependencies, value)
        - Demands (unfulfilled, priority)
        - Allocations (active, utilization)
        - Conflicts (bottlenecks, overloads)
        - Financial (Gate 15 integration)
        """
        start = time.perf_counter()
        
        # Governance: verify access
        await self._verify_resource_access(db, caller, scope_type, scope_id)
        
        # Build input fingerprint for exact-once
        input_data = {
            "organization_id": caller.organization_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": "resource_operating_slice",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing slice with same fingerprint
        existing = await db.execute(
            select(ResourceOperatingSlice).where(
                ResourceOperatingSlice.organization_id == caller.organization_id,
                ResourceOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Derive resource summary
        resources = await self._get_resources(db, caller)
        assets = await self._get_assets(db, caller)
        demands = await self._get_demands(db, caller)
        allocations = await self._get_allocations(db, caller)
        conflicts = await self._get_conflicts(db, caller)
        
        # Build summary metrics
        resources_by_category = {}
        resources_by_kind = {}
        resources_by_state = {}
        total_capacity = 0.0
        total_committed = 0.0
        total_reserved = 0.0
        total_available = 0.0
        
        for r in resources:
            resources_by_category[r.category] = resources_by_category.get(r.category, 0) + 1
            resources_by_kind[r.kind] = resources_by_kind.get(r.kind, 0) + 1
            resources_by_state[r.state] = resources_by_state.get(r.state, 0) + 1
            total_capacity += r.total_capacity
            total_committed += r.committed_capacity
            total_reserved += r.reserved_capacity
            total_available += r.available_capacity
        
        overall_utilization = total_committed / total_capacity if total_capacity > 0 else 0.0
        
        # Asset summary
        assets_by_category = {}
        assets_by_state = {}
        critical_asset_count = 0
        for a in assets:
            assets_by_category[a.asset_category] = assets_by_category.get(a.asset_category, 0) + 1
            assets_by_state[a.lifecycle_state] = assets_by_state.get(a.lifecycle_state, 0) + 1
            if a.is_critical:
                critical_asset_count += 1
        
        # Allocation summary
        total_allocations = len(allocations)
        active_allocations = sum(1 for a in allocations if a.state == "active")
        allocations_by_target_type = {}
        for a in allocations:
            allocations_by_target_type[a.target_type] = allocations_by_target_type.get(a.target_type, 0) + 1
        
        # Demand summary
        total_demands = len(demands)
        unfulfilled_demands = sum(1 for d in demands if not d.is_fulfilled)
        demand_by_kind = {}
        for d in demands:
            demand_by_kind[d.resource_kind] = demand_by_kind.get(d.resource_kind, 0) + 1
        
        # Conflicts
        conflict_count = len(conflicts)
        critical_conflict_count = sum(1 for c in conflicts if c.severity == "critical")
        conflicts_by_kind = {}
        for c in conflicts:
            conflicts_by_kind[c.conflict_kind] = conflicts_by_kind.get(c.conflict_kind, 0) + 1
        
        # Financial (Gate 15)
        total_resource_cost = sum(r.cost_per_unit or 0 for r in resources if r.cost_per_unit)
        allocated_budget = sum(a.cost_allocated or 0 for a in allocations if a.cost_allocated)
        
        slice_obj = ResourceOperatingSlice(
            organization_id=caller.organization_id,
            input_fingerprint=input_fingerprint,
            resources_by_category=resources_by_category,
            resources_by_kind=resources_by_kind,
            resources_by_state=resources_by_state,
            assets_by_category=assets_by_category,
            assets_by_state=assets_by_state,
            critical_asset_count=critical_asset_count,
            total_allocations=total_allocations,
            active_allocations=active_allocations,
            allocations_by_target_type=allocations_by_target_type,
            total_capacity=total_capacity,
            total_committed=total_committed,
            total_reserved=total_reserved,
            total_available=total_available,
            overall_utilization=overall_utilization,
            total_demands=total_demands,
            unfulfilled_demands=unfulfilled_demands,
            demand_by_kind=demand_by_kind,
            conflict_count=conflict_count,
            critical_conflict_count=critical_conflict_count,
            conflicts_by_kind=conflicts_by_kind,
            total_resource_cost=total_resource_cost,
            allocated_budget=allocated_budget,
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - start) * 1000),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "resource_count": len(resources),
                    "asset_count": len(assets),
                    "demand_count": len(demands),
                    "allocation_count": len(allocations),
                    "conflict_count": len(conflicts),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        
        # Ensure id is generated (gen_uuid default doesn't trigger for raw SQL)
        if not slice_obj.id:
            slice_obj.id = gen_uuid()
        
        # Use raw SQL INSERT with ON CONFLICT DO NOTHING for exact-once
        from sqlalchemy import text
        insert_sql = text("""
            INSERT INTO resource_operating_slices (
                id, organization_id, input_fingerprint,
                resources_by_category, resources_by_kind, resources_by_state,
                assets_by_category, assets_by_state, critical_asset_count,
                total_allocations, active_allocations, allocations_by_target_type,
                total_capacity, total_committed, total_reserved, total_available,
                overall_utilization, total_demands, unfulfilled_demands,
                demand_by_kind, conflict_count, critical_conflict_count,
                conflicts_by_kind, total_resource_cost, allocated_budget,
                computed_at, computation_duration_ms, fingerprint,
                created_at, updated_at
            ) VALUES (
                :id, :organization_id, :input_fingerprint,
                :resources_by_category, :resources_by_kind, :resources_by_state,
                :assets_by_category, :assets_by_state, :critical_asset_count,
                :total_allocations, :active_allocations, :allocations_by_target_type,
                :total_capacity, :total_committed, :total_reserved, :total_available,
                :overall_utilization, :total_demands, :unfulfilled_demands,
                :demand_by_kind, :conflict_count, :critical_conflict_count,
                :conflicts_by_kind, :total_resource_cost, :allocated_budget,
                :computed_at, :computation_duration_ms, :fingerprint,
                :created_at, :updated_at
            )
            ON CONFLICT (organization_id, input_fingerprint) DO NOTHING
        """)
        
        await db.execute(insert_sql, {
            "id": slice_obj.id,
            "organization_id": slice_obj.organization_id,
            "input_fingerprint": slice_obj.input_fingerprint,
            "resources_by_category": json.dumps(slice_obj.resources_by_category),
            "resources_by_kind": json.dumps(slice_obj.resources_by_kind),
            "resources_by_state": json.dumps(slice_obj.resources_by_state),
            "assets_by_category": json.dumps(slice_obj.assets_by_category),
            "assets_by_state": json.dumps(slice_obj.assets_by_state),
            "critical_asset_count": slice_obj.critical_asset_count,
            "total_allocations": slice_obj.total_allocations,
            "active_allocations": slice_obj.active_allocations,
            "allocations_by_target_type": json.dumps(slice_obj.allocations_by_target_type),
            "total_capacity": slice_obj.total_capacity,
            "total_committed": slice_obj.total_committed,
            "total_reserved": slice_obj.total_reserved,
            "total_available": slice_obj.total_available,
            "overall_utilization": slice_obj.overall_utilization,
            "total_demands": slice_obj.total_demands,
            "unfulfilled_demands": slice_obj.unfulfilled_demands,
            "demand_by_kind": json.dumps(slice_obj.demand_by_kind),
            "conflict_count": slice_obj.conflict_count,
            "critical_conflict_count": slice_obj.critical_conflict_count,
            "conflicts_by_kind": json.dumps(slice_obj.conflicts_by_kind),
            "total_resource_cost": slice_obj.total_resource_cost,
            "allocated_budget": slice_obj.allocated_budget,
            "computed_at": slice_obj.computed_at,
            "computation_duration_ms": slice_obj.computation_duration_ms,
            "fingerprint": slice_obj.fingerprint,
            "created_at": slice_obj.created_at,
            "updated_at": slice_obj.updated_at,
        })
        await db.flush()
        
        # Query for the existing or newly inserted slice
        existing = await db.execute(
            select(ResourceOperatingSlice).where(
                ResourceOperatingSlice.organization_id == caller.organization_id,
                ResourceOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        return existing.scalars().first()
    
    async def _get_resources(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalResource]:
        result = await db.execute(
            select(CanonicalResource).where(
                CanonicalResource.organization_id == caller.organization_id,
            ).order_by(CanonicalResource.category, CanonicalResource.kind)
        )
        return list(result.scalars().all())
    
    async def _get_assets(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalAsset]:
        result = await db.execute(
            select(CanonicalAsset).where(
                CanonicalAsset.organization_id == caller.organization_id,
            ).order_by(CanonicalAsset.asset_category, CanonicalAsset.lifecycle_state)
        )
        return list(result.scalars().all())
    
    async def _get_demands(self, db: AsyncSession, caller: CallerAccess) -> List[ResourceDemand]:
        result = await db.execute(
            select(ResourceDemand).where(
                ResourceDemand.organization_id == caller.organization_id,
            ).order_by(ResourceDemand.priority, ResourceDemand.window_start)
        )
        return list(result.scalars().all())
    
    async def _get_allocations(self, db: AsyncSession, caller: CallerAccess) -> List[ResourceAllocation]:
        result = await db.execute(
            select(ResourceAllocation).where(
                ResourceAllocation.organization_id == caller.organization_id,
            ).order_by(ResourceAllocation.window_start, ResourceAllocation.target_type)
        )
        return list(result.scalars().all())
    
    async def _get_conflicts(self, db: AsyncSession, caller: CallerAccess) -> List[ResourceConflict]:
        result = await db.execute(
            select(ResourceConflict).where(
                ResourceConflict.organization_id == caller.organization_id,
                ResourceConflict.status.in_(["open", "acknowledged", "mitigating"]),
            ).order_by(
                ResourceConflict.severity.desc(),
                ResourceConflict.detected_at.desc()
            )
        )
        return list(result.scalars().all())
    
    async def _verify_resource_access(self, db: AsyncSession, caller: CallerAccess, scope_type: str, scope_id: Optional[str]) -> None:
        """Verify caller has access to resource scope."""
        # For now, organization-level access is sufficient
        # Could be extended with scope-based RBAC
        pass
    
    # ================================================================
    # 2. RESOURCE IMPACT ANALYSIS
    # ================================================================
    
    async def analyze_resource_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        trigger_type: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_params: Optional[Dict[str, Any]] = None,
    ) -> ResourceImpactAnalysis:
        """
        Analyze cross-domain impact of a resource change.
        
        Trigger types:
        - resource_added
        - resource_removed
        - resource_reallocated
        - resource_failed
        - resource_delayed
        - capacity_changed
        - asset_lifecycle_changed
        - allocation_created
        - allocation_released
        - demand_created
        - demand_fulfilled
        """
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
            select(ResourceImpactAnalysis).where(
                ResourceImpactAnalysis.organization_id == caller.organization_id,
                ResourceImpactAnalysis.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Gather impacted entities
        affected_resources = []
        affected_allocations = []
        affected_demands = []
        affected_assets = []
        affected_projects = []
        affected_commitments = []
        affected_objectives = []
        affected_people = []
        affected_customers = []
        affected_capabilities = []
        
        # Resource-level impact
        if trigger_entity_type in ("resource", "allocation", "demand"):
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
                
                # Find allocations for this resource
                allocs = await db.execute(
                    select(ResourceAllocation).where(
                        ResourceAllocation.organization_id == caller.organization_id,
                        ResourceAllocation.resource_id == resource.id,
                    )
                )
                for a in allocs.scalars().all():
                    affected_allocations.append({
                        "id": a.id,
                        "target_type": a.target_type,
                        "target_id": a.target_id,
                        "units": a.units_allocated,
                        "state": a.state,
                    })
                
                # Find demands for this resource kind
                demands = await db.execute(
                    select(ResourceDemand).where(
                        ResourceDemand.organization_id == caller.organization_id,
                        ResourceDemand.resource_kind == resource.kind,
                    )
                )
                for d in demands.scalars().all():
                    affected_demands.append({
                        "id": d.id,
                        "source_type": d.source_type,
                        "source_id": d.source_id,
                        "units_requested": d.units_requested,
                        "units_remaining": d.units_remaining,
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
                    "dependent_projects": asset.dependent_project_ids,
                    "dependent_commitments": asset.dependent_commitment_ids,
                    "dependent_customers": asset.dependent_customer_ids,
                })
                
                # Trace to dependent projects
                for pid in asset.dependent_project_ids or []:
                    project = await db.get(Project, pid)
                    if project:
                        affected_projects.append({
                            "id": project.id,
                            "name": project.name,
                            "status": project.status,
                        })
                
                # Trace to dependent commitments
                for cid in asset.dependent_commitment_ids or []:
                    commitment = await db.get(CompanyCommitment, cid)
                    if commitment:
                        affected_commitments.append({
                            "id": commitment.id,
                            "title": commitment.title,
                        })
                
                # Trace to dependent customers
                for cust_id in asset.dependent_customer_ids or []:
                    customer = await db.get(Customer, cust_id)
                    if customer:
                        affected_customers.append({
                            "id": customer.id,
                            "name": customer.name,
                        })
        
        # Project-level impact (if trigger is project)
        if trigger_entity_type == "project":
            project = await db.get(Project, trigger_entity_id)
            if project:
                affected_projects.append({
                    "id": project.id,
                    "name": project.name,
                })
                
                # Find demands for this project
                demands = await db.execute(
                    select(ResourceDemand).where(
                        ResourceDemand.organization_id == caller.organization_id,
                        ResourceDemand.source_type == "project",
                        ResourceDemand.source_id == project.id,
                    )
                )
                for d in demands.scalars().all():
                    affected_demands.append({
                        "id": d.id,
                        "resource_kind": d.resource_kind,
                        "units_requested": d.units_requested,
                        "units_remaining": d.units_remaining,
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
                    "delta_available": -resource.available_capacity if trigger_type == "resource_removed" else 0,
                    "delta_utilization": resource.utilization_rate,
                    "bottleneck_risk": "high" if resource.is_constrained else "low",
                }
        
        # Budget impact (Gate 15 integration)
        budget_impact = 0.0
        if trigger_params and "cost" in trigger_params:
            budget_impact = float(trigger_params["cost"])
        
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
        if trigger_type in ("resource_removed", "capacity_changed", "resource_failed"):
            conflicts = await self._detect_conflicts(db, caller, trigger_entity_id, trigger_entity_type)
            for c in conflicts:
                new_conflicts.append(c.id)
        
        analysis = ResourceImpactAnalysis(
            organization_id=caller.organization_id,
            trigger_type=trigger_type,
            trigger_entity_type=trigger_entity_type,
            trigger_entity_id=trigger_entity_id,
            trigger_params=trigger_params or {},
            affected_resources=affected_resources,
            affected_allocations=affected_allocations,
            affected_demands=affected_demands,
            affected_assets=affected_assets,
            affected_projects=affected_projects,
            affected_commitments=affected_commitments,
            affected_objectives=affected_objectives,
            affected_people=affected_people,
            affected_customers=affected_customers,
            affected_capabilities=affected_capabilities,
            capacity_impact=capacity_impact,
            budget_impact=budget_impact,
            revenue_impact=0.0,
            cost_impact=0.0,
            timeline_impact_days=None,
            risk_assessment=risk_assessment,
            new_conflicts=new_conflicts,
            escalated_conflicts=escalated_conflicts,
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
                select(ResourceImpactAnalysis).where(
                    ResourceImpactAnalysis.organization_id == caller.organization_id,
                    ResourceImpactAnalysis.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def _detect_conflicts(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        resource_id: str,
        entity_type: str,
    ) -> List[ResourceConflict]:
        """Detect resource conflicts from a change."""
        conflicts = []
        
        # Check for double allocation
        allocations = await db.execute(
            select(ResourceAllocation).where(
                ResourceAllocation.organization_id == caller.organization_id,
                ResourceAllocation.resource_id == resource_id,
                ResourceAllocation.state == "active",
            )
        )
        active_allocs = list(allocations.scalars().all())
        
        if len(active_allocs) > 1:
            # Multiple active allocations for same resource
            conflict = ResourceConflict(
                organization_id=caller.organization_id,
                conflict_kind="double_allocation",
                severity="critical",
                status="open",
                resource_id=resource_id,
                affected_allocation_ids=[a.id for a in active_allocs],
                title=f"Resource {resource_id} allocated to {len(active_allocs)} targets simultaneously",
                description=f"Active allocations: {[a.target_id for a in active_allocs]}",
                evidence_json={"allocation_ids": [a.id for a in active_allocs]},
                detected_at=utcnow(),
                detected_by="system",
                detection_method="derived",
                fingerprint=hashlib.sha256(
                    json.dumps({
                        "kind": "double_allocation",
                        "resource_id": resource_id,
                        "allocations": sorted([a.id for a in active_allocs]),
                    }, sort_keys=True, default=str).encode()
                ).hexdigest()[:64],
            )
            db.add(conflict)
            conflicts.append(conflict)
        
        # Check for capacity overload
        resource = await db.get(CanonicalResource, resource_id)
        if resource and resource.is_constrained:
            conflict = ResourceConflict(
                organization_id=caller.organization_id,
                conflict_kind="capacity_overload",
                severity="critical",
                status="open",
                resource_id=resource_id,
                resource_kind=resource.kind,
                affected_allocation_ids=[a.id for a in active_allocs],
                title=f"Resource {resource.name} ({resource.kind}) is over capacity",
                description=f"Available: {resource.available_capacity}, Committed: {resource.committed_capacity}, Total: {resource.total_capacity}",
                evidence_json={
                    "total_capacity": resource.total_capacity,
                    "committed_capacity": resource.committed_capacity,
                    "available_capacity": resource.available_capacity,
                },
                detected_at=utcnow(),
                detected_by="system",
                detection_method="derived",
                fingerprint=hashlib.sha256(
                    json.dumps({
                        "kind": "capacity_overload",
                        "resource_id": resource_id,
                        "capacity": resource.total_capacity,
                    }, sort_keys=True, default=str).encode()
                ).hexdigest()[:64],
            )
            db.add(conflict)
            conflicts.append(conflict)
        
        # Check for underutilization
        for alloc in active_allocs:
            if alloc.actual_utilization is not None and alloc.actual_utilization < alloc.units_allocated * 0.3:
                conflict = ResourceConflict(
                    organization_id=caller.organization_id,
                    conflict_kind="underutilization",
                    severity="warning",
                    status="open",
                    resource_id=resource_id,
                    affected_allocation_ids=[alloc.id],
                    title=f"Allocation {alloc.id} significantly underutilized",
                    description=f"Allocated: {alloc.units_allocated}, Actual: {alloc.actual_utilization}",
                    evidence_json={
                        "allocated": alloc.units_allocated,
                        "actual": alloc.actual_utilization,
                        "target": alloc.target_id,
                    },
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({
                            "kind": "underutilization",
                            "allocation_id": alloc.id,
                        }, sort_keys=True, default=str).encode()
                    ).hexdigest()[:64],
                )
                db.add(conflict)
                conflicts.append(conflict)
        
        # Check for lifecycle risk (asset approaching retirement/maintenance)
        if entity_type == "asset":
            asset = await db.get(CanonicalAsset, resource_id)
            if asset and asset.is_approaching_maintenance:
                conflict = ResourceConflict(
                    organization_id=caller.organization_id,
                    conflict_kind="lifecycle_risk",
                    severity="warning",
                    status="open",
                    resource_id=resource_id,
                    resource_kind=asset.asset_category,
                    title=f"Asset {asset.name} approaching maintenance window",
                    description=f"Next maintenance due: {asset.next_maintenance_at}",
                    evidence_json={
                        "asset_id": asset.id,
                        "next_maintenance": str(asset.next_maintenance_at) if asset.next_maintenance_at else None,
                    },
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({
                            "kind": "lifecycle_risk",
                            "asset_id": asset.id,
                        }, sort_keys=True, default=str).encode()
                    ).hexdigest()[:64],
                )
                db.add(conflict)
                conflicts.append(conflict)
        
        return conflicts
    
    # ================================================================
    # 3. RESOURCE DEMAND MANAGEMENT
    # ================================================================
    
    async def create_resource_demand(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        source_type: str,
        source_id: str,
        source_name: Optional[str],
        resource_category: str,
        resource_kind: str,
        units_requested: float,
        unit: str,
        window_start: date,
        window_end: date,
        priority: int = 3,
        urgency: str = "normal",
        proficiency: Optional[str] = None,
        justification: Optional[str] = None,
    ) -> ResourceDemand:
        """Create a resource demand with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "source_type": source_type,
                "source_id": source_id,
                "resource_category": resource_category,
                "resource_kind": resource_kind,
                "window_start": str(window_start),
                "window_end": str(window_end),
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing demand
        existing = await db.execute(
            select(ResourceDemand).where(
                ResourceDemand.organization_id == caller.organization_id,
                ResourceDemand.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        demand = ResourceDemand(
            organization_id=caller.organization_id,
            source_type=source_type,
            source_id=source_id,
            source_name=source_name,
            resource_category=resource_category,
            resource_kind=resource_kind,
            units_requested=units_requested,
            unit=unit,
            window_start=window_start,
            window_end=window_end,
            priority=priority,
            urgency=urgency,
            proficiency=proficiency,
            justification=justification,
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(demand)
        try:
            await db.flush()
            return demand
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ResourceDemand).where(
                    ResourceDemand.organization_id == caller.organization_id,
                    ResourceDemand.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    # ================================================================
    # 4. RESOURCE ALLOCATION MANAGEMENT
    # ================================================================
    
    async def create_resource_allocation(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        resource_id: str,
        target_type: str,
        target_id: str,
        target_name: Optional[str],
        units_allocated: float,
        unit: str,
        window_start: date,
        window_end: date,
        demand_id: Optional[str] = None,
        purpose: Optional[str] = None,
        expected_outcome: Optional[str] = None,
        budget_id: Optional[str] = None,
    ) -> ResourceAllocation:
        """Create a resource allocation with exact-once semantics."""
        
        # Get resource to determine category and kind
        resource = await db.get(CanonicalResource, resource_id)
        if not resource:
            raise ValueError(f"Resource not found: {resource_id}")
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "resource_id": resource_id,
                "target_type": target_type,
                "target_id": target_id,
                "window_start": str(window_start),
                "window_end": str(window_end),
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing allocation
        existing = await db.execute(
            select(ResourceAllocation).where(
                ResourceAllocation.organization_id == caller.organization_id,
                ResourceAllocation.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        allocation = ResourceAllocation(
            organization_id=caller.organization_id,
            resource_id=resource_id,
            resource_category=resource.category,
            resource_kind=resource.kind,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            demand_id=demand_id,
            units_allocated=units_allocated,
            unit=unit,
            window_start=window_start,
            window_end=window_end,
            state="requested",
            purpose=purpose,
            expected_outcome=expected_outcome,
            budget_id=budget_id,
            requested_by=caller.employee_id or "system",
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(allocation)
        try:
            await db.flush()
            
            # Update demand fulfillment if linked
            if demand_id:
                demand = await db.get(ResourceDemand, demand_id)
                if demand:
                    demand.units_fulfilled += units_allocated
                    if demand.is_fulfilled:
                        demand.fulfillment_status = "fulfilled"
                    elif demand.units_fulfilled > 0:
                        demand.fulfillment_status = "partial"
            
            # Update resource capacity
            resource = await db.get(CanonicalResource, resource_id)
            if resource:
                resource.committed_capacity += units_allocated
                resource.available_capacity = max(0, resource.total_capacity - resource.committed_capacity - resource.reserved_capacity)
            
            # Flush demand and resource updates
            await db.flush()
            
            return allocation
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ResourceAllocation).where(
                    ResourceAllocation.organization_id == caller.organization_id,
                    ResourceAllocation.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def release_resource_allocation(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        allocation_id: str,
        released_by: Optional[str] = None,
    ) -> Optional[ResourceAllocation]:
        """Release an allocation back to available pool."""
        
        allocation = await db.get(ResourceAllocation, allocation_id)
        if not allocation:
            return None
        
        if allocation.state in ("released", "cancelled", "completed"):
            return allocation
        
        allocation.state = "released"
        allocation.released_by = released_by or caller.employee_id
        allocation.released_at = utcnow()
        
        # Update demand fulfillment
        if allocation.demand_id:
            demand = await db.get(ResourceDemand, allocation.demand_id)
            if demand:
                demand.units_fulfilled = max(0, demand.units_fulfilled - allocation.units_allocated)
                if demand.units_fulfilled <= 0:
                    demand.fulfillment_status = "unfulfilled"
                else:
                    demand.fulfillment_status = "partial"
        
        # Update resource capacity
        resource = await db.get(CanonicalResource, allocation.resource_id)
        if resource:
            resource.committed_capacity = max(0, resource.committed_capacity - allocation.units_allocated)
            resource.available_capacity = min(
                resource.total_capacity,
                resource.available_capacity + allocation.units_allocated
            )
        
        await db.flush()
        return allocation
    
    # ================================================================
    # 5. RESOURCE CREATION FROM PROCUREMENT (Gate 15 Integration)
    # ================================================================
    
    async def create_resource_from_procurement(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
    ) -> Optional[CanonicalResource]:
        """Create a CanonicalResource from a completed ProcurementRecord (Gate 15)."""
        
        procurement = await db.get(ProcurementRecord, procurement_id)
        if not procurement:
            return None
        
        # Only create resource if procurement is in a delivered state
        if procurement.state not in ("delivered", "completed", "received"):
            return None
        
        # Determine resource category/kind from procurement
        resource_category = self._map_procurement_to_category(procurement.kind)
        resource_kind = self._map_procurement_to_kind(procurement.kind, procurement.title)
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "procurement_id": procurement_id,
                "resource_category": resource_category,
                "resource_kind": resource_kind,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(CanonicalResource).where(
                CanonicalResource.organization_id == caller.organization_id,
                CanonicalResource.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Estimate capacity from procurement
        capacity = self._estimate_capacity_from_procurement(procurement)
        
        resource = CanonicalResource(
            organization_id=caller.organization_id,
            category=resource_category,
            kind=resource_kind,
            name=f"{procurement.title} ({procurement.kind})",
            description=f"Created from procurement {procurement.id}",
            resource_identity=procurement_id,
            resource_identity_type="procurement",
            owned_by_organization=True,
            vendor_id=procurement.vendor_id,
            vendor_name=procurement.vendor_name,
            unit=self._get_unit_for_kind(resource_kind),
            total_capacity=capacity,
            committed_capacity=0.0,
            reserved_capacity=0.0,
            available_capacity=capacity,
            state="available",
            supply_source="procurement",
            cost_per_unit=procurement.actual_cost / capacity if capacity > 0 and procurement.actual_cost else None,
            currency=procurement.currency,
            budget_id=procurement.budget_id,
            procurement_id=procurement_id,
            procurement_kind=procurement.kind,
            governed=True,
            created_by=caller.employee_id or "system",
            fingerprint=fingerprint,
        )
        
        db.add(resource)
        try:
            await db.flush()
            
            # Also create asset if physical/digital
            if resource_category in ("physical", "digital", "infrastructure"):
                await self._create_asset_from_resource(db, caller, resource, procurement)
            
            return resource
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(CanonicalResource).where(
                    CanonicalResource.organization_id == caller.organization_id,
                    CanonicalResource.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def _create_asset_from_resource(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        resource: CanonicalResource,
        procurement: ProcurementRecord,
    ) -> Optional[CanonicalAsset]:
        """Create a CanonicalAsset from a resource created from procurement."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "resource_id": resource.id,
                "procurement_id": procurement.id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(CanonicalAsset).where(
                CanonicalAsset.organization_id == caller.organization_id,
                CanonicalAsset.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        asset_category = self._map_resource_category_to_asset(resource.category)
        
        asset = CanonicalAsset(
            organization_id=caller.organization_id,
            asset_category=asset_category,
            asset_type=resource.kind,
            name=resource.name,
            description=f"Created from procurement {procurement.id}",
            lifecycle_state="available",
            resource_id=resource.id,
            purchase_cost=procurement.actual_cost,
            current_value=procurement.actual_cost,
            currency=procurement.currency,
            budget_id=procurement.budget_id,
            procurement_id=procurement.id,
            vendor_id=procurement.vendor_id,
            vendor_name=procurement.vendor_name,
            received_at=utcnow(),
            created_by=caller.employee_id or "system",
            fingerprint=fingerprint,
        )
        
        db.add(asset)
        try:
            await db.flush()
            return asset
        except IntegrityError:
            await db.rollback()
            return None
    
    def _map_procurement_to_category(self, procurement_kind: str) -> str:
        mapping = {
            "purchase": "physical",
            "subscription": "digital",
            "contract": "external",
            "internal_transfer": "physical",
            "lease": "physical",
            "license": "software",
            "service": "external",
            "contingent": "external",
        }
        return mapping.get(procurement_kind, "physical")
    
    def _map_procurement_to_kind(self, procurement_kind: str, title: str) -> str:
        title_lower = title.lower()
        if "laptop" in title_lower or "computer" in title_lower:
            return "equipment"
        elif "server" in title_lower:
            return "server"
        elif "license" in title_lower:
            return "perpetual_license"
        elif "subscription" in title_lower or "saas" in title_lower:
            return "saas_license"
        elif "cloud" in title_lower:
            return "cloud_compute"
        elif "gpu" in title_lower:
            return "gpu_capacity"
        elif "storage" in title_lower:
            return "cloud_storage"
        return "equipment"
    
    def _map_resource_category_to_asset(self, resource_category: str) -> str:
        mapping = {
            "physical": "hardware",
            "digital": "software",
            "infrastructure": "facility",
            "software": "software",
            "human": "hardware",  # not typical but fallback
        }
        return mapping.get(resource_category, "hardware")
    
    def _estimate_capacity_from_procurement(self, procurement: ProcurementRecord) -> float:
        """Estimate capacity units from procurement."""
        # ProcurementRecord uses estimated_cost/actual_cost instead of quantity
        if procurement.actual_cost and procurement.actual_cost > 0:
            return max(1.0, procurement.actual_cost / 1000.0)
        if procurement.estimated_cost and procurement.estimated_cost > 0:
            return max(1.0, procurement.estimated_cost / 1000.0)
        return 1.0
    
    def _get_unit_for_kind(self, kind: str) -> str:
        unit_map = {
            "employee_capacity": "fte",
            "contractor_capacity": "fte",
            "specialist_availability": "hours",
            "leadership_capacity": "fte",
            "equipment": "units",
            "machinery": "units",
            "vehicles": "units",
            "facilities": "sqft",
            "lab_space": "sqft",
            "office_space": "sqft",
            "cloud_compute": "cpu-hr",
            "cloud_storage": "gb",
            "gpu_capacity": "gpu-hr",
            "database_capacity": "gb",
            "network_bandwidth": "mbps",
            "k8s_cluster": "nodes",
            "ci_cd_capacity": "minutes",
            "saas_license": "seats",
            "perpetual_license": "seats",
            "subscription_seat": "seats",
            "api_quota": "requests",
            "server": "units",
            "rack_space": "rack-units",
            "power_capacity": "kw",
            "cooling_capacity": "tons",
            "budget_allocation": "usd",
            "funding_reserve": "usd",
            "capital_expenditure": "usd",
            "engineering_capability": "fte",
            "sales_capability": "fte",
            "legal_capability": "fte",
            "manufacturing_capability": "units",
            "vendor_capacity": "fte",
            "partner_capacity": "fte",
            "contractor_pool": "fte",
        }
        return unit_map.get(kind, "units")
    
    # ================================================================
    # 6. GATE 14 CUSTOMER INTEGRATION
    # ================================================================
    
    async def derive_customer_resource_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        customer_id: str,
    ) -> Dict[str, Any]:
        """
        Derive resource impact for a specific customer.
        
        Connects:
        Customer → Commitments → Projects → Demands → Resources → Allocations
        """
        # Verify access
        customer = await db.get(Customer, customer_id)
        if not customer or customer.organization_id != caller.organization_id:
            raise ValueError("Customer not found or access denied")
        
        # Get customer commitments
        commitments = await db.execute(
            select(CustomerCommitment).where(
                CustomerCommitment.organization_id == caller.organization_id,
                CustomerCommitment.customer_id == customer_id,
            )
        )
        commitments = list(commitments.scalars().all())
        
        # Get project links
        project_links = await db.execute(
            select(CustomerProjectLink).where(
                CustomerProjectLink.organization_id == caller.organization_id,
                CustomerProjectLink.customer_id == customer_id,
            )
        )
        project_ids = [pl.project_id for pl in project_links.scalars().all()]
        
        # Get resource demands for these projects/commitments
        demand_results = []
        for cid in [c.id for c in commitments]:
            demands = await db.execute(
                select(ResourceDemand).where(
                    ResourceDemand.organization_id == caller.organization_id,
                    ResourceDemand.source_type == "commitment",
                    ResourceDemand.source_id == cid,
                )
            )
            demand_results.extend(demands.scalars().all())
        
        for pid in project_ids:
            demands = await db.execute(
                select(ResourceDemand).where(
                    ResourceDemand.organization_id == caller.organization_id,
                    ResourceDemand.source_type == "project",
                    ResourceDemand.source_id == pid,
                )
            )
            demand_results.extend(demands.scalars().all())
        
        # Get allocations for these demands
        allocation_results = []
        for d in demand_results:
            allocs = await db.execute(
                select(ResourceAllocation).where(
                    ResourceAllocation.organization_id == caller.organization_id,
                    ResourceAllocation.demand_id == d.id,
                )
            )
            allocation_results.extend(allocs.scalars().all())
        
        # Get resources
        resource_ids = set(a.resource_id for a in allocation_results)
        resources = []
        for rid in resource_ids:
            r = await db.get(CanonicalResource, rid)
            if r:
                resources.append(r)
        
        # Get assets
        assets = []
        for alloc in allocation_results:
            resource = await db.get(CanonicalResource, alloc.resource_id)
            if resource and resource.resource_identity:
                asset = await db.execute(
                    select(CanonicalAsset).where(
                        CanonicalAsset.organization_id == caller.organization_id,
                        CanonicalAsset.resource_id == resource.id,
                    )
                )
                asset = asset.scalars().first()
                if asset:
                    assets.append(asset)
        
        return {
            "customer_id": customer_id,
            "customer_name": customer.company_name,
            "commitments": len(commitments),
            "projects": len(project_ids),
            "demands": len(demand_results),
            "unfulfilled_demands": sum(1 for d in demand_results if not d.is_fulfilled),
            "allocations": len(allocation_results),
            "active_allocations": sum(1 for a in allocation_results if a.state == "active"),
            "resources": len(resources),
            "assets": len(assets),
            "capacity_committed": sum(a.units_allocated for a in allocation_results),
            "utilization": sum(
                a.actual_utilization or 0 for a in allocation_results
            ) / sum(a.units_allocated for a in allocation_results) if allocation_results else 0,
            "critical_assets": sum(1 for a in assets if a.is_critical),
        }
    
    # ================================================================
    # 7. GATE 13 STRATEGIC ALIGNMENT INTEGRATION
    # =============================================================================
    
    async def trace_resource_to_strategy(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        resource_id: str,
    ) -> Dict[str, Any]:
        """
        Trace a resource back through allocations → demands → projects/commitments
        → objectives → initiatives → strategic intents.
        """
        resource = await db.get(CanonicalResource, resource_id)
        if not resource or resource.organization_id != caller.organization_id:
            raise ValueError("Resource not found or access denied")
        
        # Get allocations for this resource
        allocations = await db.execute(
            select(ResourceAllocation).where(
                ResourceAllocation.organization_id == caller.organization_id,
                ResourceAllocation.resource_id == resource_id,
            )
        )
        allocations = list(allocations.scalars().all())
        
        trace = {
            "resource": {
                "id": resource.id,
                "name": resource.name,
                "category": resource.category,
                "kind": resource.kind,
            },
            "allocations": [],
            "demands": [],
            "projects": [],
            "commitments": [],
            "objectives": [],
            "initiatives": [],
        }
        
        for alloc in allocations:
            alloc_trace = {
                "id": alloc.id,
                "target_type": alloc.target_type,
                "target_id": alloc.target_id,
                "units": alloc.units_allocated,
                "state": alloc.state,
            }
            
            # Trace demand
            if alloc.demand_id:
                demand = await db.get(ResourceDemand, alloc.demand_id)
                if demand:
                    alloc_trace["demand"] = {
                        "id": demand.id,
                        "source_type": demand.source_type,
                        "source_id": demand.source_id,
                        "units_requested": demand.units_requested,
                    }
                    
                    # Trace to source entity
                    if demand.source_type == "project":
                        project = await db.get(Project, demand.source_id)
                        if project:
                            alloc_trace["project"] = {"id": project.id, "name": project.name}
                            trace["projects"].append(alloc_trace["project"])
                            
                            # Get objectives via strategic alignment
                            alignment = await strategic_alignment_engine.trace_backward(
                                db, caller=caller,
                                entity_type="project", entity_id=project.id
                            )
                            if "chain" in alignment:
                                for link in alignment["chain"]:
                                    if link.get("to_type") == "objective":
                                        obj = await db.get(CompanyObjective, link.get("to_id"))
                                        if obj:
                                            trace["objectives"].append({"id": obj.id, "title": obj.title})
                                    elif link.get("to_type") == "initiative":
                                        init = await db.get(CompanyInitiative, link.get("to_id"))
                                        if init:
                                            trace["initiatives"].append({"id": init.id, "title": init.title})
                    
                    elif demand.source_type == "commitment":
                        commitment = await db.get(CompanyCommitment, demand.source_id)
                        if commitment:
                            alloc_trace["commitment"] = {"id": commitment.id, "title": commitment.title}
                            trace["commitments"].append(alloc_trace["commitment"])
                            
                            # Trace commitment to objective
                            if commitment.objective_id:
                                obj = await db.get(CompanyObjective, commitment.objective_id)
                                if obj:
                                    trace["objectives"].append({"id": obj.id, "title": obj.title})
            
            trace["allocations"].append(alloc_trace)
        
        return trace
    
    # ================================================================
    # 8. GATE 10 PREDICTION INTEGRATION
    # ================================================================
    
    async def predict_resource_capacity_pressure(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        resource_kind: Optional[str] = None,
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Predict resource capacity pressure using Gate 10 predictive intelligence.
        
        This leverages existing predictive_intelligence_service rather than
        creating a new prediction engine.
        """
        # Get current resource state
        resources = await self._get_resources(db, caller)
        if resource_kind:
            resources = [r for r in resources if r.kind == resource_kind]
        
        # Get future demands
        future_date = date.today()
        from datetime import timedelta
        future_end = future_date + timedelta(days=horizon_days)
        
        demands = await db.execute(
            select(ResourceDemand).where(
                ResourceDemand.organization_id == caller.organization_id,
                ResourceDemand.window_start <= future_end,
                ResourceDemand.window_end >= future_date,
            )
        )
        demands = list(demands.scalars().all())
        if resource_kind:
            demands = [d for d in demands if d.resource_kind == resource_kind]
        
        # Compute projected capacity vs demand
        projections = []
        for resource in resources:
            resource_demands = [d for d in demands if d.resource_kind == resource.kind]
            total_demand = sum(d.units_remaining for d in resource_demands)
            
            projected_available = resource.available_capacity - total_demand
            projected_utilization = (resource.committed_capacity + total_demand) / resource.total_capacity if resource.total_capacity > 0 else 0
            
            risk_level = "low"
            if projected_utilization > 1.0:
                risk_level = "critical"
            elif projected_utilization > 0.8:
                risk_level = "high"
            elif projected_utilization > 0.6:
                risk_level = "medium"
            
            projections.append({
                "resource_id": resource.id,
                "resource_name": resource.name,
                "kind": resource.kind,
                "current_available": resource.available_capacity,
                "projected_demand": total_demand,
                "projected_available": projected_available,
                "projected_utilization": projected_utilization,
                "risk_level": risk_level,
                "unfulfilled_demands": len([d for d in resource_demands if not d.is_fulfilled]),
            })
        
        return {
            "horizon_days": horizon_days,
            "resource_kind": resource_kind,
            "projections": projections,
            "overall_risk": max((p["risk_level"] for p in projections), default="low"),
        }
    
    # ================================================================
    # 9. GATE 11/12 COUNTERFACTUAL/DIGITAL TWIN INTEGRATION
    # ================================================================
    
    async def create_resource_scenario(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_name: str,
        resource_changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create a counterfactual scenario with resource changes.
        
        Uses Gate 11 counterfactual infrastructure.
        """
        # Build scenario changes for counterfactual engine
        changes = []
        for rc in resource_changes:
            if rc.get("type") == "add_resource":
                changes.append({
                    "kind": "capacity_change",
                    "subject_type": "resource",
                    "subject_id": rc.get("resource_id", "new"),
                    "params": {
                        "resource_kind": rc.get("resource_kind"),
                        "delta_capacity": rc.get("capacity", 1),
                    },
                })
            elif rc.get("type") == "remove_resource":
                changes.append({
                    "kind": "capacity_change",
                    "subject_type": "resource",
                    "subject_id": rc.get("resource_id"),
                    "params": {
                        "resource_kind": rc.get("resource_kind"),
                        "delta_capacity": -rc.get("capacity", 1),
                    },
                })
            elif rc.get("type") == "reallocate":
                changes.append({
                    "kind": "allocation_change",
                    "subject_type": "allocation",
                    "subject_id": rc.get("allocation_id"),
                    "params": {
                        "new_target_type": rc.get("new_target_type"),
                        "new_target_id": rc.get("new_target_id"),
                    },
                })
        
        # Use counterfactual service
        from app.intelligence.counterfactual_intelligence_service import (
            counterfactual_intelligence_service,
        )
        
        result = await counterfactual_intelligence_service.create_scenario(
            db,
            caller=caller,
            scenario_kind="resource_scenario",
            subject_type="resource",
            subject_id=scenario_name,
            params={"changes": changes, "scenario_name": scenario_name},
            dry_run=False,
        )
        
        return result
    
    # ================================================================
    # 10. CONFLICT DERIVATION (feeds Operating Attention)
    # ================================================================
    
    async def derive_resource_conflicts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[ResourceConflict]:
        """
        Derive all current resource conflicts.
        
        This feeds into the existing Operating Attention architecture (Gate 13).
        Do NOT create a parallel attention system.
        """
        conflicts = []
        
        # 1. Double allocation detection
        double_allocs = await db.execute(
            select(ResourceAllocation.resource_id, func.count(ResourceAllocation.id)).where(
                ResourceAllocation.organization_id == caller.organization_id,
                ResourceAllocation.state == "active",
            ).group_by(ResourceAllocation.resource_id).having(func.count(ResourceAllocation.id) > 1)
        )
        for resource_id, count in double_allocs.all():
            resource = await db.get(CanonicalResource, resource_id)
            conflict = ResourceConflict(
                organization_id=caller.organization_id,
                conflict_kind="double_allocation",
                severity="critical",
                status="open",
                resource_id=resource_id,
                resource_kind=resource.kind if resource else None,
                title=f"Resource allocated to {count} targets simultaneously",
                description=f"Resource {resource.name if resource else resource_id} has {count} active allocations",
                detected_at=utcnow(),
                detected_by="system",
                detection_method="derived",
                fingerprint=hashlib.sha256(
                    json.dumps({"kind": "double_allocation", "resource_id": resource_id}, sort_keys=True).encode()
                ).hexdigest()[:64],
            )
            db.add(conflict)
            conflicts.append(conflict)
        
        # 2. Capacity overload
        resources = await self._get_resources(db, caller)
        for resource in resources:
            if resource.is_constrained:
                conflict = ResourceConflict(
                    organization_id=caller.organization_id,
                    conflict_kind="capacity_overload",
                    severity="critical",
                    status="open",
                    resource_id=resource.id,
                    resource_kind=resource.kind,
                    title=f"Resource {resource.name} ({resource.kind}) over capacity",
                    description=f"Available: {resource.available_capacity}, Committed: {resource.committed_capacity}, Total: {resource.total_capacity}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "capacity_overload", "resource_id": resource.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                )
                db.add(conflict)
                conflicts.append(conflict)
        
        # 3. Underutilization
        allocations = await self._get_allocations(db, caller)
        for alloc in allocations:
            if alloc.state == "active" and alloc.actual_utilization is not None:
                if alloc.actual_utilization < alloc.units_allocated * 0.3:
                    conflict = ResourceConflict(
                        organization_id=caller.organization_id,
                        conflict_kind="underutilization",
                        severity="warning",
                        status="open",
                        resource_id=alloc.resource_id,
                        affected_allocation_ids=[alloc.id],
                        title=f"Allocation {alloc.id} underutilized",
                        description=f"Allocated: {alloc.units_allocated}, Actual: {alloc.actual_utilization}",
                        detected_at=utcnow(),
                        detected_by="system",
                        detection_method="derived",
                        fingerprint=hashlib.sha256(
                            json.dumps({"kind": "underutilization", "allocation_id": alloc.id}, sort_keys=True).encode()
                        ).hexdigest()[:64],
                    )
                    db.add(conflict)
                    conflicts.append(conflict)
        
        # 4. Procurement gaps (demands unfulfilled for extended period)
        demands = await self._get_demands(db, caller)
        for demand in demands:
            if not demand.is_fulfilled and demand.window_start < date.today():
                conflict = ResourceConflict(
                    organization_id=caller.organization_id,
                    conflict_kind="procurement_gap",
                    severity="high",
                    status="open",
                    resource_kind=demand.resource_kind,
                    affected_demand_ids=[demand.id],
                    title=f"Demand for {demand.resource_kind} unfulfilled past window start",
                    description=f"Source: {demand.source_type} {demand.source_id}, Needed: {demand.units_remaining}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "procurement_gap", "demand_id": demand.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                )
                db.add(conflict)
                conflicts.append(conflict)
        
        # 5. Asset lifecycle risks
        assets = await self._get_assets(db, caller)
        for asset in assets:
            if asset.is_approaching_maintenance:
                conflict = ResourceConflict(
                    organization_id=caller.organization_id,
                    conflict_kind="lifecycle_risk",
                    severity="warning",
                    status="open",
                    resource_id=asset.resource_id,
                    resource_kind=asset.asset_category,
                    title=f"Asset {asset.name} approaching maintenance",
                    description=f"Next maintenance: {asset.next_maintenance_at}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "lifecycle_risk", "asset_id": asset.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                )
                db.add(conflict)
                conflicts.append(conflict)
        
        await db.flush()
        return conflicts


# Global instance
canonical_resource_asset_service = CanonicalResourceAssetService()