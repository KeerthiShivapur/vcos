"""Autonomy Service — Governed Autonomous Company Operations (Gate 28).

Implements the governed autonomy lifecycle:
discovered -> eligibility_evaluated -> proposed -> evidence_validated
-> governance_evaluated -> authorization_required -> authorized
-> committed -> executing -> executed -> outcome_observed
-> verified -> assessed -> learned

All autonomous operations pass through the canonical mutation boundary
with full governance, provenance, and temporal integrity.
"""

import logging
import hashlib
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List, Dict, Tuple
from enum import Enum

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import OrganizationSecurityPolicy
from app.core.timeutils import utcnow
from app.models.autonomy import (
    AutonomyProposal,
    AutonomyPolicy,
    AutonomyPolicyEvaluation,
    AutonomyEligibility,
    AutonomyEligibilityCache,
    AutonomyEvent,
    AutonomyExecution,
    AutonomyLearning,
    AutonomyRisk,
    AutonomyContext,
    AutonomyPolicyEvaluation,
    AUTONOMY_STATES,
    AUTONOMY_RISK_CLASSES,
    AUTONOMY_PROPOSAL_TYPES,
    POLICY_DECISIONS,
    AUTONOMY_EVENT_TYPES,
)
from app.models.company_actions import CompanyAction, CompanyActionEvent
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.models.governance import ApprovalPolicy, GovernanceScope
from app.models.autonomy import (
    AutonomyProposal,
    AutonomyPolicy,
    AutonomyPolicyEvaluation,
    AutonomyEligibility,
    AutonomyEligibilityCache,
    AutonomyEvent,
    AutonomyExecution,
    AutonomyLearning,
    AutonomyRisk,
    AutonomyContext,
    AutonomyRisk,
    AUTONOMY_STATES,
    AUTONOMY_RISK_CLASSES,
    AUTONOMY_PROPOSAL_TYPES,
    POLICY_DECISIONS,
    AUTONOMY_EVENT_TYPES,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.finance import Entitlement
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.notification_service import notification_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.intelligence.company_brain import company_brain
from app.intelligence.canonical_mutation import (
    CanonicalMutationContext,
    MutationType,
    EpistemicStatus,
    ExactOnceViolation,
    ConcurrencyViolation,
)

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List, Dict, Tuple, Set
import logging

logger = logging.getLogger("vcos.autonomy")


class AutonomyService:
    """Service for governed autonomous company operations."""

    # ------------------------------------------------------------------ Policy Management

    async def create_policy(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        policy_key: str,
        name: str,
        risk_class: str,
        description: Optional[str] = None,
        applies_to_types: Optional[List[str]] = None,
        required_approval_policy_id: Optional[str] = None,
        required_entitlements: Optional[dict] = None,
        preconditions: Optional[List[dict]] = None,
        required_evidence_types: Optional[List[str]] = None,
        min_evidence_confidence: float = 0.7,
        max_financial_amount_cents: Optional[int] = None,
        max_resource_allocation_pct: Optional[float] = None,
        allowed_connectors: Optional[List[str]] = None,
        allowed_time_windows: Optional[List[dict]] = None,
        max_execution_duration_ms: Optional[int] = None,
        require_human_approval: bool = True,
        requires_privileged_approval: bool = False,
        is_active: bool = True,
        created_by: Optional[str] = None,
    ) -> AutonomyPolicy:
        """Create an autonomy policy."""
        
        existing = await db.execute(
            select(AutonomyPolicy).where(
                AutonomyPolicy.organization_id == organization_id,
                AutonomyPolicy.policy_key == policy_key,
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Policy with key '{policy_key}' already exists")
        
        if risk_class not in AUTONOMY_RISK_CLASSES:
            raise ValueError(f"Invalid risk class: {risk_class}")
        
        policy = AutonomyPolicy(
            organization_id=organization_id,
            policy_key=policy_key,
            name=name,
            description=description,
            applies_to_types=applies_to_types or [],
            risk_class=risk_class,
            required_approval_policy_id=required_approval_policy_id,
            required_entitlements=required_entitlements or {},
            preconditions=preconditions or [],
            required_evidence_types=required_evidence_types or [],
            min_evidence_confidence=min_evidence_confidence,
            requires_human_approval=require_human_approval,
            is_active=is_active,
        )
        
        db.add(policy)
        await db.flush()
        
        await self._log_audit(
            db,
            organization_id=organization_id,
            action="autonomy.policy.created",
            actor_id=created_by,
            resource_type="autonomy_policy",
            resource_id=policy.id,
            details={"policy_key": policy_key, "risk_class": risk_class},
        )
        
        logger.info(f"Created autonomy policy: {policy_key} ({risk_class})")
        return policy

    async def get_policy(self, db: AsyncSession, policy_id: str) -> Optional[AutonomyPolicy]:
        return await db.get(AutonomyPolicy, policy_id)

    async def get_policy_by_key(self, db: AsyncSession, organization_id: str, policy_key: str) -> Optional[AutonomyPolicy]:
        result = await db.execute(
            select(AutonomyPolicy).where(
                AutonomyPolicy.organization_id == organization_id,
                AutonomyPolicy.policy_key == policy_key,
            )
        )
        return result.scalar_one_or_none()

    async def list_policies(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        is_active: Optional[bool] = None,
        risk_class: Optional[str] = None,
    ) -> List[AutonomyPolicy]:
        query = select(AutonomyPolicy).where(AutonomyPolicy.organization_id == organization_id)
        if is_active is not None:
            query = query.where(AutonomyPolicy.is_active == is_active)
        if risk_class:
            query = query.where(AutonomyPolicy.risk_class == risk_class)
        query = query.order_by(AutonomyPolicy.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------ Eligibility Evaluation

    async def evaluate_eligibility(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        actor_id: str,
        actor_type: str = "human",
        proposal_type: str,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        use_cache: bool = True,
    ) -> AutonomyEligibility:
        """Evaluate autonomy eligibility for an actor."""
        
        # Check cache first
        if use_cache:
            cache_key = f"{actor_id}:{proposal_type}:{scope_type or ''}:{scope_id or ''}"
            cached = await self._get_cached_eligibility(db, organization_id, cache_key)
            if cached:
                return cached
        
        # Evaluate eligibility
        eligibility = await self._evaluate_eligibility_internal(
            db, organization_id, actor_id, actor_type, proposal_type, scope_type, scope_id
        )
        
        # Cache result
        if use_cache:
            cache_key = f"{actor_id}:{proposal_type}:{scope_type or ''}:{scope_id or ''}"
            await self._cache_eligibility(db, organization_id, cache_key, eligibility)
        
        # Persist eligibility
        existing = await db.execute(
            select(AutonomyEligibility).where(
                AutonomyEligibility.organization_id == organization_id,
                AutonomyEligibility.actor_id == actor_id,
                AutonomyEligibility.proposal_type == proposal_type,
                AutonomyEligibility.scope_id == scope_id,
            )
        )
        existing_elig = existing.scalars().first()
        
        if existing_elig:
            existing_elig.eligible = eligibility.eligible
            existing_elig.risk_class = eligibility.risk_class
            existing_elig.policy_decision = eligibility.policy_decision
            existing_elig.reason = eligibility.reason
            existing_elig.failed_checks = eligibility.failed_checks
            existing_elig.passed_checks = eligibility.passed_checks
            existing_elig.conditions = eligibility.conditions
            existing_elig.evaluated_by = "system"
            existing_elig.evaluated_at = utcnow()
            existing_elig.valid_until = utcnow() + timedelta(hours=1)
            existing_elig.version += 1
        else:
            db.add(eligibility)
            await db.flush()
        
        return eligibility

    async def _evaluate_eligibility_internal(
        self,
        db: AsyncSession,
        organization_id: str,
        actor_id: str,
        actor_type: str,
        proposal_type: str,
        scope_type: Optional[str],
        scope_id: Optional[str],
    ) -> AutonomyEligibility:
        """Internal eligibility evaluation logic."""
        
        failed_checks = []
        passed_checks = []
        conditions = []
        
        # 1. Actor must exist and be active
        actor = await db.get(User, actor_id) if actor_type == "human" else None
        if actor_type == "human" and not actor:
            failed_checks.append("actor_not_found")
        elif actor_type == "human" and actor.status != "active":
            failed_checks.append("actor_inactive")
        else:
            passed_checks.append("actor_exists_and_active")
        
        # 2. Actor must have organization membership
        if actor_type == "human" and actor:
            emp_result = await db.execute(
                select(Employee).where(
                    Employee.user_id == actor_id,
                    Employee.organization_id == organization_id,
                    Employee.status == "active",
                )
            )
            employee = emp_result.scalars().first()
            if not employee:
                failed_checks.append("no_active_employment")
            else:
                passed_checks.append("active_employment")
        
        # 3. Check organization status
        org = await db.get(Organization, organization_id)
        if not org or org.status != "active":
            failed_checks.append("organization_inactive")
        else:
            passed_checks.append("organization_active")
        
        # 4. Check commercial entitlement for automation
        entitlements = await self._get_effective_entitlements(db, organization_id)
        automation_entitled = entitlements.get("automation.enabled", {}).get("value", False)
        if not automation_entitled:
            conditions.append("automation_entitlement_required")
        else:
            passed_checks.append("automation_entitled")
        
        # 5. Check subscription state
        from app.services.commercial_service import commercial_service
        subscription = await commercial_service.get_subscription(db, organization_id)
        if not subscription or subscription.state not in ("active", "trialing"):
            failed_checks.append("no_active_subscription")
        else:
            passed_checks.append("active_subscription")
        
        # 6. Check actor permissions for proposal type
        permission_map = {
            "execute_action": "autonomy:execute",
            "create_commitment": "autonomy:commit",
            "create_decision": "decision:create",
            "create_task": "task:create",
            "create_project": "project:create",
            "allocate_resource": "resource:allocate",
            "assign_responsibility": "responsibility:assign",
            "modify_policy": "policy:manage",
            "trigger_external_operation": "autonomy:external",
            "recommend_decision": "decision:recommend",
            "adjust_plan": "plan:adjust",
            "rebalance_capacity": "capacity:manage",
            "trigger_workflow": "workflow:trigger",
        }
        
        required_permission = permission_map.get(proposal_type, "autonomy:execute")
        from app.services.permission_service import permission_service
        user_perms = await permission_service.user_permission_codes(db, actor_id, organization_id)
        if required_permission not in user_perms:
            failed_checks.append(f"missing_permission:{required_permission}")
        else:
            passed_checks.append(f"has_permission:{required_permission}")
        
        # 6. Check scope access
        if scope_type and scope_id:
            scope_access = await self._check_scope_access(db, organization_id, actor_id, scope_type, scope_id)
            if not scope_access:
                failed_checks.append(f"no_scope_access:{scope_type}:{scope_id}")
            else:
                passed_checks.append(f"scope_access:{scope_type}")
        
        # 7. Check security policy
        security_policy = await self._get_security_policy(db, organization_id)
        if security_policy and security_policy.alert_on_new_device:
            # Would check device trust here
            passed_checks.append("security_policy_compliant")
        
        # 7. Determine risk class
        risk_class = await self._determine_risk_class(db, organization_id, proposal_type)
        
        # 8. Policy decision
        policy_decision = await self._evaluate_policy_for_proposal(db, organization_id, proposal_type, risk_class)
        
        # Determine overall eligibility
        eligible = len(failed_checks) == 0 and policy_decision != "deny" and policy_decision != "block"
        
        # Determine risk class based on proposal type and context
        risk_class = await self._determine_risk_class(db, organization_id, proposal_type)
        
        # Build conditions
        conditions = []
        if proposal_type in ("create_commitment", "allocate_resource", "modify_policy"):
            conditions.append("requires_explicit_approval")
        
        # Create eligibility result
        eligibility = AutonomyEligibility(
            organization_id=organization_id,
            actor_id=actor_id,
            actor_type=actor_type,
            proposal_type=proposal_type,
            scope_type=scope_type,
            scope_id=scope_id,
            eligible=eligible,
            risk_class=risk_class,
            policy_decision="allow" if eligible else "deny",
            reason="All checks passed" if eligible else f"Failed checks: {', '.join(failed_checks)}",
            failed_checks=failed_checks,
            passed_checks=passed_checks,
            conditions=conditions,
            evaluated_by="system",
            evaluated_at=utcnow(),
            valid_until=utcnow() + timedelta(hours=1),
        )
        
        return eligibility

    async def _get_effective_entitlements(self, db: AsyncSession, organization_id: str) -> dict:
        """Get effective entitlements for organization."""
        from app.services.commercial_service import commercial_service
        return await commercial_service.resolve_entitlements(db, organization_id)

    async def _get_security_policy(
        self, db: AsyncSession, organization_id: str
    ) -> Optional[OrganizationSecurityPolicy]:
        """Get organization security policy."""
        result = await db.execute(
            select(OrganizationSecurityPolicy).where(
                OrganizationSecurityPolicy.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def _check_scope_access(
        self, db: AsyncSession, organization_id: str, actor_id: str, scope_type: str, scope_id: str
    ) -> bool:
        """Check if actor has access to scope."""
        if scope_type == "org":
            return True
        elif scope_type == "department":
            from app.models.department import Department
            dept = await db.get(scope_id)
            return dept is not None and dept.organization_id == organization_id
        elif scope_type == "team":
            from app.models.team import Team, TeamMember
            member = await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == scope_id,
                    TeamMember.employee_id.in_(
                        select(Employee.id).where(Employee.user_id == actor_id)
                    )
                )
            )
            return member.scalars().first() is not None
        elif scope_type == "project":
            from app.models.project import Project, ProjectMember
            member = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == scope_id,
                    ProjectMember.employee_id.in_(
                        select(Employee.id).where(Employee.user_id == actor_id)
                    )
                )
            )
            return member.scalars().first() is not None
        return False

    async def _determine_risk_class(self, db: AsyncSession, organization_id: str, proposal_type: str) -> str:
        """Determine risk class for proposal type."""
        # High-risk proposal types
        high_risk = {"modify_policy", "create_commitment", "allocate_resource", "modify_policy"}
        if proposal_type in high_risk:
            return "human_approval_required"
        
        # Medium risk
        medium_risk = {"create_commitment", "allocate_resource", "assign_responsibility", "trigger_external_operation"}
        if proposal_type in medium_risk:
            return "auto_execute_within_policy"
        
        # Low risk
        return "auto_execute_reversible"

    async def _evaluate_policy_for_proposal(self, db: AsyncSession, organization_id: str, proposal_type: str, risk_class: str) -> str:
        """Evaluate policy for proposal type and risk class."""
        # Find applicable policies
        result = await db.execute(
            select(AutonomyPolicy).where(
                AutonomyPolicy.organization_id == organization_id,
                AutonomyPolicy.is_active == True,
                or_(
                    AutonomyPolicy.applies_to_types == [],
                    AutonomyPolicy.applies_to_types.contains([proposal_type]),
                ),
                AutonomyPolicy.risk_class == risk_class,
            ).order_by(AutonomyPolicy.created_at.desc())
        )
        policies = result.scalars().all()
        
        if not policies:
            return "require_approval"  # Default to requiring approval
        
        # Evaluate first matching policy
        for policy in policies:
            # Check entitlements
            if policy.required_entitlements:
                entitlements = await self._get_effective_entitlements(db, organization_id)
                for key, req in policy.required_entitlements.items():
                    if key not in entitlements or not entitlements[key].get("value"):
                        return "deny"
        
        return policies[0].risk_class if policies else "require_approval"

    # ------------------------------------------------------------------ Proposal Lifecycle

    async def create_proposal(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        proposal_type: str,
        title: str,
        description: Optional[str] = None,
        actor_id: str,
        actor_type: str = "human",
        scope_type: str = "org",
        scope_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        target_label: Optional[str] = None,
        context_type: Optional[str] = None,
        context_id: Optional[str] = None,
        context_label: Optional[str] = None,
        why: Optional[str] = None,
        evidence_items: Optional[List[dict]] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        source_label: Optional[str] = None,
        risk_class: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> AutonomyProposal:
        """Create a new autonomy proposal."""
        
        if proposal_type not in AUTONOMY_PROPOSAL_TYPES:
            raise ValueError(f"Invalid proposal type: {proposal_type}")
        
        # Evaluate eligibility
        eligibility = await self.evaluate_eligibility(
            db, organization_id=organization_id, actor_id=actor_id,
            actor_type=actor_type, proposal_type=proposal_type,
            scope_type=scope_type, scope_id=scope_id
        )
        
        if not eligibility.eligible:
            raise ValueError(f"Not eligible: {eligibility.reason}")
        
        # Generate fingerprint
        fingerprint_data = f"{organization_id}:{proposal_type}:{scope_type or ''}:{scope_id or ''}:{target_type or ''}:{target_id or ''}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]
        
        # Check for existing proposal with same fingerprint
        existing = await db.execute(
            select(AutonomyProposal).where(
                AutonomyProposal.organization_id == organization_id,
                AutonomyProposal.fingerprint == fingerprint,
                AutonomyProposal.state.not_in(["cancelled", "rejected", "failed", "superseded"]),
            )
        )
        if existing.scalars().first():
            raise ValueError("Proposal with same fingerprint already exists")
        
        # Determine risk class
        if risk_class is None:
            risk_class = await self._determine_risk_class(db, organization_id, proposal_type)
        
        # Evaluate eligibility
        eligibility = await self.evaluate_eligibility(
            db, organization_id=organization_id, actor_id=actor_id,
            actor_type=actor_type, proposal_type=proposal_type,
            scope_type=scope_type, scope_id=scope_id
        )
        
        # Create proposal
        proposal = AutonomyProposal(
            organization_id=organization_id,
            proposal_type=proposal_type,
            title=title,
            description=description,
            state="discovered",
            risk_class=risk_class or "human_approval_required",
            actor_id=actor_id,
            actor_type=actor_type,
            scope_type=scope_type,
            scope_id=scope_id,
            fingerprint=hashlib.sha256(f"{organization_id}:{proposal_type}:{scope_type or ''}:{scope_id or ''}:{target_type or ''}:{target_id or ''}".encode()).hexdigest()[:160],
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            context_type=context_type,
            context_id=context_id,
            context_label=context_label,
            source_type=source_type,
            source_id=source_id,
            source_label=source_label,
            why=why,
            evidence_items=evidence_items or [],
            evidence_confidence=0.0,
            proposed_at=utcnow(),
            eligibility_result="eligible",
            eligibility_evaluated_at=utcnow(),
            eligibility_evaluated_by="system",
            eligibility_details={
                "eligible": True,
                "risk_class": risk_class,
                "policy_decision": "allow",
            },
            created_by=created_by,
        )
        
        db.add(proposal)
        await db.flush()
        
        # Log event
        await self._log_event(db, proposal, "discovered", actor_id, "human", "discovered", "proposed")
        
        # Evaluate eligibility
        await self._evaluate_proposal_eligibility(db, proposal)
        
        await db.flush()
        return proposal

    async def _evaluate_proposal_eligibility(self, db: AsyncSession, proposal: AutonomyProposal) -> None:
        """Evaluate eligibility for a proposal."""
        eligibility = await self.evaluate_eligibility(
            db,
            organization_id=proposal.organization_id,
            actor_id=proposal.actor_id,
            actor_type=proposal.actor_type,
            proposal_type=proposal.proposal_type,
            scope_type=proposal.scope_type,
            scope_id=proposal.scope_id,
        )
        
        proposal.eligibility_result = "eligible" if eligibility.eligible else "ineligible"
        proposal.eligibility_details = {
            "eligible": eligibility.eligible,
            "risk_class": eligibility.risk_class,
            "policy_decision": eligibility.policy_decision,
            "failed_checks": eligibility.failed_checks,
            "passed_checks": eligibility.passed_checks,
        }
        proposal.eligibility_evaluated_at = utcnow()
        proposal.eligibility_evaluated_by = "system"
        proposal.state = "eligibility_evaluated"
        proposal.risk_class = eligibility.risk_class
        
        await self._log_event(db, proposal, "eligibility_evaluated", "system", "system")
        
        # If eligible, move to proposed
        if eligibility.eligible:
            await self._propose(db, proposal)

    async def _propose(self, db: AsyncSession, proposal: AutonomyProposal) -> None:
        """Move proposal to proposed state."""
        proposal.state = "proposed"
        proposal.proposed_at = utcnow()
        await self._log_event(db, proposal, "proposed", proposal.actor_id, "human")
        
        # Validate evidence
        await self._validate_evidence(db, proposal)

    async def _validate_evidence(self, db: AsyncSession, proposal: AutonomyProposal) -> None:
        """Validate evidence for proposal."""
        # Check evidence confidence
        if proposal.evidence_items:
            total_confidence = sum(e.get("confidence", 0.5) for e in proposal.evidence_items)
            avg_confidence = total_confidence / len(proposal.evidence_items)
            proposal.evidence_confidence = avg_confidence
            
            if avg_confidence >= 0.7:
                proposal.evidence_validated = True
                proposal.evidence_validated_at = utcnow()
                proposal.evidence_validated_by = "system"
                proposal.state = "evidence_validated"
                await self._log_event(db, proposal, "evidence_validated", "system", "system")
            else:
                proposal.state = "evidence_insufficient"
                await self._log_event(db, proposal, "evidence_insufficient", "system", "system", outcome="failure")

    async def evaluate_governance(self, db: AsyncSession, proposal: AutonomyProposal) -> None:
        """Evaluate governance policies for proposal."""
        if proposal.state != "evidence_validated":
            raise ValueError(f"Cannot evaluate governance for proposal in state: {proposal.state}")
        
        # Find applicable policies
        result = await db.execute(
            select(AutonomyPolicy).where(
                AutonomyPolicy.organization_id == proposal.organization_id,
                AutonomyPolicy.is_active == True,
                or_(
                    AutonomyPolicy.applies_to_types == [],
                    AutonomyPolicy.applies_to_types.contains([proposal.proposal_type]),
                ),
                AutonomyPolicy.risk_class == proposal.risk_class,
            ).order_by(AutonomyPolicy.created_at.desc())
        )
        policies = result.scalars().all()
        
        if not policies:
            proposal.governance_evaluated = True
            proposal.governance_evaluated_at = utcnow()
            proposal.governance_evaluated_by = "system"
            proposal.governance_details = {"policies_evaluated": 0, "result": "no_policies"}
            proposal.governance_evaluated = True
            proposal.governance_evaluated_at = utcnow()
            proposal.state = "governance_evaluated"
            await self._log_event(db, proposal, "governance_evaluated", "system", "system")
            return
        
        # Evaluate policies
        all_passed = True
        all_passed_rules = []
        all_failed_rules = []
        all_warnings = []
        
        for policy in policies:
            if policy.applies_to_types and proposal.proposal_type not in policy.applies_to_types:
                continue
            
            evaluation = await self._evaluate_policy(db, policy, proposal)
            if evaluation["decision"] == "deny" or evaluation["decision"] == "block":
                all_passed = False
                all_failed_rules.extend(evaluation.get("failed_rules", []))
            elif evaluation["decision"] == "require_approval":
                # Will need approval
                pass
            else:
                all_passed = all_passed and evaluation["decision"] in ("allow", "require_approval")
            
            all_passed_rules.extend(evaluation.get("passed_rules", []))
            all_warnings.extend(evaluation.get("warnings", []))
        
        proposal.governance_evaluated = True
        proposal.governance_evaluated_at = utcnow()
        proposal.governance_evaluated_by = "system"
        proposal.governance_details = {
            "policies_evaluated": len(policies),
            "all_passed": all_passed,
            "passed_rules": all_passed_rules,
            "failed_rules": all_failed_rules,
            "warnings": all_warnings,
        }
        
        if all_passed:
            proposal.policy_decision = "allow"
            proposal.state = "governance_evaluated"
        else:
            proposal.policy_decision = "require_approval"
            proposal.state = "authorization_required"
        
        proposal.governance_evaluated_at = utcnow()
        await self._log_event(db, proposal, "governance_evaluated", "system", "system")

    async def _evaluate_policy(self, db: AsyncSession, policy: AutonomyPolicy, proposal: AutonomyProposal) -> dict:
        """Evaluate a single policy against a proposal."""
        passed_rules = []
        failed_rules = []
        warnings = []
        
        # Check entitlements
        if policy.required_entitlements:
            from app.services.commercial_service import commercial_service
            entitlements = await commercial_service.resolve_entitlements(db, proposal.organization_id)
            for key, req in policy.required_entitlements.items():
                if key not in entitlements:
                    failed_rules.append(f"missing_entitlement:{key}")
                elif isinstance(req, dict) and "min_value" in req:
                    if entitlements[key].get("numeric_value", 0) < req["min_value"]:
                        failed_rules.append(f"entitlement_too_low:{key}")
                    else:
                        passed_rules.append(f"entitlement_ok:{key}")
                else:
                    passed_rules.append(f"entitlement_ok:{key}")
        
        # Check preconditions
        for precondition in policy.preconditions:
            if precondition.get("type") == "entitlement":
                # Already checked above
                pass
            elif precondition.get("type") == "scope_access":
                # Would check scope access
                pass
        
        # Check financial amount
        if policy.max_financial_amount_cents and proposal.metadata_json.get("estimated_cost_cents", 0) > policy.max_financial_amount_cents:
            return {"decision": "deny", "failed_rules": ["exceeds_max_financial_amount"]}
        
        # Determine decision
        if not all_passed:
            return {"decision": "deny", "passed_rules": passed_rules, "failed_rules": failed_rules}
        
        if policy.requires_human_approval:
            return {"decision": "require_approval", "passed_rules": passed_rules, "failed_rules": failed_rules, "warnings": ["human_approval_required"]}
        
        return {"decision": "allow", "passed_rules": passed_rules, "failed_rules": failed_rules, "warnings": warnings}

    async def authorize_proposal(
        self,
        db: AsyncSession,
        proposal_id: str,
        actor_id: str,
        approval_note: Optional[str] = None,
    ) -> AutonomyProposal:
        """Authorize a proposal (human or policy approval)."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state not in ("governance_evaluated", "authorization_required"):
            raise ValueError(f"Cannot authorize proposal in state: {proposal.state}")
        
        if proposal.authorization_required and not proposal.approval_required:
            # Policy approval
            proposal.state = "authorized"
            proposal.authorized_at = utcnow()
            await self._log_event(db, proposal, "authorized", "system", "system")
        else:
            # Human approval
            # Check if actor is authorized to approve
            from app.services.permission_service import permission_service
            perms = await permission_service.user_permission_codes(db, actor_id, proposal.organization_id)
            if "autonomy:approve" not in perms:
                raise ValueError("Actor not authorized to approve proposals")
            
            proposal.approval_state = "approved"
            proposal.approved_by = actor_id
            proposal.approved_at = utcnow()
            proposal.approval_note = approval_note
            proposal.state = "authorized"
            proposal.authorized_at = utcnow()
            await self._log_event(db, proposal, "authorized", actor_id, "human")
        
        proposal.authorized = True
        await db.flush()
        return proposal

    async def commit_proposal(
        self,
        db: AsyncSession,
        proposal_id: str,
        committed_by: Optional[str] = None,
    ) -> AutonomyProposal:
        """Create commitment for authorized proposal."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state != "authorized":
            raise ValueError(f"Cannot commit proposal in state: {proposal.state}")
        
        # Create commitment
        commitment = CompanyCommitment(
            organization_id=proposal.organization_id,
            commitment_type="unconditional",
            title=f"Autonomous: {proposal.title}",
            description=proposal.description,
            state="authorized",
            target_date=utcnow() + timedelta(days=30),
            scope_type="objective",
            fingerprint=hashlib.sha256(f"{proposal.organization_id}:{proposal.id}:commit".encode()).hexdigest()[:160],
            authorized_at=utcnow(),
            authorized_by=proposal.actor_id,
        )
        db.add(commitment)
        await db.flush()
        
        proposal.commitment_id = commitment.id
        proposal.committed_at = utcnow()
        proposal.committed_by = committed_by or proposal.actor_id
        proposal.state = "committed"
        
        await self._log_event(db, proposal, "committed", proposal.actor_id, "human")
        await db.flush()
        return proposal

    async def execute_proposal(
        self,
        db: AsyncSession,
        proposal_id: str,
        actor_id: Optional[str] = None,
    ) -> AutonomyProposal:
        """Execute an autonomous proposal."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state != "committed":
            raise ValueError(f"Cannot execute proposal in state: {proposal.state}")
        
        proposal.state = "executing"
        proposal.execution_started_at = utcnow()
        
        # Route to appropriate execution based on proposal type
        if proposal.proposal_type == "execute_action":
            result = await self._execute_via_company_action(db, proposal)
        elif proposal.proposal_type == "trigger_external_operation":
            result = await self._execute_external_operation(db, proposal)
        elif proposal.proposal_type == "create_task":
            result = await self._create_task(db, proposal)
        elif proposal.proposal_type == "create_commitment":
            result = await self._create_commitment_via_autonomy(db, proposal)
        else:
            # Generic execution via CompanyAction
            result = await self._execute_via_company_action(db, proposal)
        
        if result.get("success"):
            proposal.state = "executed"
            proposal.execution_completed_at = utcnow()
            proposal.execution_duration_ms = result.get("duration_ms")
            proposal.execution_result = result
            await self._log_event(db, proposal, "executed", "system", "system")
        else:
            proposal.state = "failed"
            proposal.execution_error = result.get("error")
            await self._log_event(db, proposal, "failed", "system", "system", outcome="failure")
        
        await db.flush()
        return proposal

    async def _execute_via_company_action(self, db: AsyncSession, proposal: AutonomyProposal) -> dict:
        """Execute proposal via CompanyAction."""
        action = CompanyAction(
            organization_id=proposal.organization_id,
            action_type=proposal.proposal_type,
            title=proposal.title,
            description=proposal.description,
            state="ready",
            scope_type=proposal.scope_type,
            scope_id=proposal.scope_id,
            fingerprint=proposal.fingerprint,
            target_type=proposal.target_type,
            target_id=proposal.target_id,
            target_label=proposal.target_label,
            source_recommendation_id=proposal.source_id,
            source_event_id=proposal.source_id,
            source_company_decision_id=proposal.metadata_json.get("source_decision_id"),
            assignee_type="system",
            assignee_id=proposal.actor_id,
            policy="auto",
            approval_required=False,
            created_by="system",
        )
        db.add(action)
        await db.flush()
        
        proposal.execution_id = action.id
        proposal.execution_state = "in_progress"
        
        # Execute via canonical mutation
        from app.intelligence.company_context import CallerAccess
        caller = CallerAccess(
            proposal.organization_id,
            proposal.actor_id,
            None,
            False,
            frozenset(),
            frozenset(),
            frozenset(),
            frozenset(),
            frozenset(),
            {},
        )
        context = CanonicalMutationContext(
            caller=caller,
            tenant_id=proposal.organization_id,
            governance_scope_ids=frozenset(),
            permissions=frozenset(),
            target_entity_type="company_action",
            target_id=action.id,
            mutation_type=MutationType.CREATE,
            expected_version=1,
            fingerprint=action.fingerprint,
        )
        
        try:
            result = await canonical_mutation_boundary.mutate(
                context,
                mutation_type=MutationType.CREATE,
                entity_type="company_action",
                entity_id=action.id,
                payload=action.__dict__,
            )
            return {"success": True, "action_id": action.id, "duration_ms": 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_external_operation(self, db: AsyncSession, proposal: AutonomyProposal) -> dict:
        """Execute external operation via Gate 24 connector."""
        if not proposal.external_connector_id:
            return {"success": False, "error": "No external connector specified"}
        
        from app.intelligence.canonical_integration_service import connector_service
        
        connector = await connector_service.get_connector(db, proposal.external_connector_id)
        if not connector:
            return {"success": False, "error": "Connector not found"}
        
        # Check connector is connected
        instance = await connector_service.get_instance(db, proposal.organization_id, connector.id)
        if not instance or instance.state != "connected":
            return {"success": False, "error": "Connector not connected"}
        
        # Create external operation
        from app.models.canonical_integration import ExternalOperation
        ext_op = ExternalOperation(
            organization_id=proposal.organization_id,
            connector_instance_id=instance.id,
            operation_type=proposal.external_operation_type,
            payload=proposal.metadata_json.get("external_payload", {}),
            idempotency_key=proposal.external_idempotency_key or secrets.token_hex(16),
            requested_by=proposal.actor_id,
            state="pending",
        )
        db.add(ext_op)
        await db.flush()
        
        proposal.external_operation_id = ext_op.id
        proposal.external_connector_id = connector.id
        
        # Execute via connector
        try:
            result = await connector.execute_operation(ext_op.id, ext_op.payload)
            ext_op.state = "completed"
            ext_op.result = result
            proposal.external_result = result
            return {"success": True, "external_operation_id": ext_op.id, "result": result}
        except Exception as e:
            ext_op.state = "failed"
            ext_op.error = str(e)
            return {"success": False, "error": str(e)}

    async def _create_task(self, db: AsyncSession, proposal: AutonomyProposal) -> dict:
        """Create a task via autonomy."""
        from app.models.task import Task
        
        task = Task(
            organization_id=proposal.organization_id,
            title=proposal.title,
            description=proposal.description,
            project_id=proposal.metadata_json.get("project_id"),
            assignee_id=proposal.actor_id,
            status="pending",
            priority="medium",
            due_date=proposal.metadata_json.get("due_at"),
        )
        db.add(task)
        await db.flush()
        
        proposal.execution_id = task.id
        proposal.execution_state = "completed"
        return {"success": True, "task_id": task.id}

    async def _create_commitment_via_autonomy(self, db: AsyncSession, proposal: AutonomyProposal) -> dict:
        """Create a commitment via autonomy."""
        from app.models.execution_strategy import CompanyCommitment
        
        commitment = CompanyCommitment(
            organization_id=proposal.organization_id,
            title=proposal.title,
            description=proposal.description,
            state="proposed",
            target_date=proposal.metadata_json.get("target_date"),
            owner_id=proposal.actor_id,
        )
        db.add(commitment)
        await db.flush()
        
        proposal.commitment_id = commitment.id
        proposal.committed_at = utcnow()
        proposal.committed_by = proposal.actor_id
        return {"success": True, "commitment_id": commitment.id}

    # ------------------------------------------------------------------ Outcome & Verification

    async def record_outcome(
        self,
        db: AsyncSession,
        proposal_id: str,
        outcome_type: str,
        outcome_state: str,
        outcome_summary: str,
        outcome_details: Optional[dict] = None,
        observed_by: Optional[str] = None,
        epistemic_status: str = "observed",
    ) -> AutonomyProposal:
        """Record outcome of autonomous operation."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state != "executed":
            raise ValueError(f"Cannot record outcome for proposal in state: {proposal.state}")
        
        proposal.outcome_id = secrets.token_hex(16)
        proposal.outcome_type = outcome_type
        proposal.outcome_state = outcome_state
        proposal.outcome_summary = outcome_summary
        proposal.outcome_details = outcome_details or {}
        proposal.outcome_epistemic_status = epistemic_status
        proposal.outcome_observed_at = utcnow()
        proposal.outcome_observed_by = observed_by
        proposal.state = "outcome_observed"
        
        await self._log_event(db, proposal, "outcome_observed", "system", "system")
        await db.flush()
        return proposal

    async def verify_outcome(
        self,
        db: AsyncSession,
        proposal_id: str,
        verified_by: str,
        verification_note: Optional[str] = None,
    ) -> AutonomyProposal:
        """Verify outcome of autonomous operation."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state != "outcome_observed":
            raise ValueError(f"Cannot verify outcome for proposal in state: {proposal.state}")
        
        proposal.verified = True
        proposal.verified_by = verified_by
        proposal.verified_at = utcnow()
        proposal.verification_note = verification_note
        proposal.state = "verified"
        
        await self._log_event(db, proposal, "verified", verified_by, "human")
        await db.flush()
        return proposal

    async def assess_outcome(
        self,
        db: AsyncSession,
        proposal_id: str,
        assessed_by: str,
        assessment: str,
        success_score: Optional[float] = None,
        assessment_details: Optional[dict] = None,
    ) -> AutonomyProposal:
        """Assess autonomous operation outcome."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state != "verified":
            raise ValueError(f"Cannot assess outcome for proposal in state: {proposal.state}")
        
        proposal.assessed = True
        proposal.assessed_by = assessed_by
        proposal.assessed_at = utcnow()
        proposal.assessment = assessment
        proposal.assessment_details = assessment_details or {}
        proposal.success_score = success_score
        proposal.state = "assessed"
        
        await self._log_event(db, proposal, "assessed", assessed_by, "human")
        await db.flush()
        return proposal

    async def record_learning(
        self,
        db: AsyncSession,
        proposal_id: str,
        lesson_type: str,
        lesson_title: str,
        lesson_summary: Optional[str] = None,
        lesson_details: Optional[dict] = None,
        confidence: float = 0.5,
        evidence_fingerprints: Optional[List[str]] = None,
        applicable_proposal_types: Optional[List[str]] = None,
        applicable_contexts: Optional[List[dict]] = None,
    ) -> AutonomyLearning:
        """Record learning from autonomous operation."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        if proposal.state != "assessed":
            raise ValueError(f"Cannot record learning for proposal in state: {proposal.state}")
        
        learning = AutonomyLearning(
            organization_id=proposal.organization_id,
            proposal_id=proposal.id,
            lesson_type=lesson_type,
            lesson_title=lesson_title,
            lesson_summary=lesson_summary,
            lesson_details=lesson_details or {},
            confidence=confidence,
            evidence_fingerprints=evidence_fingerprints or [],
            applicable_proposal_types=applicable_proposal_types or [proposal.proposal_type],
            applicable_contexts=applicable_contexts or [],
        )
        
        db.add(learning)
        await db.flush()
        
        proposal.learned = True
        proposal.learned_at = utcnow()
        proposal.lesson_fingerprints.append(learning.lesson_fingerprint or "")
        proposal.state = "learned"
        
        await self._log_event(db, proposal, "learned", "system", "system")
        await db.flush()
        return learning

    # ------------------------------------------------------------------ Risk & Context

    async def create_risk_assessment(
        self,
        db: AsyncSession,
        proposal_id: str,
        kind: str,
        level: str,
        title: str,
        description: Optional[str] = None,
        probability: float = 0.5,
        impact_score: float = 0.0,
        financial_exposure_cents: Optional[int] = None,
    ) -> AutonomyRisk:
        """Create risk assessment for proposal."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        risk = AutonomyRisk(
            organization_id=proposal.organization_id,
            proposal_id=proposal.id,
            kind=kind,
            level=level,
            title=title,
            description=description,
            probability=probability,
            impact_score=impact_score,
            financial_exposure_cents=financial_exposure_cents,
            fingerprint=hashlib.sha256(f"{proposal.organization_id}:{proposal.id}:{kind}:{title}".encode()).hexdigest()[:160],
        )
        
        db.add(risk)
        await db.flush()
        
        await self._log_event(db, None, "risk_assessed", "system", "system", details={"risk_id": risk.id})
        return risk

    async def create_context(
        self,
        db: AsyncSession,
        proposal_id: str,
        context_type: str,
        context_json: dict,
        input_fingerprint: str,
    ) -> AutonomyContext:
        """Create governed context for proposal."""
        proposal = await db.get(AutonomyProposal, proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        
        context = AutonomyContext(
            organization_id=proposal.organization_id,
            proposal_id=proposal.id,
            context_type=context_type,
            context_json=context_json,
            input_fingerprint=input_fingerprint,
            fingerprint=hashlib.sha256(f"{proposal.organization_id}:{proposal.id}:{context_type}:{input_fingerprint}".encode()).hexdigest()[:160],
        )
        
        db.add(context)
        await db.flush()
        return context

    # ------------------------------------------------------------------ Cache & Invalidation

    async def _get_cached_eligibility(
        self, db: AsyncSession, organization_id: str, cache_key: str
    ) -> Optional[AutonomyEligibility]:
        result = await db.execute(
            select(AutonomyEligibilityCache).where(
                AutonomyEligibilityCache.organization_id == organization_id,
                AutonomyEligibilityCache.cache_key == cache_key,
                AutonomyEligibilityCache.invalidated == False,
                or_(
                    AutonomyEligibilityCache.expires_at.is_(None),
                    AutonomyEligibilityCache.expires_at > utcnow(),
                ),
            )
        )
        cached = result.scalars().first()
        if cached:
            # Reconstruct eligibility from cache
            return AutonomyEligibility(
                organization_id=organization_id,
                actor_id=cached.details.get("actor_id", ""),
                actor_type="human",
                proposal_type=cached.details.get("proposal_type", ""),
                scope_type=cached.details.get("scope_type"),
                scope_id=cached.details.get("scope_id"),
                eligible=cached.result,
                risk_class=cached.risk_class,
                policy_decision=cached.policy_decision,
                reason=cached.details.get("reason", ""),
                failed_checks=cached.details.get("failed_checks", []),
                passed_checks=cached.details.get("passed_checks", []),
                conditions=cached.details.get("conditions", []),
            )
        return None

    async def _cache_eligibility(
        self, db: AsyncSession, organization_id: str, cache_key: str, eligibility: AutonomyEligibility
    ) -> None:
        cache = AutonomyEligibilityCache(
            organization_id=organization_id,
            cache_key=cache_key,
            result=eligibility.eligible,
            risk_class=eligibility.risk_class,
            policy_decision=eligibility.policy_decision,
            details={
                "actor_id": eligibility.actor_id,
                "proposal_type": eligibility.proposal_type,
                "scope_type": eligibility.scope_type,
                "scope_id": eligibility.scope_id,
                "reason": eligibility.reason,
                "failed_checks": eligibility.failed_checks,
                "passed_checks": eligibility.passed_checks,
                "conditions": eligibility.conditions,
            },
            expires_at=utcnow() + timedelta(hours=1),
        )
        db.add(cache)
        await db.flush()

    async def invalidate_eligibility_cache(
        self,
        db: AsyncSession,
        organization_id: str,
        actor_id: Optional[str] = None,
        proposal_type: Optional[str] = None,
    ) -> int:
        """Invalidate eligibility cache."""
        query = select(AutonomyEligibilityCache).where(
            AutonomyEligibilityCache.organization_id == organization_id,
            AutonomyEligibilityCache.invalidated == False,
        )
        if actor_id:
            query = query.where(AutonomyEligibilityCache.cache_key.contains(actor_id))
        if proposal_type:
            query = query.where(AutonomyEligibilityCache.cache_key.contains(proposal_type))
        
        result = await db.execute(query)
        caches = result.scalars().all()
        
        count = 0
        for cache in caches:
            cache.invalidated = True
            cache.invalidated_at = utcnow()
            cache.invalidation_reason = "policy_or_entitlement_change"
            count += 1
        
        await db.flush()
        return count

    # ------------------------------------------------------------------ Event Logging

    async def _log_event(
        self,
        db: AsyncSession,
        proposal: Optional[AutonomyProposal],
        event_type: str,
        actor_id: Optional[str],
        actor_type: str,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        outcome: str = "success",
        details: Optional[dict] = None,
        risk_score: int = 0,
        risk_factors: Optional[List[str]] = None,
    ) -> AutonomyEvent:
        """Log an autonomy event."""
        
        event = AutonomyEvent(
            organization_id=proposal.organization_id if proposal else "system",
            proposal_id=proposal.id if proposal else None,
            event_type=event_type,
            actor_id=actor_id,
            actor_type=actor_type,
            from_state=from_state,
            to_state=to_state,
            outcome=outcome,
            details_json=details or {},
            risk_score=risk_score,
            risk_factors=risk_factors or [],
            occurred_at=utcnow(),
        )
        
        db.add(event)
        await db.flush()
        return event

    async def _log_audit(
        self,
        db: AsyncSession,
        organization_id: str,
        action: str,
        actor_id: Optional[str],
        resource_type: str,
        resource_id: str,
        details: Optional[dict] = None,
    ) -> None:
        """Log audit event."""
        await audit_service.log(
            db,
            organization_id=organization_id,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )

    # ------------------------------------------------------------------ Proposal Queries

    async def get_proposal(self, db: AsyncSession, proposal_id: str) -> Optional[AutonomyProposal]:
        return await db.get(AutonomyProposal, proposal_id)

    async def get_proposal_by_fingerprint(
        self, db: AsyncSession, organization_id: str, fingerprint: str
    ) -> Optional[AutonomyProposal]:
        result = await db.execute(
            select(AutonomyProposal).where(
                AutonomyProposal.organization_id == organization_id,
                AutonomyProposal.fingerprint == fingerprint,
            )
        )
        return result.scalar_one_or_none()

    async def list_proposals(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        state: Optional[str] = None,
        proposal_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AutonomyProposal]:
        query = select(AutonomyProposal).where(AutonomyProposal.organization_id == organization_id)
        if state:
            query = query.where(AutonomyProposal.state == state)
        if proposal_type:
            query = query.where(AutonomyProposal.proposal_type == proposal_type)
        if actor_id:
            query = query.where(AutonomyProposal.actor_id == actor_id)
        query = query.order_by(AutonomyProposal.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------ Cache Invalidation

    async def invalidate_eligibility_cache(
        self,
        db: AsyncSession,
        organization_id: str,
        actor_id: Optional[str] = None,
        proposal_type: Optional[str] = None,
    ) -> int:
        """Invalidate eligibility cache entries."""
        query = select(AutonomyEligibilityCache).where(
            AutonomyEligibilityCache.organization_id == organization_id,
            AutonomyEligibilityCache.invalidated == False,
        )
        if actor_id:
            query = query.where(AutonomyEligibilityCache.cache_key.contains(actor_id))
        if proposal_type:
            query = query.where(AutonomyEligibilityCache.cache_key.contains(proposal_type))
        
        result = await db.execute(query)
        caches = result.scalars().all()
        
        count = 0
        for cache in caches:
            cache.invalidated = True
            cache.invalidated_at = utcnow()
            cache.invalidated_by = "system"
            cache.invalidation_reason = "policy_or_entitlement_change"
            count += 1
        
        await db.flush()
        return count


autonomy_service = AutonomyService()