"""Canonical Enterprise Operations & Business Process Fabric Service — Gate 19.

Derives the unified business process operating fabric by composing Gates 15-18
into a single coherent operational fabric.

This is a DERIVED PROJECTION layer — it does NOT create a second process/operations graph.
All data is composed from existing canonical primitives:
- Gates 8-14: People, Work, Communication, Meetings, Organizational Intelligence, Capacity
- Gate 9: Institutional Learning
- Gate 10: Predictive Intelligence
- Gate 11: Counterfactual Intelligence
- Gate 12: Digital Twin
- Gate 13: Strategic Alignment & Cross-Domain Operating Fabric
- Gate 14: Customer/Commercial Operating Fabric
- Gate 15: Financial + Resource + Procurement Operating Fabric
- Gate 16: Resource + Asset + Allocation Operating Fabric
- Gate 17: Procurement + Vendor + External Capacity Operating Fabric
- Gate 18: Economic Intelligence
"""

import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import sqlalchemy
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.organization import TimestampMixin, gen_uuid
from app.models.canonical_business_process import (
    CanonicalBusinessProcess,
    ProcessExecution,
    ProcessStep,
    ProcessApproval,
    ProcessBottleneck,
    ProcessOperatingSlice,
    ProcessImpactAnalysis,
    ProcessPerformance,
    ProcessDependency,
    ProcessScenario,
    ProcessKnowledge,
    PROCESS_LIFECYCLE_STATES,
    PROCESS_TYPES,
    PROCESS_TRIGGERS,
    PROCESS_PRIORITIES,
    PROCESS_SEVERITY,
    PROCESS_ROLES,
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
)
from app.models.canonical_procurement_vendor import (
    CanonicalVendor,
    VendorCapability,
    ExternalCapacity,
    CanonicalProcurement,
    VendorPerformance,
    VendorDependency,
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
from app.intelligence.financial_resource_procurement_service import financial_resource_procurement_service
from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
from app.intelligence.canonical_economic_intelligence_service import canonical_economic_intelligence_service

logger = logging.getLogger("vcos.intelligence.canonical_business_process")


class CanonicalBusinessProcessService:
    """
    Service for deriving the canonical business process operating fabric.
    
    Composes Gates 15-18 into a single coherent operational fabric.
    All methods return DERIVED PROJECTIONS over canonical reality.
    They do NOT mutate canonical data.
    """
    
    # ================================================================
    # 1. PROCESS OPERATING SLICE
    # ================================================================
    
    async def derive_process_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "organization",
        scope_id: Optional[str] = None,
    ) -> ProcessOperatingSlice:
        """
        Derive a governed, point-in-time operating slice for processes.
        
        Composes all canonical reality relevant to processes:
        - Processes (lifecycle, state, ownership)
        - Executions (state, performance)
        - Steps (state, performance)
        - Approvals (state, performance)
        - Bottlenecks (type, severity)
        - Performance metrics
        - Financial (Gate 18)
        """
        start = time.perf_counter()
        
        # Governance: verify org-wide access
        if not caller.org_wide:
            raise ValueError("Process operating slice requires org-wide access")
        
        # Build input fingerprint for exact-once
        input_data = {
            "organization_id": caller.organization_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "scope": "process_operating_slice",
        }
        input_fingerprint = hashlib.sha256(
            json.dumps(input_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        # Check for existing slice with same fingerprint
        existing = await db.execute(
            select(ProcessOperatingSlice).where(
                ProcessOperatingSlice.organization_id == caller.organization_id,
                ProcessOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Derive from existing slices
        financial_slice = await financial_resource_procurement_service.derive_financial_operating_slice(
            db, caller=caller
        )
        resource_slice = await canonical_resource_asset_service.derive_resource_operating_slice(
            db, caller=caller
        )
        vendor_slice = await canonical_procurement_vendor_service.derive_vendor_operating_slice(
            db, caller=caller
        )
        economic_slice = await canonical_economic_intelligence_service.derive_economic_operating_slice(
            db, caller=caller
        )
        
        # Get processes
        processes = await self._get_processes(db, caller)
        executions = await self._get_executions(db, caller)
        steps = await self._get_steps(db, caller)
        approvals = await self._get_approvals(db, caller)
        bottlenecks = await self.derive_process_conflicts(db=db, caller=caller)
        performance = await self._get_performance(db, caller)
        
        # Build slice
        slice_obj = ProcessOperatingSlice(
            organization_id=caller.organization_id,
            input_fingerprint=input_fingerprint,
            processes_by_type=self._count_by_field(processes, "process_type"),
            processes_by_state=self._count_by_field(processes, "lifecycle_state"),
            processes_by_category=self._count_by_field(processes, "category"),
            processes_by_owner=self._count_by_field(processes, "owner_id"),
            
            total_executions=len(executions),
            active_executions=sum(1 for e in executions if e.state in ("running", "paused", "waiting", "blocked")),
            completed_executions=sum(1 for e in executions if e.state == "completed"),
            failed_executions=sum(1 for e in executions if e.state == "failed"),
            executions_by_state=self._count_by_field(executions, "state"),
            executions_by_process_type=self._count_by_field(executions, "process_type"),
            
            total_steps=len(steps),
            active_steps=sum(1 for s in steps if s.state in ("running", "waiting_approval", "waiting_delay")),
            blocked_steps=sum(1 for s in steps if s.state == "blocked"),
            waiting_approval_steps=sum(1 for s in steps if s.state == "waiting_approval"),
            failed_steps=sum(1 for s in steps if s.state == "failed"),
            
            pending_approvals=sum(1 for a in approvals if a.status == "pending"),
            overdue_approvals=sum(1 for a in approvals if a.due_at and a.due_at < utcnow() and a.status == "pending"),
            approval_by_type=self._count_by_field(approvals, "approval_type"),
            
            avg_cycle_time_hours=self._avg_cycle_time(executions),
            median_cycle_time_hours=self._median_cycle_time(executions),
            avg_wait_time_hours=self._avg_wait_time(steps),
            completion_rate=self._completion_rate(executions),
            failure_rate=self._failure_rate(executions),
            rework_rate=self._rework_rate(steps),
            sla_breach_rate=self._sla_breach_rate(steps),
            
            bottleneck_count=len(bottlenecks),
            critical_bottlenecks=sum(1 for b in bottlenecks if b.severity == "critical"),
            bottlenecks_by_type=self._count_by_field(bottlenecks, "bottleneck_type"),
            
            total_process_cost=sum(e.total_process_cost or 0 for e in executions if hasattr(e, 'total_process_cost')),
            avg_cost_per_execution=None,
            
            customer_impacting_processes=sum(1 for e in executions if getattr(e, 'customer_id', None)),
            at_risk_customers=0,
            
            computed_at=utcnow(),
            computation_duration_ms=int((time.perf_counter() - start) * 1000),
            fingerprint=hashlib.sha256(
                json.dumps({
                    "process_count": len(processes),
                    "execution_count": len(executions),
                    "step_count": len(steps),
                    "bottleneck_count": len(bottlenecks),
                }, sort_keys=True, default=str).encode()
            ).hexdigest()[:64],
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        
        # Ensure id is generated
        if not slice_obj.id:
            slice_obj.id = gen_uuid()
        
        # Use raw SQL INSERT with ON CONFLICT DO NOTHING for exact-once
        from sqlalchemy import text
        insert_sql = text("""
            INSERT INTO process_operating_slices (
                id, organization_id, input_fingerprint,
                processes_by_type, processes_by_state, processes_by_category, processes_by_owner,
                total_executions, active_executions, completed_executions, failed_executions,
                executions_by_state, executions_by_process_type,
                total_steps, active_steps, blocked_steps, waiting_approval_steps, failed_steps,
                pending_approvals, overdue_approvals, approval_by_type,
                avg_cycle_time_hours, median_cycle_time_hours, avg_wait_time_hours,
                completion_rate, failure_rate, rework_rate, sla_breach_rate,
                bottleneck_count, critical_bottlenecks, bottlenecks_by_type,
                total_process_cost, avg_cost_per_execution,
                customer_impacting_processes, at_risk_customers,
                computed_at, computation_duration_ms, fingerprint,
                created_at, updated_at
            ) VALUES (
                :id, :organization_id, :input_fingerprint,
                :processes_by_type, :processes_by_state, :processes_by_category, :processes_by_owner,
                :total_executions, :active_executions, :completed_executions, :failed_executions,
                :executions_by_state, :executions_by_process_type,
                :total_steps, :active_steps, :blocked_steps, :waiting_approval_steps, :failed_steps,
                :pending_approvals, :overdue_approvals, :approval_by_type,
                :avg_cycle_time_hours, :median_cycle_time_hours, :avg_wait_time_hours,
                :completion_rate, :failure_rate, :rework_rate, :sla_breach_rate,
                :bottleneck_count, :critical_bottlenecks, :bottlenecks_by_type,
                :total_process_cost, :avg_cost_per_execution,
                :customer_impacting_processes, :at_risk_customers,
                :computed_at, :computation_duration_ms, :fingerprint,
                :created_at, :updated_at
            )
            ON CONFLICT (organization_id, input_fingerprint) DO NOTHING
        """)
        
        await db.execute(insert_sql, {
            "id": slice_obj.id,
            "organization_id": slice_obj.organization_id,
            "input_fingerprint": slice_obj.input_fingerprint,
            "processes_by_type": json.dumps(slice_obj.processes_by_type),
            "processes_by_state": json.dumps(slice_obj.processes_by_state),
            "processes_by_category": json.dumps(slice_obj.processes_by_category),
            "processes_by_owner": json.dumps(slice_obj.processes_by_owner),
            "total_executions": slice_obj.total_executions,
            "active_executions": slice_obj.active_executions,
            "completed_executions": slice_obj.completed_executions,
            "failed_executions": slice_obj.failed_executions,
            "executions_by_state": json.dumps(slice_obj.executions_by_state),
            "executions_by_process_type": json.dumps(slice_obj.executions_by_process_type),
            "total_steps": slice_obj.total_steps,
            "active_steps": slice_obj.active_steps,
            "blocked_steps": slice_obj.blocked_steps,
            "waiting_approval_steps": slice_obj.waiting_approval_steps,
            "failed_steps": slice_obj.failed_steps,
            "pending_approvals": slice_obj.pending_approvals,
            "overdue_approvals": slice_obj.overdue_approvals,
            "approval_by_type": json.dumps(slice_obj.approval_by_type),
            "avg_cycle_time_hours": slice_obj.avg_cycle_time_hours,
            "median_cycle_time_hours": slice_obj.median_cycle_time_hours,
            "avg_wait_time_hours": slice_obj.avg_wait_time_hours,
            "completion_rate": slice_obj.completion_rate,
            "failure_rate": slice_obj.failure_rate,
            "rework_rate": slice_obj.rework_rate,
            "sla_breach_rate": slice_obj.sla_breach_rate,
            "bottleneck_count": slice_obj.bottleneck_count,
            "critical_bottlenecks": slice_obj.critical_bottlenecks,
            "bottlenecks_by_type": json.dumps(slice_obj.bottlenecks_by_type),
            "total_process_cost": slice_obj.total_process_cost,
            "avg_cost_per_execution": slice_obj.avg_cost_per_execution,
            "customer_impacting_processes": slice_obj.customer_impacting_processes,
            "at_risk_customers": slice_obj.at_risk_customers,
            "computed_at": slice_obj.computed_at,
            "computation_duration_ms": slice_obj.computation_duration_ms,
            "fingerprint": slice_obj.fingerprint,
            "created_at": slice_obj.created_at,
            "updated_at": slice_obj.updated_at,
        })
        await db.flush()
        
        # Query for the existing or newly inserted slice
        existing = await db.execute(
            select(ProcessOperatingSlice).where(
                ProcessOperatingSlice.organization_id == caller.organization_id,
                ProcessOperatingSlice.input_fingerprint == input_fingerprint,
            )
        )
        return existing.scalars().first()
    
    async def _get_processes(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalBusinessProcess]:
        result = await db.execute(
            select(CanonicalBusinessProcess).where(
                CanonicalBusinessProcess.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_executions(self, db: AsyncSession, caller: CallerAccess) -> List[ProcessExecution]:
        result = await db.execute(
            select(ProcessExecution).where(
                ProcessExecution.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_steps(self, db: AsyncSession, caller: CallerAccess) -> List[ProcessStep]:
        result = await db.execute(
            select(ProcessStep).where(
                ProcessStep.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_approvals(self, db: AsyncSession, caller: CallerAccess) -> List[ProcessApproval]:
        result = await db.execute(
            select(ProcessApproval).where(
                ProcessApproval.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_resources(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalResource]:
        result = await db.execute(
            select(CanonicalResource).where(
                CanonicalResource.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_demands(self, db: AsyncSession, caller: CallerAccess) -> List[ResourceDemand]:
        result = await db.execute(
            select(ResourceDemand).where(
                ResourceDemand.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_assets(self, db: AsyncSession, caller: CallerAccess) -> List[CanonicalAsset]:
        result = await db.execute(
            select(CanonicalAsset).where(
                CanonicalAsset.organization_id == caller.organization_id,
            )
        )
        return list(result.scalars().all())
    
    async def _get_performance(self, db: AsyncSession, caller: CallerAccess) -> List[ProcessPerformance]:
        result = await db.execute(
            select(ProcessPerformance).where(
                ProcessPerformance.organization_id == caller.organization_id,
            ).order_by(ProcessPerformance.computed_at.desc()).limit(20)
        )
        return list(result.scalars().all())
    
    def _count_by_field(self, items: List, field: str) -> Dict[str, int]:
        counts = {}
        for item in items:
            val = getattr(item, field, None)
            if val:
                counts[val] = counts.get(val, 0) + 1
        return counts
    
    def _avg_cycle_time(self, executions: List[ProcessExecution]) -> Optional[float]:
        valid = [e for e in executions if e.completed_at and e.started_at]
        if not valid:
            return None
        total = sum((e.completed_at - e.started_at).total_seconds() / 3600 for e in valid)
        return total / len(valid)
    
    def _median_cycle_time(self, executions: List[ProcessExecution]) -> Optional[float]:
        valid = [e for e in executions if e.completed_at and e.started_at]
        if not valid:
            return None
        times = sorted((e.completed_at - e.started_at).total_seconds() / 3600 for e in valid)
        n = len(times)
        if n % 2 == 0:
            return (times[n//2 - 1] + times[n//2]) / 2
        return times[n//2]
    
    def _avg_wait_time(self, steps: List[ProcessStep]) -> Optional[float]:
        valid = [s for s in steps if s.waiting_duration_ms is not None]
        if not valid:
            return None
        total = sum(s.waiting_duration_ms / 3600000 for s in valid)
        return total / len(valid)
    
    def _completion_rate(self, executions: List[ProcessExecution]) -> Optional[float]:
        if not executions:
            return 0.0
        completed = sum(1 for e in executions if e.state == "completed")
        return completed / len(executions)
    
    def _failure_rate(self, executions: List[ProcessExecution]) -> Optional[float]:
        if not executions:
            return 0.0
        failed = sum(1 for e in executions if e.state == "failed")
        return failed / len(executions)
    
    def _rework_rate(self, steps: List[ProcessStep]) -> Optional[float]:
        if not steps:
            return 0.0
        reworked = sum(1 for s in steps if s.retry_count and s.retry_count > 0)
        return reworked / len(steps)
    
    def _sla_breach_rate(self, steps: List[ProcessStep]) -> Optional[float]:
        if not steps:
            return 0.0
        breached = sum(1 for s in steps if s.due_at and s.due_at < utcnow() and s.state != "completed")
        return breached / len(steps)
    
    # ================================================================
    # 2. CANONICAL BUSINESS PROCESS CREATION
    # ================================================================
    
    async def create_business_process(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        name: str,
        process_type: str,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        description: Optional[str] = None,
        trigger_type: str = "manual",
        trigger_config: Optional[dict] = None,
        trigger_condition: Optional[str] = None,
        owner_id: Optional[str] = None,
        owner_type: Optional[str] = None,
        accountable_id: Optional[str] = None,
        accountable_type: Optional[str] = None,
        governance_scope_id: Optional[str] = None,
        requires_approval: bool = False,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        participants_json: Optional[list] = None,
        required_capabilities_json: Optional[list] = None,
        required_resources_json: Optional[list] = None,
        depends_on_process_ids_json: Optional[list] = None,
        blocks_process_ids_json: Optional[list] = None,
        objective_id: Optional[str] = None,
        initiative_id: Optional[str] = None,
        project_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        priority: str = "medium",
        expected_outcome: Optional[str] = None,
        estimated_duration_hours: Optional[float] = None,
        due_at: Optional[datetime] = None,
    ) -> CanonicalBusinessProcess:
        """Create a canonical business process with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "name": name,
                "process_type": process_type,
                "organization_id": caller.organization_id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(CanonicalBusinessProcess).where(
                CanonicalBusinessProcess.organization_id == caller.organization_id,
                CanonicalBusinessProcess.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        process = CanonicalBusinessProcess(
            organization_id=caller.organization_id,
            name=name,
            description=description,
            process_type=process_type,
            category=category,
            subcategory=subcategory,
            lifecycle_state="defined",
            trigger_type=trigger_type,
            trigger_config=trigger_config or {},
            trigger_condition=trigger_condition,
            owner_id=owner_id or caller.employee_id,
            owner_type=owner_type,
            accountable_id=accountable_id,
            accountable_type=accountable_type,
            governance_scope_id=governance_scope_id,
            requires_approval=requires_approval,
            scope_type=scope_type,
            scope_id=scope_id,
            participants_json=participants_json or [],
            required_capabilities_json=required_capabilities_json or [],
            required_resources_json=required_resources_json or [],
            depends_on_process_ids_json=depends_on_process_ids_json or [],
            blocks_process_ids_json=blocks_process_ids_json or [],
            objective_id=objective_id,
            initiative_id=initiative_id,
            project_id=project_id,
            commitment_id=commitment_id,
            customer_id=customer_id,
            priority=priority,
            expected_outcome=expected_outcome,
            estimated_duration_hours=estimated_duration_hours,
            due_at=due_at,
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(process)
        try:
            await db.flush()
            return process
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(CanonicalBusinessProcess).where(
                    CanonicalBusinessProcess.organization_id == caller.organization_id,
                    CanonicalBusinessProcess.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def transition_process_state(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        process_id: str,
        new_state: str,
        reason: Optional[str] = None,
    ) -> Optional[CanonicalBusinessProcess]:
        """Transition process to new lifecycle state."""
        
        if new_state not in PROCESS_LIFECYCLE_STATES:
            raise ValueError(f"Invalid process state: {new_state}")
        
        process = await db.get(CanonicalBusinessProcess, process_id)
        if not process:
            return None
        
        if process.organization_id != caller.organization_id:
            raise ValueError("Process not found or access denied")
        
        process.previous_state = process.lifecycle_state
        process.lifecycle_state = new_state
        process.state_changed_at = utcnow()
        process.state_change_reason = reason
        
        # Update timestamps based on state
        now = utcnow()
        if new_state == "triggered":
            process.started_at = now
        elif new_state == "completed":
            process.completed_at = now
        elif new_state == "verified":
            process.verified_at = now
        
        process.version += 1
        await db.flush()
        return process
    
    # ================================================================
    # 3. PROCESS EXECUTION MANAGEMENT
    # ================================================================
    
    async def create_process_execution(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        process_id: str,
        trigger_type: str = "manual",
        trigger_event_id: Optional[str] = None,
        trigger_payload: Optional[dict] = None,
        inputs: Optional[dict] = None,
        context: Optional[dict] = None,
        owner_id: Optional[str] = None,
        participants: Optional[list] = None,
        allocated_resources: Optional[dict] = None,
        allocated_capacity: Optional[dict] = None,
        due_at: Optional[datetime] = None,
    ) -> ProcessExecution:
        """Create a process execution with exact-once semantics."""
        
        # Get process for execution number
        process = await db.get(CanonicalBusinessProcess, process_id)
        if not process:
            raise ValueError("Process not found")
        
        # Get next execution number
        result = await db.execute(
            select(func.max(ProcessExecution.execution_number)).where(
                ProcessExecution.organization_id == caller.organization_id,
                ProcessExecution.process_id == process_id,
            )
        )
        max_num = result.scalar() or 0
        execution_number = max_num + 1
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "process_id": process_id,
                "execution_number": execution_number,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(ProcessExecution).where(
                ProcessExecution.organization_id == caller.organization_id,
                ProcessExecution.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        execution = ProcessExecution(
            organization_id=caller.organization_id,
            process_id=process_id,
            execution_number=execution_number,
            trigger_type=trigger_type,
            trigger_event_id=trigger_event_id,
            trigger_payload_json=trigger_payload or {},
            inputs_json=inputs or {},
            context_json=context or {},
            owner_id=owner_id or caller.employee_id,
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(execution)
        try:
            await db.flush()
            return execution
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ProcessExecution).where(
                    ProcessExecution.organization_id == caller.organization_id,
                    ProcessExecution.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def transition_execution_state(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        execution_id: str,
        new_state: str,
        reason: Optional[str] = None,
    ) -> Optional[ProcessExecution]:
        """Transition execution to new state."""
        
        valid_states = ("initializing", "running", "paused", "waiting", "blocked", "completed", "failed", "cancelled")
        if new_state not in valid_states:
            raise ValueError(f"Invalid execution state: {new_state}")
        
        execution = await db.get(ProcessExecution, execution_id)
        if not execution:
            return None
        
        if execution.organization_id != caller.organization_id:
            raise ValueError("Execution not found or access denied")
        
        execution.previous_state = execution.state
        execution.state = new_state
        execution.version += 1
        
        now = utcnow()
        if new_state == "running":
            execution.started_at = now
        elif new_state == "paused":
            execution.paused_at = now
        elif new_state in ("completed", "failed", "cancelled"):
            execution.completed_at = now
            if execution.started_at:
                execution.total_duration_ms = int((now - execution.started_at).total_seconds() * 1000)
        
        execution.version += 1
        await db.flush()
        return execution
    
    # ================================================================
    # 4. PROCESS STEP MANAGEMENT
    # ================================================================
    
    async def create_process_step(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        execution_id: str,
        step_key: str,
        step_name: str,
        step_type: str,
        step_config: Optional[dict] = None,
        input_data: Optional[dict] = None,
        expected_output: Optional[dict] = None,
        unit: str = "units",
        assignee_id: Optional[str] = None,
        assignee_type: Optional[str] = None,
        role_in_step: Optional[str] = None,
        depends_on_step_keys: Optional[list] = None,
        blocks_step_keys: Optional[list] = None,
        due_at: Optional[datetime] = None,
        estimated_duration_ms: Optional[int] = None,
        approval_required: bool = False,
        approver_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> ProcessStep:
        """Create a process step with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "execution_id": execution_id,
                "step_key": step_key,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(ProcessStep).where(
                ProcessStep.organization_id == caller.organization_id,
                ProcessStep.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        step = ProcessStep(
            organization_id=caller.organization_id,
            execution_id=execution_id,
            step_key=step_key,
            step_name=step_name,
            step_type=step_type,
            step_config_json=step_config or {},
            input_data_json=input_data or {},
            expected_output_json=expected_output or {},
            assignee_id=assignee_id,
            assignee_type=assignee_type,
            role_in_step=role_in_step,
            depends_on_step_keys_json=depends_on_step_keys or [],
            blocks_step_keys_json=blocks_step_keys or [],
            due_at=due_at,
            estimated_duration_ms=estimated_duration_ms,
            approval_required=approval_required,
            approver_id=approver_id,
            max_retries=max_retries,
            fingerprint=fingerprint,
            created_by=caller.employee_id or "system",
        )
        
        db.add(step)
        try:
            await db.flush()
            return step
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ProcessStep).where(
                    ProcessStep.organization_id == caller.organization_id,
                    ProcessStep.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def transition_step_state(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        step_id: str,
        new_state: str,
        reason: Optional[str] = None,
        actual_output: Optional[dict] = None,
        actual_duration_ms: Optional[int] = None,
    ) -> Optional[ProcessStep]:
        """Transition step to new state."""
        
        valid_states = ("pending", "running", "succeeded", "failed", "skipped", "waiting_approval", "waiting_delay", "blocked")
        if new_state not in valid_states:
            raise ValueError(f"Invalid step state: {new_state}")
        
        step = await db.get(ProcessStep, step_id)
        if not step:
            return None
        
        if step.organization_id != caller.organization_id:
            raise ValueError("Step not found or access denied")
        
        step.previous_state = step.state
        step.state = new_state
        step.version += 1
        
        now = utcnow()
        if new_state == "running":
            step.started_at = now
        elif new_state in ("succeeded", "failed", "skipped"):
            step.completed_at = now
            if step.started_at:
                step.actual_duration_ms = int((now - step.started_at).total_seconds() * 1000)
        
        if actual_output is not None:
            step.output_data_json = actual_output
        if actual_duration_ms is not None:
            step.actual_duration_ms = actual_duration_ms
        
        step.version += 1
        await db.flush()
        return step
    
    async def complete_step(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        step_id: str,
        output_data: Optional[dict] = None,
        actual_duration_ms: Optional[int] = None,
    ) -> Optional[ProcessStep]:
        """Complete a step successfully."""
        return await self.transition_step_state(
            db, caller=caller, step_id=step_id,
            new_state="succeeded", actual_output=output_data, actual_duration_ms=actual_duration_ms
        )
    
    async def fail_step(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        step_id: str,
        error: str,
        actual_duration_ms: Optional[int] = None,
    ) -> Optional[ProcessStep]:
        """Fail a step."""
        step = await db.get(ProcessStep, step_id)
        if not step:
            return None
        
        step.error = error
        step.error_count += 1
        step.last_error_at = utcnow()
        
        if step.retry_count < step.max_retries:
            step.retry_count += 1
            step.state = "pending"  # Will retry
        else:
            step.state = "failed"
        
        step.version += 1
        await db.flush()
        return step
    
    # ================================================================
    # 5. PROCESS APPROVAL MANAGEMENT
    # ================================================================
    
    async def create_process_approval(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        execution_id: str,
        step_id: Optional[str] = None,
        title: str,
        description: Optional[str] = None,
        approval_type: str = "sequential",
        approver_type: str = "user",
        required_approvers: Optional[list] = None,
        minimum_approvals: int = 1,
        budget_id: Optional[str] = None,
        requires_approval: bool = True,
        justification: Optional[str] = None,
        due_at: Optional[datetime] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> ProcessApproval:
        """Create a process approval with exact-once semantics."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "execution_id": execution_id,
                "step_id": step_id,
                "title": title,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(ProcessApproval).where(
                ProcessApproval.organization_id == caller.organization_id,
                ProcessApproval.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        approval = ProcessApproval(
            organization_id=caller.organization_id,
            execution_id=execution_id,
            step_id=step_id,
            title=title,
            description=description,
            approval_type=approval_type,
            approver_type=approver_type,
            required_approvers_json=required_approvers or [],
            minimum_approvals=minimum_approvals,
            requires_approval=requires_approval,
            requested_by=caller.employee_id or "system",
            due_at=due_at,
            entity_type=entity_type,
            entity_id=entity_id,
            fingerprint=fingerprint,
        )
        
        db.add(approval)
        try:
            await db.flush()
            return approval
        except IntegrityError:
            await db.rollback()
            existing = await db.execute(
                select(ProcessApproval).where(
                    ProcessApproval.organization_id == caller.organization_id,
                    ProcessApproval.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    async def decide_approval(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        approval_id: str,
        decision: str,  # approved|rejected
        decided_by: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[ProcessApproval]:
        """Record approval decision."""
        
        approval = await db.get(ProcessApproval, approval_id)
        if not approval:
            return None
        
        if approval.organization_id != caller.organization_id:
            raise ValueError("Approval not found or access denied")
        
        if approval.status not in ("pending", "escalated"):
            raise ValueError(f"Cannot decide approval in state: {approval.status}")
        
        if decision == "approved":
            approval.approval_count += 1
            if approval.approval_count >= approval.minimum_approvals:
                approval.status = "approved"
        elif decision == "rejected":
            approval.rejection_count += 1
            approval.status = "rejected"
        else:
            raise ValueError("Invalid decision")
        
        approval.decided_by = decided_by or caller.employee_id
        approval.decided_at = utcnow()
        approval.decision_note = note
        approval.version += 1
        
        await db.flush()
        return approval
    
    async def escalate_approval(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        approval_id: str,
        escalated_to_id: str,
        reason: str,
    ) -> Optional[ProcessApproval]:
        """Escalate an approval."""
        
        approval = await db.get(ProcessApproval, approval_id)
        if not approval:
            return None
        
        if approval.organization_id != caller.organization_id:
            raise ValueError("Approval not found or access denied")
        
        approval.escalation_level += 1
        approval.escalated_to_id = escalated_to_id
        approval.escalated_at = utcnow()
        approval.escalation_reason = reason
        approval.status = "escalated"
        approval.version += 1
        
        await db.flush()
        return approval
    
    # ================================================================
    # 6. PROCESS IMPACT ANALYSIS
    # ================================================================
    
    async def analyze_process_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        trigger_type: str,
        trigger_entity_type: str,
        trigger_entity_id: str,
        trigger_params: Optional[Dict[str, Any]] = None,
    ) -> ProcessImpactAnalysis:
        """Analyze cross-domain impact of a process change."""
        
        fingerprint = hashlib.sha256(
            json.dumps({
                "trigger_type": trigger_type,
                "trigger_entity_type": trigger_entity_type,
                "trigger_entity_id": trigger_entity_id,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()[:64]
        
        existing = await db.execute(
            select(ProcessImpactAnalysis).where(
                ProcessImpactAnalysis.organization_id == caller.organization_id,
                ProcessImpactAnalysis.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Gather impacted entities
        affected_processes = []
        affected_executions = []
        affected_steps = []
        affected_approvals = []
        affected_resources = []
        affected_allocations = []
        affected_demands = []
        affected_projects = []
        affected_commitments = []
        affected_objectives = []
        affected_people = []
        affected_customers = []
        affected_commitments = []
        affected_vendors = []
        affected_external_capacity = []
        
        if trigger_entity_type == "process":
            p = await db.get(CanonicalBusinessProcess, trigger_entity_id)
            if p:
                affected_processes.append({"id": p.id, "name": p.name, "state": p.lifecycle_state})
                if p.project_id:
                    affected_projects.append({"id": p.project_id})
                if p.commitment_id:
                    affected_commitments.append({"id": p.commitment_id})
                if p.objective_id:
                    affected_objectives.append({"id": p.objective_id})
        
        elif trigger_entity_type == "execution":
            e = await db.get(ProcessExecution, trigger_entity_id)
            if e:
                affected_executions.append({"id": e.id, "state": e.state, "process_id": e.process_id})
                if e.process_id:
                    affected_processes.append({"id": e.process_id})
                if e.project_id:
                    affected_projects.append({"id": e.project_id})
                if e.commitment_id:
                    affected_commitments.append({"id": e.commitment_id})
                if e.objective_id:
                    affected_objectives.append({"id": e.objective_id})
        
        elif trigger_entity_type == "step":
            s = await db.get(ProcessStep, trigger_entity_id)
            if s:
                affected_steps.append({"id": s.id, "name": s.step_name, "state": s.state})
                if s.execution_id:
                    affected_executions.append({"id": s.execution_id})
        
        elif trigger_entity_type == "approval":
            a = await db.get(ProcessApproval, trigger_entity_id)
            if a:
                affected_approvals.append({"id": a.id, "title": a.title, "status": a.status})
                if a.execution_id:
                    affected_executions.append({"id": a.execution_id})
        
        # Quantitative impact
        capacity_impact = {
            "delta_available": 0.0,
            "delta_utilization": 0.0,
            "bottleneck_risk": "low",
        }
        
        budget_impact = 0.0
        if trigger_params and "amount" in trigger_params:
            budget_impact = float(trigger_params["amount"])
        
        risk_assessment = {
            "conflicts_triggered": [],
            "bottleneck_risk": "low",
            "customer_risk": len(affected_customers) > 0,
            "commitment_risk": len(affected_commitments) > 0,
        }
        
        new_conflicts = []
        escalated_conflicts = []
        
        # Detect new conflicts from this change
        if trigger_type in ("budget_cut", "capacity_changed", "resource_removed", "vendor_removed"):
            conflicts = await self.derive_process_conflicts(db, caller=caller)
            for c in conflicts:
                new_conflicts.append(c.id)
        
        analysis = ProcessImpactAnalysis(
            organization_id=caller.organization_id,
            trigger_type=trigger_type,
            trigger_entity_type=trigger_entity_type,
            trigger_entity_id=trigger_entity_id,
            trigger_params=trigger_params or {},
            affected_processes=affected_processes,
            affected_executions=affected_executions,
            affected_steps=affected_steps,
            affected_approvals=affected_approvals,
            affected_resources=affected_resources,
            affected_allocations=affected_allocations,
            affected_demands=affected_demands,
            affected_projects=affected_projects,
            affected_commitments=affected_commitments,
            affected_objectives=affected_objectives,
            affected_people=affected_people,
            affected_customers=affected_customers,
            affected_vendors=affected_vendors,
            affected_external_capacity=affected_external_capacity,
            capacity_impact=capacity_impact,
            budget_impact=budget_impact,
            revenue_impact=0.0,
            cost_impact=0.0,
            timeline_impact_days=None,
            risk_assessment=risk_assessment,
            new_bottlenecks=new_conflicts,
            escalated_bottlenecks=escalated_conflicts,
            scenario_ids=[],
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
                select(ProcessImpactAnalysis).where(
                    ProcessImpactAnalysis.organization_id == caller.organization_id,
                    ProcessImpactAnalysis.fingerprint == fingerprint,
                )
            )
            return existing.scalars().first()
    
    # ================================================================
    # 7. PROCESS SCENARIO (Counterfactual)
    # ================================================================
    
    async def create_process_scenario(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_name: str,
        process_changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a counterfactual scenario with process changes."""
        
        changes = []
        for pc in process_changes:
            if pc.get("type") == "remove_approval":
                changes.append({
                    "kind": "remove_approval",
                    "subject_type": "process_step",
                    "subject_id": pc.get("step_id"),
                    "params": {"approval_id": pc.get("approval_id")},
                })
            elif pc.get("type") == "add_approval":
                changes.append({
                    "kind": "add_approval",
                    "subject_type": "process_step",
                    "subject_id": pc.get("step_id"),
                    "params": {"approver": pc.get("approver"), "type": pc.get("type", "sequential")},
                })
            elif pc.get("type") == "change_owner":
                changes.append({
                    "kind": "change_owner",
                    "subject_type": "process",
                    "subject_id": pc.get("process_id"),
                    "params": {"new_owner": pc.get("new_owner")},
                })
            elif pc.get("type") == "reallocate":
                changes.append({
                    "kind": "reallocate",
                    "subject_type": "process",
                    "subject_id": pc.get("process_id"),
                    "params": {"from_owner": pc.get("from_owner"), "to_owner": pc.get("to_owner")},
                })
            elif pc.get("type") == "add_resource":
                changes.append({
                    "kind": "add_resource",
                    "subject_type": "resource",
                    "subject_id": pc.get("resource_id"),
                    "params": {"capacity": pc.get("capacity")},
                })
            elif pc.get("type") == "change_vendor":
                changes.append({
                    "kind": "vendor_changed",
                    "subject_type": "procurement",
                    "subject_id": pc.get("procurement_id"),
                    "params": {"new_vendor_id": pc.get("new_vendor_id")},
                })
        
        from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
        
        result = await counterfactual_intelligence_service.create_scenario(
            db,
            caller=caller,
            scenario_kind="process_scenario",
            subject_type="process",
            subject_id=scenario_name,
            params={"changes": changes, "scenario_name": scenario_name},
            dry_run=False,
        )
        
        return result
    
    # ================================================================
    # 8. COUNTERFACTUAL / DIGITAL TWIN INTEGRATION (Gates 11/12)
    # ================================================================
    
    async def create_process_scenario(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_name: str,
        process_changes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create a counterfactual scenario with process changes."""
        
        changes = []
        for pc in process_changes:
            if pc.get("type") == "remove_approval":
                changes.append({
                    "kind": "remove_approval",
                    "subject_type": "process_step",
                    "subject_id": pc.get("step_id"),
                    "params": {"approval_id": pc.get("approval_id")},
                })
            elif pc.get("type") == "add_approval":
                changes.append({
                    "kind": "add_approval",
                    "subject_type": "process_step",
                    "subject_id": pc.get("step_id"),
                    "params": {"approver": pc.get("approver"), "type": pc.get("type", "sequential")},
                })
            elif pc.get("type") == "change_owner":
                changes.append({
                    "kind": "change_owner",
                    "subject_type": "process",
                    "subject_id": pc.get("process_id"),
                    "params": {"new_owner": pc.get("new_owner")},
                })
            elif pc.get("type") == "reallocate":
                changes.append({
                    "kind": "reallocate",
                    "subject_type": "process",
                    "subject_id": pc.get("process_id"),
                    "params": {"from_owner": pc.get("from_owner"), "to_owner": pc.get("to_owner")},
                })
            elif pc.get("type") == "add_resource":
                changes.append({
                    "kind": "add_resource",
                    "subject_type": "resource",
                    "subject_id": pc.get("resource_id"),
                    "params": {"capacity": pc.get("capacity")},
                })
            elif pc.get("type") == "change_vendor":
                changes.append({
                    "kind": "vendor_changed",
                    "subject_type": "procurement",
                    "subject_id": pc.get("procurement_id"),
                    "params": {"new_vendor_id": pc.get("new_vendor_id")},
                })
        
        from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
        
        result = await counterfactual_intelligence_service.create_scenario(
            db,
            caller=caller,
            scenario_kind="process_scenario",
            subject_type="process",
            subject_id=scenario_name,
            params={"changes": changes, "scenario_name": scenario_name},
            dry_run=False,
        )
        
        return result
    
    # ================================================================
    # 12. CONFLICT DERIVATION (feeds Operating Attention)
    # ================================================================
    
    async def derive_process_conflicts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[ProcessBottleneck]:
        """Derive process bottlenecks for Operating Attention."""
        
        bottlenecks = []
        
        # 1. Overdue approvals
        approvals_result = await db.execute(
            select(ProcessApproval).where(
                ProcessApproval.organization_id == caller.organization_id,
                ProcessApproval.status == "pending",
                ProcessApproval.due_at < utcnow(),
            )
        )
        overdue = approvals_result.scalars().all()
        for a in overdue:
            bottleneck = ProcessBottleneck(
                organization_id=caller.organization_id,
                bottleneck_type="approval_bottleneck",
                severity="critical" if a.due_at < utcnow() - timedelta(hours=48) else "warning",
                status="open",
                execution_id=a.execution_id,
                step_id=a.step_id,
                title=f"Overdue approval: {a.title}",
                description=f"Approval '{a.title}' overdue by {(utcnow() - a.due_at).total_seconds() / 3600:.1f} hours",
                wait_time_hours=(utcnow() - a.due_at).total_seconds() / 3600,
                detected_at=utcnow(),
                detected_by="system",
                detection_method="derived",
                fingerprint=hashlib.sha256(
                    json.dumps({"kind": "overdue_approval", "approval_id": a.id}, sort_keys=True).encode()
                ).hexdigest()[:64],
            )
            db.add(bottleneck)
            bottlenecks.append(bottleneck)
        
        # 2. Blocked steps
        steps = await db.execute(
            select(ProcessStep).where(
                ProcessStep.organization_id == caller.organization_id,
                ProcessStep.state == "blocked",
            )
        )
        for step in steps.scalars().all():
            if step.started_at and (utcnow() - step.started_at).total_seconds() > 86400:  # 24h
                bottleneck = ProcessBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="dependency_bottleneck",
                    severity="critical",
                    status="open",
                    execution_id=step.execution_id,
                    step_id=step.id,
                    title=f"Step blocked > 24h: {step.step_name}",
                    description=f"Step '{step.step_name}' blocked for > 24 hours",
                    wait_time_hours=(utcnow() - step.started_at).total_seconds() / 3600,
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "blocked_step", "step_id": step.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                )
                db.add(bottleneck)
                bottlenecks.append(bottleneck)
        
# 3. Capacity overload
        resource_slice = await canonical_resource_asset_service.derive_resource_operating_slice(
            db, caller=CallerAccess(organization_id=caller.organization_id, user_id=caller.user_id, employee_id=caller.employee_id, org_wide=True)
        )
        for r in await self._get_resources(db, caller):
            if r.is_constrained:
                bottleneck = ProcessBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="resource_capacity",
                    severity="critical",
                    status="open",
                    process_id=r.id,
                    title=f"Resource {r.name} ({r.kind}) over capacity",
                    description=f"Available: {r.available_capacity}, Committed: {r.committed_capacity}, Total: {r.total_capacity}",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "capacity_overload", "resource_id": r.id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                )
                db.add(bottleneck)
                bottlenecks.append(bottleneck)
        
        # 3b. Resource underutilization (from resource asset service)
        resource_conflicts = await canonical_resource_asset_service.derive_resource_conflicts(
            db, caller=CallerAccess(organization_id=caller.organization_id, user_id=caller.user_id, employee_id=caller.employee_id, org_wide=True)
        )
        for rc in resource_conflicts:
            if rc.conflict_kind == "underutilization":
                bottleneck = ProcessBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="underutilization",
                    severity="warning",
                    status="open",
                    affected_person_ids_json=[rc.resource_id] if rc.resource_kind == "person" else [],
                    affected_project_ids_json=[rc.resource_id] if rc.resource_kind != "person" else [],
                    title=f"Resource {rc.resource_id} underutilized",
                    description=f"Resource underutilized",
                    detected_at=utcnow(),
                    detected_by="system",
                    detection_method="derived",
                    fingerprint=hashlib.sha256(
                        json.dumps({"kind": "underutilization", "resource_id": rc.resource_id}, sort_keys=True).encode()
                    ).hexdigest()[:64],
                )
                db.add(bottleneck)
                bottlenecks.append(bottleneck)
        
        # 3c. Vendor contract expiring (from procurement vendor service)
        vendors = await db.execute(
            select(CanonicalVendor).where(
                CanonicalVendor.organization_id == caller.organization_id,
                CanonicalVendor.contract_expires_at.isnot(None),
                CanonicalVendor.contract_expires_at < utcnow() + timedelta(days=60),
                CanonicalVendor.auto_renew == False,
            )
        )
        for v in vendors.scalars().all():
            days_until = (v.contract_expires_at - utcnow()).days if v.contract_expires_at else 0
            bottleneck = ProcessBottleneck(
                organization_id=caller.organization_id,
                bottleneck_type="vendor_contract_expiring",
                severity="critical" if days_until <= 14 else "warning",
                status="open",
                title=f"Vendor contract expiring: {v.name}",
                description=f"Vendor {v.name} contract expires in {days_until} days, auto-renew disabled",
                detected_at=utcnow(),
                detected_by="system",
                detection_method="derived",
                fingerprint=hashlib.sha256(
                    json.dumps({"kind": "vendor_contract_expiring", "vendor_id": v.id}, sort_keys=True).encode()
                ).hexdigest()[:64],
            )
            db.add(bottleneck)
            bottlenecks.append(bottleneck)
        
        # 4. Procurement gaps
        demands = await self._get_demands(db, caller)
        for demand in demands:
            if not demand.is_fulfilled and demand.window_start < date.today():
                bottleneck = ProcessBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="procurement_gap",
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
                db.add(bottleneck)
                bottlenecks.append(bottleneck)
        
        # 5. Asset lifecycle risks
        assets = await self._get_assets(db, caller)
        for asset in assets:
            if asset.is_approaching_maintenance:
                bottleneck = ProcessBottleneck(
                    organization_id=caller.organization_id,
                    bottleneck_type="lifecycle_risk",
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
                db.add(bottleneck)
                bottlenecks.append(bottleneck)
        
        await db.flush()
        return bottlenecks


# Global instance
canonical_business_process_service = CanonicalBusinessProcessService()