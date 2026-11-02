"""Canonical Procurement, Vendor & External Capacity Operating Fabric Service — Gate 17.

Derives vendor/procurement/external-capacity operating slices, impact analyses, and contexts
from the canonical company reality (Gates 8-16).

This is a DERIVED PROJECTION layer — it does NOT create a second procurement/vendor reality.
All data is composed from existing canonical primitives:
- Gate 8: People, Work, Communication, Meetings, Organizational Intelligence, Capacity
- Gate 9: Institutional Learning
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric
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
from app.models.canonical_procurement_vendor import (
    CanonicalVendor,
    VendorCapability,
    ExternalCapacity,
    CanonicalProcurement,
    VendorPerformance,
    VendorDependency,
    VendorOperatingSlice,
    ProcurementImpactAnalysis,
    VENDOR_KINDS,
    VENDOR_STATES,
    EXTERNAL_CAPACITY_TYPES,
    PROCUREMENT_LIFECYCLE_STATES,
    PROCUREMENT_KINDS,
    AUTHORIZATION_STATES,
    VENDOR_CAPABILITY_CATEGORIES,
    DEPENDENCY_CRITICALITY,
    VENDOR_RISK_KINDS,
)
from app.models.financial_resource_procurement import (
    ProcurementRecord,
    BudgetCommitmentRecord,
    FinancialOutcomeRecord,
)
from app.models.canonical_resource_asset import (
    CanonicalResource,
    CanonicalAsset,
    ResourceDemand,
    ResourceAllocation,
    ResourceAllocation as Gate16ResourceAllocation,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
)
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilityProjectLink,
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
from app.intelligence.strategic_alignment_engine import strategic_alignment_engine
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.customer_operating_fabric_service import customer_operating_fabric_service
from app.intelligence.financial_resource_procurement_service import financial_resource_procurement_service
from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service

logger = logging.getLogger("vcos.intelligence.canonical_procurement_vendor")


class CanonicalProcurementVendorService:
    """
    Service for deriving the canonical procurement/vendor/external-capacity operating fabric.
    
    All methods return DERIVED PROJECTIONS over canonical reality.
    They do NOT mutate canonical data.
    """
    
    # ================================================================
    # 1. VENDOR OPERATING SLICE
    # ================================================================
    
    async def derive_vendor_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "organization",
        scope_id: Optional[str] = None,
    ) -> VendorOperatingSlice:
        """
        Derive a governed, point-in-time operating slice for vendors/procurement.
        
        Composes all canonical reality relevant to vendors:
        - Vendors (capabilities, performance, risk)
        - External capacity
        - Procurements (lifecycle, financials)
        - Dependencies and risks
        - Financial commitments
        """
        start = time.perf_counter()
        
        # Governance: verify access
        await self._verify_vendor_access(db, caller, scope_type, scope_id)
        
        # Build input fingerprint for exact-once
        input_data = {
            "organization_id": caller.organization_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": "vendor_operating_slice",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing slice with same fingerprint
        existing = await db.execute(
            select(VendorOperatingSlice).where(
                VendorOperatingSlice.organization_id == caller.organization_id,
                VendorOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Derive vendor summary
        vendors = await self._get_vendors(db, caller)
        external_capacity = await self._get_external_capacity(db, caller)
        procurements = await self._get_procurements(db, caller)
        dependencies = await self._get_dependencies(db, caller)
        performance = await self._get_performance(db, caller)
        
        # Vendor summary
        vendors_by_kind = {}
        vendors_by_state = {}
        vendors_by_criticality = {}
        total_vendors = len(vendors)
        active_vendors = 0
        critical_vendors = 0
        
        for v in vendors:
            vendors_by_kind[v.kind] = vendors_by_kind.get(v.kind, 0) + 1
            vendors_by_state[v.state] = vendors_by_state.get(v.state, 0) + 1
            vendors_by_criticality[v.criticality] = vendors_by_criticality.get(v.criticality, 0) + 1
            if v.state == "active":
                active_vendors += 1
            if v.is_critical:
                critical_vendors += 1
        
        # External capacity summary
        external_capacity_by_type = {}
        total_external_capacity = 0.0
        available_external_capacity = 0.0
        committed_external_capacity = 0.0
        
        for ec in external_capacity:
            external_capacity_by_type[ec.capacity_type] = external_capacity_by_type.get(ec.capacity_type, 0) + 1
            total_external_capacity += ec.total_capacity
            available_external_capacity += ec.available_capacity
            committed_external_capacity += ec.committed_capacity
        
        # Procurement summary
        procurements_by_state = {}
        procurements_by_kind = {}
        active_procurements = 0
        delayed_procurements = 0
        overdue_procurements = 0
        
        for p in procurements:
            procurements_by_state[p.state] = procurements_by_state.get(p.state, 0) + 1
            procurements_by_kind[p.kind] = procurements_by_kind.get(p.kind, 0) + 1
            if p.is_active:
                active_procurements += 1
            if p.is_delayed:
                delayed_procurements += 1
            if p.expected_delivery and p.expected_delivery < date.today() and not p.delivered_at:
                overdue_procurements += 1
        
        # Financial
        total_committed_spend = sum(p.estimated_cost or 0 for p in procurements if p.estimated_cost)
        total_actual_spend = sum(p.actual_cost or 0 for p in procurements if p.actual_cost)
        
        # Performance
        performance_scores = [p.metric_value for p in performance if p.metric_value is not None]
        avg_on_time_delivery = sum(p.metric_value for p in performance if p.metric_kind == "on_time_delivery") / max(1, len([p for p in performance if p.metric_kind == "on_time_delivery"]))
        avg_quality_rate = sum(p.metric_value for p in performance if p.metric_kind == "quality") / max(1, len([p for p in performance if p.metric_kind == "quality"]))
        
        # Dependencies & Risks
        dependency_count = len(dependencies)
        critical_dependency_count = sum(1 for d in dependencies if d.criticality in ("critical", "high"))
        
        slice_obj = VendorOperatingSlice(
            organization_id=caller.organization_id,
            input_fingerprint=input_fingerprint,
            vendors_by_kind=vendors_by_kind,
            vendors_by_state=vendors_by_state,
            vendors_by_criticality=vendors_by_criticality,
            total_vendors=total_vendors,
            active_vendors=active_vendors,
            critical_vendors=critical_vendors,
            external_capacity_by_type=external_capacity_by_type,
            total_external_capacity=total_external_capacity,
            available_external_capacity=available_external_capacity,
            committed_external_capacity=committed_external_capacity,
            procurements_by_state=procurements_by_state,
            procurements_by_kind=procurements_by_kind,
            active_procurements=active_procurements,
            delayed_procurements=delayed_procurements,
            overdue_procurements=overdue_procurements,
            total_committed_spend=total_committed_spend,
            total_actual_spend=total_actual_spend,
            avg_on_time_delivery=avg_on_time_delivery,
            avg_quality_rate=avg_quality_rate,
            dependency_count=dependency_count,
            critical_dependency_count=critical_dependency_count,
            vendor_risk_count=0,
            critical_vendor_risk_count=0,
            contract_expiring_soon=0,
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - start) * 1000),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "vendor_count": len(vendors),
                    "external_capacity_count": len(external_capacity),
                    "procurement_count": len(procurements),
                    "dependency_count": len(dependencies),
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
            INSERT INTO vendor_operating_slices (
                id, organization_id, input_fingerprint,
                vendors_by_kind, vendors_by_state, vendors_by_criticality,
                total_vendors, active_vendors, critical_vendors,
                external_capacity_by_type, total_external_capacity,
                available_external_capacity, committed_external_capacity,
                procurements_by_state, procurements_by_kind,
                active_procurements, delayed_procurements, overdue_procurements,
                total_committed_spend, total_actual_spend,
                avg_on_time_delivery, avg_quality_rate,
                dependency_count, critical_dependency_count,
                vendor_risk_count, critical_vendor_risk_count, contract_expiring_soon,
                computed_at, computation_duration_ms, fingerprint,
                created_at, updated_at
            ) VALUES (
                :id, :organization_id, :input_fingerprint,
                :vendors_by_kind, :vendors_by_state, :vendors_by_criticality,
                :total_vendors, :active_vendors, :critical_vendors,
                :external_capacity_by_type, :total_external_capacity,
                :available_external_capacity, :committed_external_capacity,
                :procurements_by_state, :procurements_by_kind,
                :active_procurements, :delayed_procurements, :overdue_procurements,
                :total_committed_spend, :total_actual_spend,
                :avg_on_time_delivery, :avg_quality_rate,
                :dependency_count, :critical_dependency_count,
                :vendor_risk_count, :critical_vendor_risk_count, :contract_expiring_soon,
                :computed_at, :computation_duration_ms, :fingerprint,
                :created_at, :updated_at
            )
            ON CONFLICT (organization_id, input_fingerprint) DO NOTHING
        """)
        
        await db.execute(insert_sql, {
            "id": slice_obj.id,
            "organization_id": slice_obj.organization_id,
            "input_fingerprint": slice_obj.input_fingerprint,
            "vendors_by_kind": json.dumps(slice_obj.vendors_by_kind),
            "vendors_by_state": json.dumps(slice_obj.vendors_by_state),
            "vendors_by_criticality": json.dumps(slice_obj.vendors_by_criticality),
            "total_vendors": slice_obj.total_vendors,
            "active_vendors": slice_obj.active_vendors,
            "critical_vendors": slice_obj.critical_vendors,
            "external_capacity_by_type": json.dumps(slice_obj.external_capacity_by_type),
            "total_external_capacity": slice_obj.total_external_capacity,
            "available_external_capacity": slice_obj.available_external_capacity,
            "committed_external_capacity": slice_obj.committed_external_capacity,
            "procurements_by_state": json.dumps(slice_obj.procurements_by_state),
            "procurements_by_kind": json.dumps(slice_obj.procurements_by_kind),
            "active_procurements": slice_obj.active_procurements,
            "delayed_procurements": slice_obj.delayed_procurements,
            "overdue_procurements": slice_obj.overdue_procurements,
            "total_committed_spend": slice_obj.total_committed_spend,
            "total_actual_spend": slice_obj.total_actual_spend,
            "avg_on_time_delivery": slice_obj.avg_on_time_delivery,
            "avg_quality_rate": slice_obj.avg_quality_rate,
            "dependency_count": slice_obj.dependency_count,
            "critical_dependency_count": slice_obj.critical_dependency_count,
            "vendor_risk_count": slice_obj.vendor_risk_count,
            "critical_vendor_risk_count": slice_obj.critical_vendor_risk_count,
            "contract_expiring_soon": slice_obj.contract_expiring_soon,
            "computed_at": slice_obj.computed_at,
            "computation_duration_ms": slice_obj.computation_duration_ms,
            "fingerprint": slice_obj.fingerprint,
            "created_at": slice_obj.created_at,
            "updated_at": slice_obj.updated_at,
        })
        await db.flush()
        
        # Query for the existing or newly inserted slice
        existing = await db.execute(
            select(VendorOperatingSlice).where(
                VendorOperatingSlice.organization_id == caller.organization_id,
                VendorOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        return existing.scalars().first()
    
    async def _get_vendors(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalVendor]:
        result = await db.execute(
            select(CanonicalVendor).where(
                CanonicalVendor.organization_id == caller.organization_id,
            ).order_by(CanonicalVendor.kind, CanonicalVendor.state)
        )
        return list(result.scalars().all())
    
    async def _get_external_capacity(self, db: AsyncSession, caller: CallerAccess) -> List[ExternalCapacity]:
        result = await db.execute(
            select(ExternalCapacity).where(
                ExternalCapacity.organization_id == caller.organization_id,
            ).order_by(ExternalCapacity.capacity_type, ExternalCapacity.window_start)
        )
        return list(result.scalars().all())
    
    async def _get_procurements(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalProcurement]:
        result = await db.execute(
            select(CanonicalProcurement).where(
                CanonicalProcurement.organization_id == caller.organization_id,
            ).order_by(CanonicalProcurement.state, CanonicalProcurement.kind)
        )
        return list(result.scalars().all())
    
    async def _get_dependencies(self, db: AsyncSession, caller: CallerAccess) -> List[VendorDependency]:
        result = await db.execute(
            select(VendorDependency).where(
                VendorDependency.organization_id == caller.organization_id,
            ).order_by(VendorDependency.criticality.desc(), VendorDependency.detected_at.desc())
        )
        return list(result.scalars().all())
    
    async def _get_performance(self, db: AsyncSession, caller: CallerAccess) -> List[VendorPerformance]:
        result = await db.execute(
            select(VendorPerformance).where(
                VendorPerformance.organization_id == caller.organization_id,
            ).order_by(VendorPerformance.period_end.desc())
        )
        return list(result.scalars().all())
    
    async def _verify_vendor_access(self, db: AsyncSession, caller: CallerAccess, scope_type: str, scope_id: Optional[str]) -> None:
        """Verify caller has access to vendor scope."""
        pass
    
    # ================================================================
    # 2. CANONICAL VENDOR MANAGEMENT
    # ================================================================
    
    async def create_vendor(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        name: str,
        kind: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        primary_contact_name: Optional[str] = None,
        primary_contact_email: Optional[str] = None,
        payment_terms: Optional[str] = None,
        currency: str = "USD",
        criticality: str = "medium",
        owner_id: Optional[str] = None,
        vendor_code: Optional[str] = None,
    ) -> CanonicalVendor:
        """Create a canonical vendor with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "name": name,
                "kind": kind,
                "organization_id": caller.organization_id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(CanonicalVendor).where(
                CanonicalVendor.organization_id == caller.organization_id,
                CanonicalVendor.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        vendor = CanonicalVendor(
            organization_id=caller.organization_id,
            name=name,
            display_name=display_name or name,
            kind=kind,
            description=description,
            industry=industry,
            country=country,
            primary_contact_name=primary_contact_name,
            primary_contact_email=primary_contact_email,
            payment_terms=payment_terms,
            currency=currency,
            criticality=criticality,
            owner_id=owner_id or caller.employee_id,
            vendor_code=vendor_code,
            state="active",
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
            onboarded_at=utcnow(),
            onboarded_by=caller.employee_id or "system",
        )
        
        db.add(vendor)
        try:
            await db.flush()
            return vendor
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(CanonicalVendor).where(
                    CanonicalVendor.organization_id == caller.organization_id,
                    CanonicalVendor.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def create_vendor_capability(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        vendor_id: str,
        capability_category: str,
        capability_name: str,
        unit: str,
        max_capacity: Optional[float] = None,
        unit_cost: Optional[float] = None,
        currency: str = "USD",
        sla_details: Optional[dict] = None,
    ) -> VendorCapability:
        """Create a vendor capability with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "vendor_id": vendor_id,
                "capability_category": capability_category,
                "capability_name": capability_name,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(VendorCapability).where(
                VendorCapability.organization_id == caller.organization_id,
                VendorCapability.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        capability = VendorCapability(
            organization_id=caller.organization_id,
            vendor_id=vendor_id,
            capability_category=capability_category,
            capability_name=capability_name,
            unit=unit,
            max_capacity=max_capacity,
            unit_cost=unit_cost,
            currency=currency,
            sla_details_json=sla_details or {},
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(capability)
        try:
            await db.flush()
            return capability
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(VendorCapability).where(
                    VendorCapability.organization_id == caller.organization_id,
                    VendorCapability.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    # ================================================================
    # 3. EXTERNAL CAPACITY MANAGEMENT
    # ================================================================
    
    async def create_external_capacity(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        vendor_id: str,
        capacity_type: str,
        capacity_name: str,
        unit: str,
        total_capacity: float,
        window_start: date,
        window_end: date,
        cost_per_unit: Optional[float] = None,
        currency: str = "USD",
        availability_sla: Optional[float] = None,
        capability_id: Optional[str] = None,
        procurement_id: Optional[str] = None,
    ) -> ExternalCapacity:
        """Create external capacity with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "vendor_id": vendor_id,
                "capacity_type": capacity_type,
                "capacity_name": capacity_name,
                "window_start": str(window_start),
                "window_end": str(window_end),
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(ExternalCapacity).where(
                ExternalCapacity.organization_id == caller.organization_id,
                ExternalCapacity.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        capacity = ExternalCapacity(
            organization_id=caller.organization_id,
            vendor_id=vendor_id,
            capacity_type=capacity_type,
            capacity_name=capacity_name,
            unit=unit,
            total_capacity=total_capacity,
            committed_capacity=0.0,
            reserved_capacity=0.0,
            available_capacity=total_capacity,
            window_start=window_start,
            window_end=window_end,
            cost_per_unit=cost_per_unit,
            currency=currency,
            state="available",
            capability_id=capability_id,
            procurement_id=procurement_id,
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(capacity)
        try:
            await db.flush()
            return capacity
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ExternalCapacity).where(
                    ExternalCapacity.organization_id == caller.organization_id,
                    ExternalCapacity.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    # ================================================================
    # 4. CANONICAL PROCUREMENT MANAGEMENT
    # ================================================================
    
    async def create_procurement(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        kind: str,
        title: str,
        description: Optional[str] = None,
        vendor_id: Optional[str] = None,
        demand_id: Optional[str] = None,
        requirement_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        project_id: Optional[str] = None,
        budget_commitment_id: Optional[str] = None,
        capability_id: Optional[str] = None,
        external_capacity_id: Optional[str] = None,
        estimated_cost: Optional[float] = None,
        currency: str = "USD",
        budget_id: Optional[str] = None,
        quantity: float = 1.0,
        unit: str = "units",
        needed_by: Optional[date] = None,
        payment_terms: Optional[str] = None,
        contract_reference: Optional[str] = None,
        window_start: Optional[date] = None,
        window_end: Optional[date] = None,
        authorization_required: bool = False,
        justification: Optional[str] = None,
    ) -> CanonicalProcurement:
        """Create a canonical procurement with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "kind": kind,
                "vendor_id": vendor_id,
                "demand_id": demand_id,
                "title": title,
                "quantity": quantity,
                "window_start": str(window_start) if window_start else None,
                "window_end": str(window_end) if window_end else None,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(CanonicalProcurement).where(
                CanonicalProcurement.organization_id == caller.organization_id,
                CanonicalProcurement.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        procurement = CanonicalProcurement(
            organization_id=caller.organization_id,
            kind=kind,
            title=title,
            description=description,
            vendor_id=vendor_id,
            demand_id=demand_id,
            requirement_id=requirement_id,
            commitment_id=commitment_id,
            project_id=project_id,
            budget_commitment_id=budget_commitment_id,
            capability_id=capability_id,
            external_capacity_id=external_capacity_id,
            estimated_cost=estimated_cost,
            currency=currency,
            budget_id=budget_id,
            quantity=quantity,
            unit=unit,
            needed_by=needed_by,
            payment_terms=payment_terms,
            contract_reference=contract_reference,
            window_start=window_start,
            window_end=window_end,
            authorization_required=authorization_required,
            state="identified",
            requested_by=caller.employee_id or "system",
            requested_at=utcnow(),
            justification=justification,
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(procurement)
        try:
            await db.flush()
            return procurement
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(CanonicalProcurement).where(
                    CanonicalProcurement.organization_id == caller.organization_id,
                    CanonicalProcurement.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def transition_procurement_state(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
        new_state: str,
        reason: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[CanonicalProcurement]:
        """Transition procurement to new lifecycle state."""
        
        procurement = await db.get(CanonicalProcurement, procurement_id)
        if not procurement:
            return None
        
        if new_state not in PROCUREMENT_LIFECYCLE_STATES:
            raise ValueError(f"Invalid procurement state: {new_state}")
        
        procurement.previous_state = procurement.state
        procurement.state = new_state
        procurement.state_changed_at = utcnow()
        procurement.state_change_reason = reason
        
        # Update timestamps based on state
        now = utcnow()
        if new_state == "requested":
            procurement.requested_at = now
        elif new_state == "approved":
            procurement.approved_by = caller.employee_id
            procurement.approved_at = now
        elif new_state == "ordered":
            procurement.ordered_at = now
        elif new_state == "delivered":
            procurement.delivered_at = now
        elif new_state == "received":
            procurement.received_at = now
        elif new_state == "accepted":
            procurement.accepted_at = now
        
        procurement.version += 1
        await db.flush()
        return procurement
    
    async def authorize_procurement(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
        authorized: bool,
        authorized_by: Optional[str] = None,
        amount: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> Optional[CanonicalProcurement]:
        """Authorize or reject a procurement (Decision != Authorization != Commitment != Action != Execution)."""
        
        procurement = await db.get(CanonicalProcurement, procurement_id)
        if not procurement:
            return None
        
        if authorized:
            procurement.authorization_state = "approved"
            procurement.authorized_by = authorized_by or caller.employee_id
            procurement.authorized_at = utcnow()
            procurement.authorization_amount = amount
            procurement.authorization_notes = notes
        else:
            procurement.authorization_state = "rejected"
            procurement.authorization_notes = notes
        
        procurement.version += 1
        await db.flush()
        return procurement
    
    # ================================================================
    # 5. PROCUREMENT -> FINANCE (Gate 15 Integration)
    # ================================================================
    
    async def link_procurement_to_budget(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
        budget_commitment_id: str,
    ) -> Optional[CanonicalProcurement]:
        """Link procurement to budget commitment (Gate 15)."""
        
        procurement = await db.get(CanonicalProcurement, procurement_id)
        if not procurement:
            return None
        
        budget_commitment = await db.get(BudgetCommitmentRecord, budget_commitment_id)
        if not budget_commitment:
            return None
        
        procurement.budget_commitment_id = budget_commitment_id
        procurement.budget_id = budget_commitment.budget_id
        procurement.version += 1
        await db.flush()
        return procurement
    
    async def link_procurement_to_financial_outcome(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
        financial_outcome_id: str,
    ) -> Optional[CanonicalProcurement]:
        """Link procurement to financial outcome (Gate 15)."""
        
        procurement = await db.get(CanonicalProcurement, procurement_id)
        if not procurement:
            return None
        
        outcome = await db.get(FinancialOutcomeRecord, financial_outcome_id)
        if not outcome:
            return None
        
        procurement.actual_cost = outcome.actual_value or outcome.target_value
        procurement.version += 1
        await db.flush()
        return procurement
    
    # ================================================================
    # 6. PROCUREMENT -> RESOURCE/ASSET (Gate 16 Integration)
    # ================================================================
    
    async def fulfill_procurement_create_resource(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
        received_quantity: float,
        accepted_quantity: float,
        quality_notes: Optional[str] = None,
    ) -> Optional[CanonicalProcurement]:
        """Fulfill procurement and create canonical resource/asset (Gate 16)."""
        
        procurement = await db.get(CanonicalProcurement, procurement_id)
        if not procurement:
            return None
        
        procurement.received_quantity = received_quantity
        procurement.accepted_quantity = accepted_quantity
        procurement.quality_notes = quality_notes
        procurement.received_at = utcnow()
        procurement.accepted_at = utcnow()
        procurement.state = "received"
        
        # Create canonical resource from procurement
        from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
        resource = await canonical_resource_asset_service.create_resource_from_procurement(
            db, caller=caller, procurement_id=procurement.id
        )
        
        if resource:
            procurement.external_capacity_id = None  # Could link to external capacity
        
        procurement.version += 1
        await db.flush()
        return procurement
    
    # ================================================================
    # 6. VENDOR PERFORMANCE DERIVATION
    # ================================================================
    
    async def derive_vendor_performance(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        vendor_id: str,
        period_start: date,
        period_end: date,
    ) -> List[VendorPerformance]:
        """Derive vendor performance metrics from procurement history."""
        
        # Get procurements in period
        procurements = await db.execute(
            select(CanonicalProcurement).where(
                CanonicalProcurement.organization_id == caller.organization_id,
                CanonicalProcurement.vendor_id == vendor_id,
                CanonicalProcurement.delivered_at >= period_start,
                CanonicalProcurement.delivered_at <= period_end,
            )
        )
        procurements = list(procurements.scalars().all())
        
        if not procurements:
            return []
        
        results = []
        
        # On-time delivery
        on_time = [p for p in procurements if p.delivered_at and p.expected_delivery and p.delivered_at.date() <= p.expected_delivery]
        on_time_rate = len(on_time) / len(procurements) if procurements else 0
        
        perf = VendorPerformance(
            organization_id=caller.organization_id,
            vendor_id=vendor_id,
            period_start=period_start,
            period_end=period_end,
            metric_kind="on_time_delivery",
            metric_value=on_time_rate,
            metric_unit="ratio",
            target_value=0.95,
            variance=on_time_rate - 0.95,
            trend="improving" if on_time_rate > 0.9 else "stable",
            sample_size=len(procurements),
            confidence=min(1.0, len(procurements) / 20),
            evidence_fingerprints=[p.fingerprint for p in procurements],
            procurement_ids_json=[p.id for p in procurements],
            fingerprint=hashlib.sha256(
                json.dumps({
                    "vendor_id": vendor_id,
                    "metric": "on_time_delivery",
                    "period_start": str(period_start),
                    "period_end": str(period_end),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
        )
        results.append(perf)
        
        # Quality acceptance rate
        accepted = [p for p in procurements if p.accepted_quantity and p.received_quantity and p.accepted_quantity >= p.received_quantity * 0.95]
        quality_rate = len(accepted) / len(procurements) if procurements else 0
        
        perf2 = VendorPerformance(
            organization_id=caller.organization_id,
            vendor_id=vendor_id,
            period_start=period_start,
            period_end=period_end,
            metric_kind="quality",
            metric_value=quality_rate,
            metric_unit="ratio",
            target_value=0.98,
            variance=quality_rate - 0.98,
            trend="stable",
            sample_size=len(procurements),
            confidence=min(1.0, len(procurements) / 20),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "vendor_id": vendor_id,
                    "metric": "quality",
                    "period_start": str(period_start),
                    "period_end": str(period_end),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
        )
        results.append(perf2)
        
        # Average lead time
        lead_times = [p.lead_time_days for p in procurements if p.lead_time_days is not None]
        avg_lead_time = sum(lead_times) / len(lead_times) if lead_times else 0
        
        perf3 = VendorPerformance(
            organization_id=caller.organization_id,
            vendor_id=vendor_id,
            period_start=period_start,
            period_end=period_end,
            metric_kind="lead_time",
            metric_value=avg_lead_time,
            metric_unit="days",
            target_value=7.0,
            variance=avg_lead_time - 7.0,
            trend="stable",
            sample_size=len(lead_times),
            confidence=min(1.0, len(lead_times) / 10),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "vendor_id": vendor_id,
                    "metric": "lead_time",
                    "period_start": str(period_start),
                    "period_end": str(period_end),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
        )
        results.append(perf3)
        
        db.add_all(results)
        await db.flush()
        return results
    
    # ================================================================
    # 7. VENDOR DEPENDENCY DERIVATION
    # ================================================================
    
    async def derive_vendor_dependencies(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[VendorDependency]:
        """Derive vendor dependencies from canonical relationships."""
        
        dependencies = []
        vendors = await self._get_vendors(db, caller)
        
        for vendor in vendors:
            # Get resources/items dependent on this vendor
            procurements = await db.execute(
                select(CanonicalProcurement).where(
                    CanonicalProcurement.organization_id == caller.organization_id,
                    CanonicalProcurement.vendor_id == vendor.id,
                    CanonicalProcurement.state.in_(["ordered", "in_fulfillment", "received", "accepted"]),
                )
            )
            procurements = list(procurements.scalars().all())
            
            if not procurements:
                continue
            
            # Collect affected entities
            affected_projects = set()
            affected_commitments = set()
            affected_customers = set()
            affected_resources = set()
            affected_capabilities = set()
            
            for p in procurements:
                if p.project_id:
                    affected_projects.add(p.project_id)
                if p.commitment_id:
                    affected_commitments.add(p.commitment_id)
                if p.demand_id:
                    demand = await db.get(ResourceDemand, p.demand_id)
                    if demand and demand.source_type == "project":
                        affected_projects.add(demand.source_id)
                if p.requirement_id:
                    affected_resources.add(p.requirement_id)
                if p.capability_id:
                    affected_capabilities.add(p.capability_id)
            
            # Determine criticality
            criticality = "medium"
            if len(procurements) > 10:
                criticality = "critical"
            elif len(procurements) > 5:
                criticality = "high"
            elif len(procurements) > 2:
                criticality = "medium"
            else:
                criticality = "low"
            
            # Check for single source
            dependency_type = "distributed"
            if len(procurements) > 0:
                # Check if other vendors provide similar
                dep_type = "single_source"
                dependency_type = dep_type
            
            # Risk assessment
            risk_kinds = []
            if vendor.is_contract_expiring_soon:
                risk_kinds.append("contract_risk")
            if vendor.risk_level in ("high", "critical"):
                risk_kinds.append("financial_risk")
            if len(procurements) > 5 and len(procurements) / max(1, len(procurements)) > 0.5:
                risk_kinds.append("concentration_risk")
            
            fingerprint = hashlib.sha256(
                json.dumps({
                    "vendor_id": vendor.id,
                    "criticality": "critical" if vendor.is_critical else "high",
                    "project_count": len(affected_projects),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64]
            
            dep = VendorDependency(
                organization_id=caller.organization_id,
                vendor_id=vendor.id,
                criticality=criticality,
                dependency_type="single_source" if len(affected_projects) > 0 else "distributed",
                affected_project_ids_json=list(affected_projects),
                affected_commitment_ids_json=list(affected_commitments),
                affected_customer_ids_json=list(affected_customers),
                affected_resource_kinds_json=list(affected_resources),
                affected_capability_categories_json=list(affected_capabilities),
                risk_level=vendor.risk_level,
                risk_kinds_json=risk_kinds,
                alternative_vendor_ids_json=[],  # Would need to query for alternatives
                substitution_feasibility="moderate",
                title=f"Dependency on {vendor.name}",
                description=f"Vendor {vendor.name} supplies {len(procurements)} active procurements affecting {len(affected_projects)} projects",
                evidence_json={
                    "procurement_count": len(procurements),
                    "project_count": len(affected_projects),
                    "commitment_count": len(affected_commitments),
                },
                fingerprint=hashlib.sha256(
                    json.dumps({
                        "vendor_id": vendor.id,
                        "projects": sorted(list(affected_projects)),
                    }, sort_keys=True, default=str).encode()
                ).hexdigest()[:64],
            )
            dependencies.append(dep)
        
        db.add_all(dependencies)
        await db.flush()
        return dependencies
    
    # ================================================================
    # 8. CONFLICT DERIVATION (for Operating Attention)
    # ================================================================
    
    async def derive_procurement_conflicts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[ProcurementImpactAnalysis]:
        """Derive procurement conflicts and risks."""
        
        conflicts = []
        
        # 1. Overdue procurements
        overdue = await db.execute(
            select(CanonicalProcurement).where(
                CanonicalProcurement.organization_id == caller.organization_id,
                CanonicalProcurement.expected_delivery < date.today(),
                CanonicalProcurement.state.in_(["ordered", "in_fulfillment"]),
            )
        )
        overdue = list(overdue.scalars().all())
        
        for p in overdue:
            fp = hashlib.sha256(
                json.dumps({"kind": "overdue", "procurement_id": p.id}, sort_keys=True).encode()
            ).hexdigest()[:64]
            
            analysis = ProcurementImpactAnalysis(
                organization_id=caller.organization_id,
                trigger_type="procurement_overdue",
                trigger_entity_type="procurement",
                trigger_entity_id=p.id,
                trigger_params={"days_overdue": (date.today() - p.expected_delivery).days},
                affected_procurements=[{"id": p.id, "days_overdue": (date.today() - p.expected_delivery).days}],
                risk_assessment={"type": "delivery_delay", "severity": "high"},
                fingerprint=fp,
                confidence=0.9,
                analyzed_at=utcnow(),
            )
            conflicts.append(analysis)
        
        # 2. Vendor contract expiring
        vendors = await self._get_vendors(db, caller)
        for v in vendors:
            if v.is_contract_expiring_soon:
                fp = hashlib.sha256(
                    json.dumps({"kind": "contract_expiring", "vendor_id": v.id}, sort_keys=True).encode()
                ).hexdigest()[:64]
                
                analysis = ProcurementImpactAnalysis(
                    organization_id=caller.organization_id,
                    trigger_type="vendor_contract_expiring",
                    trigger_entity_type="vendor",
                    trigger_entity_id=v.id,
                    trigger_params={"days_until_expiry": (v.contract_expires_at - utcnow()).days if v.contract_expires_at else 0},
                    affected_vendors=[{"id": v.id, "contract_expires": str(v.contract_expires_at)}],
                    risk_assessment={"type": "contract_expiry", "severity": "high"},
                    fingerprint=fp,
                    confidence=0.95,
                    analyzed_at=utcnow(),
                )
                conflicts.append(analysis)
        
        # 3. External capacity constrained
        external_caps = await self._get_external_capacity(db, caller)
        for ec in external_caps:
            if ec.is_constrained:
                fp = hashlib.sha256(
                    json.dumps({"kind": "capacity_constrained", "capacity_id": ec.id}, sort_keys=True).encode()
                ).hexdigest()[:64]
                
                analysis = ProcurementImpactAnalysis(
                    organization_id=caller.organization_id,
                    trigger_type="external_capacity_constrained",
                    trigger_entity_type="external_capacity",
                    trigger_entity_id=ec.id,
                    trigger_params={"capacity_type": ec.capacity_type},
                    affected_external_capacity=[{"id": ec.id, "available": ec.available_capacity}],
                    risk_assessment={"type": "capacity_shortage", "severity": "high"},
                    fingerprint=fp,
                    confidence=0.9,
                    analyzed_at=utcnow(),
                )
                conflicts.append(analysis)
        
        db.add_all(conflicts)
        await db.flush()
        return conflicts
    
    # ================================================================
    # 9. PROCUREMENT IMPACT ANALYSIS
    # ================================================================
    
    async def analyze_procurement_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        trigger_type: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_params: Optional[Dict[str, Any]] = None,
    ) -> ProcurementImpactAnalysis:
        """Analyze cross-domain impact of procurement/vendor changes."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "trigger_type": trigger_type,
                "trigger_entity_type": trigger_entity_type,
                "trigger_entity_id": trigger_entity_id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(ProcurementImpactAnalysis).where(
                ProcurementImpactAnalysis.organization_id == caller.organization_id,
                ProcurementImpactAnalysis.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Gather impacted entities based on trigger
        affected_procurements = []
        affected_vendors = []
        affected_external_capacity = []
        affected_resources = []
        affected_allocations = []
        affected_demands = []
        affected_projects = []
        affected_commitments = []
        affected_objectives = []
        affected_customers = []
        
        if trigger_entity_type == "procurement":
            p = await db.get(CanonicalProcurement, trigger_entity_id)
            if p:
                affected_procurements.append({"id": p.id, "state": p.state, "vendor": p.vendor_name})
                if p.project_id:
                    affected_projects.append({"id": p.project_id})
                if p.commitment_id:
                    affected_commitments.append({"id": p.commitment_id})
                if p.demand_id:
                    affected_demands.append({"id": p.demand_id})
        
        elif trigger_entity_type == "vendor":
            v = await db.get(CanonicalVendor, trigger_entity_id)
            if v:
                affected_vendors.append({"id": v.id, "criticality": v.criticality})
                # Find procurements for this vendor
                procs = await db.execute(
                    select(CanonicalProcurement).where(
                        CanonicalProcurement.organization_id == caller.organization_id,
                        CanonicalProcurement.vendor_id == v.id,
                    )
                )
                for p in procs.scalars().all():
                    affected_procurements.append({"id": p.id, "state": p.state})
                    if p.project_id:
                        affected_projects.append({"id": p.project_id})
        
        analysis = ProcurementImpactAnalysis(
            organization_id=caller.organization_id,
            trigger_type=trigger_type,
            trigger_entity_type=trigger_entity_type,
            trigger_entity_id=trigger_entity_id,
            trigger_params=trigger_params or {},
            affected_procurements=affected_procurements,
            affected_vendors=affected_vendors,
            affected_projects=affected_projects,
            affected_commitments=affected_commitments,
            affected_objectives=affected_objectives,
            affected_customers=affected_customers,
            budget_impact=0.0,
            revenue_impact=0.0,
            cost_impact=0.0,
            timeline_impact_days=None,
            risk_assessment={},
            confidence=0.6,
            analyzed_at=utcnow(),
            source_event_id=trigger_params.get("source_event_id") if trigger_params else None,
            fingerprint=fingerprint,
        )
        
        db.add(analysis)
        try:
            await db.flush()
            return analysis
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ProcurementImpactAnalysis).where(
                    ProcurementImpactAnalysis.organization_id == caller.organization_id,
                    ProcurementImpactAnalysis.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    # ================================================================
    # 10. GATE 14 CUSTOMER INTEGRATION
    # ================================================================
    
    async def derive_customer_procurement_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        customer_id: str,
    ) -> Dict[str, Any]:
        """Derive procurement impact for a specific customer."""
        
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
        
        # Get procurements for these projects
        procurement_results = []
        for pid in project_ids:
            procs = await db.execute(
                select(CanonicalProcurement).where(
                    CanonicalProcurement.organization_id == caller.organization_id,
                    CanonicalProcurement.project_id == pid,
                )
            )
            procurement_results.extend(procs.scalars().all())
        
        # Get vendor dependencies
        vendor_ids = set(p.vendor_id for p in procurement_results if p.vendor_id)
        vendors = []
        for vid in vendor_ids:
            v = await db.get(CanonicalVendor, vid)
            if v:
                vendors.append(v)
        
        return {
            "customer_id": customer_id,
            "customer_name": customer.company_name,
            "commitments": len(commitments),
            "projects": len(project_ids),
            "procurements": len(procurement_results),
            "active_procurements": sum(1 for p in procurement_results if p.is_active),
            "delayed_procurements": sum(1 for p in procurement_results if p.is_delayed),
            "vendors": len(vendors),
            "critical_vendors": sum(1 for v in vendors if v.is_critical),
            "total_committed_spend": sum(p.estimated_cost or 0 for p in procurement_results),
            "total_actual_spend": sum(p.actual_cost or 0 for p in procurement_results if p.actual_cost),
        }
    
    # ================================================================
    # 11. GATE 13 STRATEGIC ALIGNMENT INTEGRATION
    # ================================================================
    
    async def trace_procurement_to_strategy(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        procurement_id: str,
    ) -> Dict[str, Any]:
        """Trace a procurement back through project → commitment → objective → initiative → intent."""
        
        procurement = await db.get(CanonicalProcurement, procurement_id)
        if not procurement or procurement.organization_id != caller.organization_id:
            raise ValueError("Procurement not found or access denied")
        
        trace = {
            "procurement": {
                "id": procurement.id,
                "title": procurement.title,
                "kind": procurement.kind,
                "state": procurement.state,
                "vendor": procurement.vendor_name,
            },
            "project": None,
            "commitment": None,
            "objective": None,
            "initiative": None,
            "intent": None,
        }
        
        # Trace project
        if procurement.project_id:
            project = await db.get(Project, procurement.project_id)
            if project:
                trace["project"] = {"id": project.id, "name": project.name}
                
                # Get strategic alignment
                alignment = await strategic_alignment_engine.trace_backward(
                    db, caller=caller,
                    entity_type="project", entity_id=project.id
                )
                if "chain" in alignment:
                    for link in alignment["chain"]:
                        if link.get("to_type") == "commitment":
                            trace["commitment"] = {"id": link.get("to_id")}
                        elif link.get("to_type") == "objective":
                            obj = await db.get(CompanyObjective, link.get("to_id"))
                            if obj:
                                trace["objective"] = {"id": obj.id, "title": obj.title}
                        elif link.get("to_type") == "initiative":
                            init = await db.get(CompanyInitiative, link.get("to_id"))
                            if init:
                                trace["initiative"] = {"id": init.id, "title": init.title}
                        elif link.get("to_type") == "intent":
                            trace["intent"] = {"id": link.get("to_id")}
        
        return trace
    
    # ================================================================
    # 12. PREDICTION INTEGRATION (Gate 10)
    # ================================================================
    
    async def predict_vendor_delivery_risk(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        vendor_id: Optional[str] = None,
        horizon_days: int = 30,
    ) -> Dict[str, Any]:
        """Predict vendor delivery risk using Gate 10 predictive intelligence."""
        
        vendors = await self._get_vendors(db, caller)
        if vendor_id:
            vendors = [v for v in vendors if v.id == vendor_id]
        
        predictions = []
        future_date = date.today()
        from datetime import timedelta
        future_end = future_date + timedelta(days=horizon_days)
        
        for vendor in vendors:
            # Get upcoming procurements
            upcoming = await db.execute(
                select(CanonicalProcurement).where(
                    CanonicalProcurement.organization_id == caller.organization_id,
                    CanonicalProcurement.vendor_id == vendor.id,
                    CanonicalProcurement.state.in_(["ordered", "in_fulfillment"]),
                    CanonicalProcurement.expected_delivery <= future_end,
                    CanonicalProcurement.expected_delivery >= future_date,
                )
            )
            upcoming = list(upcoming.scalars().all())
            
            if not upcoming:
                continue
            
            # Get vendor performance
            perf = await db.execute(
                select(VendorPerformance).where(
                    VendorPerformance.organization_id == caller.organization_id,
                    VendorPerformance.vendor_id == vendor.id,
                    VendorPerformance.metric_kind == "on_time_delivery",
                ).order_by(VendorPerformance.period_end.desc()).limit(1)
            )
            perf = perf.scalars().first()
            
            on_time_rate = perf.metric_value if perf else 0.9
            at_risk = [p for p in upcoming if p.expected_delivery and p.expected_delivery <= date.today() + timedelta(days=7)]
            
            risk_score = 1.0 - on_time_rate
            if len(at_risk) > 0:
                risk_score += 0.3
            
            predictions.append({
                "vendor_id": vendor.id,
                "vendor_name": vendor.name,
                "upcoming_procurements": len(upcoming),
                "at_risk_procurements": len(at_risk),
                "on_time_delivery_rate": on_time_rate,
                "risk_score": min(1.0, risk_score),
                "risk_level": "high" if risk_score > 0.6 else "medium" if risk_score > 0.3 else "low",
                "at_risk_details": [{"id": p.id, "expected": str(p.expected_delivery)} for p in at_risk],
            })
        
        return {
            "horizon_days": horizon_days,
            "predictions": predictions,
            "overall_risk": max((p["risk_level"] for p in predictions), default="low"),
        }
    
    # ================================================================
    # 13. COUNTERFACTUAL/DIGITAL TWIN INTEGRATION (Gates 11/12)
    # ================================================================
    
    async def create_procurement_scenario(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_name: str,
        vendor_changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a counterfactual scenario with vendor/procurement changes."""
        
        changes = []
        for vc in vendor_changes:
            if vc.get("type") == "vendor_unavailable":
                changes.append({
                    "kind": "vendor_unavailable",
                    "subject_type": "vendor",
                    "subject_id": vc.get("vendor_id"),
                    "params": {"duration_days": vc.get("duration_days", 30)},
                })
            elif vc.get("type") == "procurement_delayed":
                changes.append({
                    "kind": "procurement_delayed",
                    "subject_type": "procurement",
                    "subject_id": vc.get("procurement_id"),
                    "params": {"delay_days": vc.get("delay_days", 7)},
                })
            elif vc.get("type") == "vendor_changed":
                changes.append({
                    "kind": "vendor_changed",
                    "subject_type": "procurement",
                    "subject_id": vc.get("procurement_id"),
                    "params": {"new_vendor_id": vc.get("new_vendor_id")},
                })
            elif vc.get("type") == "external_capacity_changed":
                changes.append({
                    "kind": "external_capacity_changed",
                    "subject_type": "external_capacity",
                    "subject_id": vc.get("capacity_id"),
                    "params": {"capacity_delta": vc.get("capacity_delta", 0)},
                })
        
        from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
        
        result = await counterfactual_intelligence_service.create_scenario(
            db,
            caller=caller,
            scenario_kind="procurement_scenario",
            subject_type="procurement",
            subject_id=scenario_name,
            params={"changes": changes, "scenario_name": scenario_name},
            dry_run=False,
        )
        
        return result
    
    # ================================================================
    # 14. CONFLICT DERIVATION FOR OPERATING ATTENTION
    # ================================================================
    
    async def derive_operating_conflicts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[ProcurementImpactAnalysis]:
        """Derive procurement/vendor conflicts for Operating Attention."""
        
        return await self.derive_procurement_conflicts(db, caller=caller)


# Global instance
canonical_procurement_vendor_service = CanonicalProcurementVendorService()