"""Canonical Communication, Collaboration & Community Fabric Service — Gate 22.

Derives the unified communication/collaboration fabric by composing Gates 6-21
into a single coherent communication/collaboration operating fabric.

This is a DERIVED PROJECTION layer — it does NOT create a second communication/
social/community graph/brain/system. All communication/collaboration intelligence
is composed from existing canonical primitives.

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
- Gate 21: Canonical People, Talent & Workforce Operating Fabric

Epistemic boundaries preserved:
Message ≠ Claim ≠ Evidence ≠ Decision ≠ Authorization ≠ Execution ≠ Outcome
Communication ≠ Decision ≠ Authorization ≠ Commitment ≠ Execution
Group ≠ Organizational Hierarchy
Community ≠ Social Network
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
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
from app.models.canonical_communication_collaboration import (
    CanonicalGroup,
    CanonicalGroupVersion,
    CanonicalGroupMembership,
    CanonicalCommunity,
    CanonicalCommunityMembership,
    CanonicalCommunityPost,
    CanonicalCommunityComment,
    CanonicalAnnouncement,
    CanonicalAnnouncementReceipt,
    CanonicalGroupMessage,
    CanonicalGroupMessageReaction,
    CanonicalGroupRelation,
    CANONICAL_GROUP_KINDS,
    CANONICAL_GROUP_LIFECYCLE_STATES,
    CANONICAL_GROUP_MEMBERSHIP_ROLES,
    CANONICAL_GROUP_SCOPES,
    CANONICAL_GROUP_MEMBERSHIP_ROLES,
)
from app.models.canonical_business_process import (
    CanonicalBusinessProcess,
    ProcessExecution,
    ProcessStep,
    ProcessApproval,
)
from app.models.canonical_procurement_vendor import CanonicalVendor
from app.models.canonical_resource_asset import CanonicalResource
from app.models.company_actions import CompanyAction
from app.models.employee import Employee
from app.models.execution_strategy import CompanyCommitment, CompanyObjective, CompanyInitiative
from app.models.finance import Budget
from app.models.knowledge import KnowledgeSource
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
    OutcomeAssessment,
)
from app.models.organization import TimestampMixin, gen_uuid
from app.models.project import Project
from app.models.resource_allocation_intelligence import AllocationDemand
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.intelligence.company_brain import company_brain
from app.models.knowledge import KnowledgeSource

logger = logging.getLogger("vcos.intelligence.canonical_communication_collaboration")


# =============================================================================
# UTILITIES
# =============================================================================

def _compute_fingerprint(data: dict) -> str:
    """Compute deterministic fingerprint for exact-once semantics."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:160]


def _compute_group_fingerprint(
    org_id: str,
    kind: str,
    name: str,
    description: Optional[str],
    version: int,
    valid_from: datetime,
) -> str:
    """Compute fingerprint for a group."""
    return _compute_fingerprint({
        "org": org_id,
        "kind": kind,
        "name": name,
        "desc_hash": hashlib.sha256((description or "").encode()).hexdigest()[:32] if description else None,
        "version": version,
        "valid_from": valid_from.isoformat(),
    })


def _compute_community_fingerprint(
    org_id: str,
    community_type: str,
    name: str,
    description: Optional[str],
    version: int,
    valid_from: datetime,
) -> str:
    """Compute fingerprint for a community."""
    return _compute_fingerprint({
        "org": org_id,
        "type": community_type,
        "name": name,
        "desc_hash": hashlib.sha256((description or "").encode()).hexdigest()[:32] if description else None,
        "version": version,
        "valid_from": valid_from.isoformat(),
    })


def _compute_announcement_fingerprint(
    org_id: str,
    announcement_type: str,
    title: str,
    body: Optional[str],
    version: int,
    valid_from: datetime,
) -> str:
    """Compute fingerprint for an announcement."""
    return _compute_fingerprint({
        "org": org_id,
        "type": announcement_type,
        "title": title,
        "body_hash": hashlib.sha256((body or "").encode()).hexdigest()[:32] if body else None,
        "version": version,
        "valid_from": valid_from.isoformat(),
    })


# =============================================================================
# SERVICE CLASS
# =============================================================================

class CanonicalCommunicationCollaborationService:
    """Canonical Communication, Collaboration & Community Fabric Service — Gate 22."""

    # -------------------------------------------------------------------------
    # 1. CANONICAL GROUP CRUD WITH EXACT-ONCE SEMANTICS
    # -------------------------------------------------------------------------

    async def create_group(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        kind: str,
        name: str,
        description: Optional[str] = None,
        summary: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        scope: str = "company",
        scope_id: Optional[str] = None,
        lifecycle_state: str = "forming",
        owner_id: Optional[str] = None,
        owner_type: Optional[str] = None,
        fingerprint: Optional[str] = None,
        content: Optional[str] = None,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
        supersedes_id: Optional[str] = None,
    ) -> CanonicalGroup:
        """Create a canonical group with exact-once semantics."""

        if kind not in CANONICAL_GROUP_KINDS:
            raise ValueError(f"Invalid kind: {kind}. Must be one of {CANONICAL_GROUP_KINDS}")
        if scope not in CANONICAL_GROUP_SCOPES:
            raise ValueError(f"Invalid scope: {scope}. Must be one of {CANONICAL_GROUP_SCOPES}")
        if lifecycle_state not in CANONICAL_GROUP_LIFECYCLE_STATES:
            raise ValueError(f"Invalid lifecycle_state: {lifecycle_state}")

        now = utcnow()

        # Determine version - if superseding, inherit version from superseded group
        version = 1
        if supersedes_id:
            superseded = await db.get(CanonicalGroup, supersedes_id)
            if superseded:
                version = superseded.version_counter + 1

        # Compute fingerprint for exact-once
        fp = fingerprint or _compute_group_fingerprint(
            caller.organization_id, kind, name, description, version, now
        )

        # Check for exact duplicate
        existing = await db.execute(
            select(CanonicalGroup).where(
                CanonicalGroup.organization_id == caller.organization_id,
                CanonicalGroup.fingerprint == fp,
            )
        )
        if existing.scalar_one_or_none():
            raise IntegrityError("Duplicate group fingerprint", None, None)

        # Create group
        group = CanonicalGroup(
            organization_id=caller.organization_id,
            name=name,
            slug=f"{kind}-{gen_uuid()[:8]}",
            description=description,
            summary=summary,
            kind=kind,
            category=category,
            tags_json=tags or [],
            scope=scope,
            scope_id=scope_id,
            lifecycle_state=lifecycle_state,
            owner_id=owner_id,
            owner_type=owner_type,
            author_id=caller.employee_id or caller.user_id,
            fingerprint=fp,
            content_hash=hashlib.sha256((description or "").encode()).hexdigest()[:64] if description else None,
            content=content,
            valid_from=valid_from,
            valid_to=valid_to,
            supersedes_id=supersedes_id,
            version_counter=version,
        )

        db.add(group)
        await db.flush()

        # Create version record for initial creation
        version_record = CanonicalGroupVersion(
            organization_id=caller.organization_id,
            group_id=group.id,
            version=group.version_counter,
            name=group.name,
            description=group.description,
            summary=group.summary,
            tags_json=group.tags_json,
            category=group.category,
            kind=group.kind,
            lifecycle_state=group.lifecycle_state,
            valid_from=group.valid_from,
            valid_to=group.valid_to,
            editor_id=caller.employee_id or caller.user_id,
            change_note=f"Created version {group.version_counter}",
            change_type="create",
            content_hash=group.content_hash,
            provenance_json=group.provenance_json,
        )
        db.add(version_record)

        # Add creator as owner member
        if caller.employee_id:
            membership = CanonicalGroupMembership(
                organization_id=caller.organization_id,
                group_id=group.id,
                employee_id=caller.employee_id,
                role="owner",
                valid_from=utcnow(),
                can_post=True,
                can_moderate=True,
                can_invite=True,
                can_manage_members=True,
                can_manage_settings=True,
                notifications_enabled=True,
                fingerprint=_compute_fingerprint({
                    "org": caller.organization_id,
                    "group": group.id,
                    "emp": caller.employee_id,
                    "role": "owner",
                    "time": now.isoformat(),
                }),
            )
            db.add(membership)

        await db.flush()

        return group

    async def update_group(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        summary: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        lifecycle_state: Optional[str] = None,
        version_counter: Optional[int] = None,
    ) -> Optional[CanonicalGroup]:
        """Update group with optimistic concurrency and versioning."""

        group = await db.get(CanonicalGroup, group_id)
        if not group or group.organization_id != caller.organization_id:
            return None

        # Optimistic concurrency check
        if version_counter is not None and group.version_counter != version_counter:
            raise IntegrityError("Concurrent modification detected", None, None)

        # Track changes
        changes = {}
        if name is not None and name != group.name:
            changes["name"] = {"old": group.name, "new": name}
            group.name = name
        if description is not None and description != group.description:
            changes["description"] = True
            group.description = description
            group.content_hash = hashlib.sha256(description.encode()).hexdigest()[:64]
        if summary is not None and summary != group.summary:
            changes["summary"] = {"old": group.summary, "new": summary}
            group.summary = summary
        if category is not None and category != group.category:
            changes["category"] = {"old": group.category, "new": category}
            group.category = category
        if tags is not None and tags != (group.tags_json or []):
            changes["tags"] = {"old": group.tags_json, "new": tags}
            group.tags_json = tags
        if lifecycle_state is not None and lifecycle_state != group.lifecycle_state:
            if lifecycle_state not in CANONICAL_GROUP_LIFECYCLE_STATES:
                raise ValueError(f"Invalid lifecycle_state: {lifecycle_state}")
            changes["lifecycle_state"] = {"old": group.lifecycle_state, "new": lifecycle_state}
            group.lifecycle_state = lifecycle_state

        if not changes:
            return group

        # Increment version for content changes
        content_changed = any(k in changes for k in ("description", "name", "summary"))
        if content_changed:
            group.version_counter += 1
            group.valid_from = utcnow()

        group.updated_at = utcnow()

        # Create version record
        version_record = CanonicalGroupVersion(
            organization_id=caller.organization_id,
            group_id=group.id,
            version=group.version_counter,
            name=group.name,
            description=group.description,
            summary=group.summary,
            tags_json=group.tags_json,
            category=group.category,
            kind=group.kind,
            lifecycle_state=group.lifecycle_state,
            valid_from=group.valid_from,
            valid_to=group.valid_to,
            editor_id=caller.employee_id or caller.user_id,
            change_note=f"Updated: {', '.join(changes.keys())}",
            change_type="update",
            content_hash=group.content_hash,
            provenance_json=group.provenance_json,
        )
        db.add(version_record)

        return group

    async def supersede_group(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        new_group_data: dict,
    ) -> CanonicalGroup:
        """Create a new version that supersedes the current group."""
        group = await db.get(CanonicalGroup, group_id)
        if not group or group.organization_id != caller.organization_id:
            raise ValueError("Group not found")

        new_group = await self.create_group(
            db,
            caller=caller,
            supersedes_id=group_id,
            **new_group_data,
        )
        
        # Update the old group to point to the new superseding group
        group.superseded_by_id = new_group.id
        group.lifecycle_state = "superseded"
        group.valid_to = utcnow()
        
        # Create version record for the superseded group
        version_record = CanonicalGroupVersion(
            organization_id=caller.organization_id,
            group_id=group.id,
            version=group.version_counter + 1,
            name=group.name,
            description=group.description,
            summary=group.summary,
            tags_json=group.tags_json,
            category=group.category,
            kind=group.kind,
            lifecycle_state="superseded",
            valid_from=group.valid_from,
            valid_to=group.valid_to,
            editor_id=caller.employee_id or caller.user_id,
            change_note=f"Superseded by group {new_group.id}",
            change_type="supersede",
            content_hash=group.content_hash,
            provenance_json=group.provenance_json,
        )
        db.add(version_record)
        
        await db.flush()
        
        return new_group

    async def get_group(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
    ) -> Optional[CanonicalGroup]:
        """Get group by ID with tenant isolation."""
        result = await db.execute(
            select(CanonicalGroup).where(
                CanonicalGroup.id == group_id,
                CanonicalGroup.organization_id == caller.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_groups(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        kind: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        valid_at: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalGroup]:
        """List groups with filters and point-in-time validity."""
        query = select(CanonicalGroup).where(
            CanonicalGroup.organization_id == caller.organization_id,
        )

        if kind:
            query = query.where(CanonicalGroup.kind == kind)
        if scope:
            query = query.where(CanonicalGroup.scope == scope)
        if scope_id:
            query = query.where(CanonicalGroup.scope_id == scope_id)
        if lifecycle_state:
            query = query.where(CanonicalGroup.lifecycle_state == lifecycle_state)

        # Point-in-time validity filter
        if valid_at:
            query = query.where(
                and_(
                    CanonicalGroup.valid_from <= valid_at,
                    or_(
                        CanonicalGroup.valid_to.is_(None),
                        CanonicalGroup.valid_to > valid_at,
                    ),
                )
            )
        else:
            # Default: currently valid
            now = utcnow()
            query = query.where(
                and_(
                    CanonicalGroup.valid_from <= now,
                    or_(
                        CanonicalGroup.valid_to.is_(None),
                        CanonicalGroup.valid_to > now,
                    ),
                )
            )

        query = query.order_by(CanonicalGroup.updated_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_group_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
    ) -> List[CanonicalGroupVersion]:
        """Get full version history of a group."""
        result = await db.execute(
            select(CanonicalGroupVersion).where(
                CanonicalGroupVersion.organization_id == caller.organization_id,
                CanonicalGroupVersion.group_id == group_id,
            ).order_by(CanonicalGroupVersion.version.asc())
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 2. GROUP MEMBERSHIP MANAGEMENT
    # -------------------------------------------------------------------------

    async def add_group_member(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        employee_id: str,
        role: str = "participant",
    ) -> CanonicalGroupMembership:
        """Add a member to a canonical group."""

        if role not in CANONICAL_GROUP_MEMBERSHIP_ROLES:
            raise ValueError(f"Invalid role: {role}")

        group = await self.get_group(db, caller=caller, group_id=group_id)
        if not group:
            raise ValueError("Group not found")

        # Check exact-once
        fp = _compute_fingerprint({
            "org": caller.organization_id,
            "group": group_id,
            "emp": employee_id,
            "role": role,
        })

        existing = await db.execute(
            select(CanonicalGroupMembership).where(
                CanonicalGroupMembership.organization_id == caller.organization_id,
                CanonicalGroupMembership.group_id == group_id,
                CanonicalGroupMembership.employee_id == employee_id,
                CanonicalGroupMembership.role == role,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one()

        membership = CanonicalGroupMembership(
            organization_id=caller.organization_id,
            group_id=group_id,
            employee_id=employee_id,
            role=role,
            valid_from=utcnow(),
            can_post=role in ("owner", "moderator", "lead", "facilitator", "participant"),
            can_moderate=role in ("owner", "moderator", "lead", "facilitator"),
            can_invite=role in ("owner", "moderator", "lead"),
            can_manage_members=role in ("owner", "moderator", "lead"),
            can_manage_settings=role in ("owner", "moderator"),
            fingerprint=_compute_fingerprint({
                "org": caller.organization_id,
                "group": group_id,
                "emp": employee_id,
                "role": role,
            }),
        )
        db.add(membership)
        await db.flush()
        return membership

    async def remove_group_member(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        employee_id: str,
    ) -> None:
        """Remove a member from a group (soft delete with valid_to)."""

        result = await db.execute(
            select(CanonicalGroupMembership).where(
                CanonicalGroupMembership.organization_id == caller.organization_id,
                CanonicalGroupMembership.group_id == group_id,
                CanonicalGroupMembership.employee_id == employee_id,
                CanonicalGroupMembership.valid_to.is_(None),
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            return

        membership.valid_to = utcnow()
        membership.left_at = utcnow()
        await db.flush()

    async def get_group_members(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        role: Optional[str] = None,
    ) -> List[CanonicalGroupMembership]:
        """Get all current members of a group."""
        query = select(CanonicalGroupMembership).where(
            CanonicalGroupMembership.organization_id == caller.organization_id,
            CanonicalGroupMembership.group_id == group_id,
            CanonicalGroupMembership.valid_to.is_(None),
        )
        if role:
            query = query.where(CanonicalGroupMembership.role == role)
        result = await db.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 3. GROUP RELATIONS — Connect groups to canonical reality
    # -------------------------------------------------------------------------

    async def create_group_relation(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        target_type: str,
        target_id: str,
        relation_type: str,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> CanonicalGroupRelation:
        """Create a typed relation between a group and canonical reality."""

        fp = _compute_fingerprint({
            "org": caller.organization_id,
            "source_type": "group",
            "source_id": group_id,
            "target_type": target_type,
            "target_id": target_id,
            "relation_type": relation_type,
        })

        existing = await db.execute(
            select(CanonicalGroupRelation).where(
                CanonicalGroupRelation.organization_id == caller.organization_id,
                CanonicalGroupRelation.source_type == "group",
                CanonicalGroupRelation.source_id == group_id,
                CanonicalGroupRelation.target_type == target_type,
                CanonicalGroupRelation.target_id == target_id,
                CanonicalGroupRelation.relation_type == relation_type,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one()

        relation = CanonicalGroupRelation(
            organization_id=caller.organization_id,
            group_id=group_id,
            source_type="group",
            source_id=group_id,
            target_type=target_type,
            target_id=target_id,
            relation_type=relation_type,
            created_by=caller.employee_id or caller.user_id,
            confidence=confidence,
            metadata_json=metadata or {},
            fingerprint=fp,
        )
        db.add(relation)
        await db.flush()
        return relation

    async def get_relations_for_group(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        group_id: str,
        target_type: Optional[str] = None,
    ) -> List[CanonicalGroupRelation]:
        """Get all relations from a group to canonical reality."""
        query = select(CanonicalGroupRelation).where(
            CanonicalGroupRelation.organization_id == caller.organization_id,
            CanonicalGroupRelation.group_id == group_id,
        )
        if target_type:
            query = query.where(CanonicalGroupRelation.target_type == target_type)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_relations_to_target(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        target_type: str,
        target_id: str,
        relation_type: Optional[str] = None,
    ) -> List[CanonicalGroupRelation]:
        """Get all group relations pointing to a canonical entity."""
        query = select(CanonicalGroupRelation).where(
            CanonicalGroupRelation.organization_id == caller.organization_id,
            CanonicalGroupRelation.target_type == target_type,
            CanonicalGroupRelation.target_id == target_id,
        )
        if relation_type:
            query = query.where(CanonicalGroupRelation.relation_type == relation_type)
        result = await db.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 4. CANONICAL COMMUNITY CRUD
    # -------------------------------------------------------------------------

    async def create_community(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        name: str,
        description: Optional[str] = None,
        summary: Optional[str] = None,
        community_type: str = "practice",
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        scope: str = "company",
        scope_id: Optional[str] = None,
        visibility: str = "public",
        owner_id: Optional[str] = None,
        owner_type: Optional[str] = None,
        moderator_ids: Optional[List[str]] = None,
        fingerprint: Optional[str] = None,
    ) -> CanonicalCommunity:
        """Create a canonical community with exact-once semantics."""

        now = utcnow()

        # Compute fingerprint for exact-once
        fp = fingerprint or _compute_community_fingerprint(
            caller.organization_id, community_type, name, description, 1, now
        )

        # Check for exact duplicate
        existing = await db.execute(
            select(CanonicalCommunity).where(
                CanonicalCommunity.organization_id == caller.organization_id,
                CanonicalCommunity.fingerprint == fp,
            )
        )
        if existing.scalar_one_or_none():
            raise IntegrityError("Duplicate community fingerprint", None, None)

        # Create community
        community = CanonicalCommunity(
            organization_id=caller.organization_id,
            name=name,
            slug=f"{community_type}-{gen_uuid()[:8]}",
            description=description,
            summary=summary,
            community_type=community_type,
            category=category,
            tags_json=tags or [],
            scope=scope,
            scope_id=scope_id,
            visibility=visibility,
            owner_id=owner_id,
            owner_type=owner_type,
            author_id=caller.employee_id or caller.user_id,
            moderator_ids_json=moderator_ids or [],
            fingerprint=fp,
            content_hash=hashlib.sha256((description or "").encode()).hexdigest()[:64] if description else None,
        )

        db.add(community)
        await db.flush()

        # Add creator as owner member
        if caller.employee_id:
            membership = CanonicalCommunityMembership(
                organization_id=caller.organization_id,
                community_id=community.id,
                employee_id=caller.employee_id,
                role="owner",
                valid_from=utcnow(),
                can_post=True,
                can_moderate=True,
                can_invite=True,
                fingerprint=_compute_fingerprint({
                    "org": caller.organization_id,
                    "community": community.id,
                    "emp": caller.employee_id,
                    "role": "owner",
                }),
            )
            db.add(membership)

        return community

    async def get_community(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        community_id: str,
    ) -> Optional[CanonicalCommunity]:
        """Get community by ID with tenant isolation."""
        result = await db.execute(
            select(CanonicalCommunity).where(
                CanonicalCommunity.id == community_id,
                CanonicalCommunity.organization_id == caller.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_communities(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        community_type: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalCommunity]:
        """List communities with filters."""
        query = select(CanonicalCommunity).where(
            CanonicalCommunity.organization_id == caller.organization_id,
        )

        if community_type:
            query = query.where(CanonicalCommunity.community_type == community_type)
        if scope:
            query = query.where(CanonicalCommunity.scope == scope)
        if scope_id:
            query = query.where(CanonicalCommunity.scope_id == scope_id)
        if lifecycle_state:
            query = query.where(CanonicalCommunity.lifecycle_state == lifecycle_state)

        query = query.order_by(CanonicalCommunity.updated_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 5. CANONICAL ANNOUNCEMENT CRUD
    # -------------------------------------------------------------------------

    async def create_announcement(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        title: str,
        body: Optional[str] = None,
        summary: Optional[str] = None,
        announcement_type: str = "general",
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        scope: str = "company",
        scope_id: Optional[str] = None,
        lifecycle_state: str = "draft",
        priority: str = "normal",
        acknowledge_required: bool = False,
        starts_at: Optional[datetime] = None,
        ends_at: Optional[datetime] = None,
        author_id: Optional[str] = None,
        department_id: Optional[str] = None,
        team_id: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> CanonicalAnnouncement:
        """Create a canonical announcement with exact-once semantics."""

        now = utcnow()

        # Compute fingerprint for exact-once
        fp = fingerprint or _compute_announcement_fingerprint(
            caller.organization_id, announcement_type, title, body, 1, now
        )

        # Check for exact duplicate
        existing = await db.execute(
            select(CanonicalAnnouncement).where(
                CanonicalAnnouncement.organization_id == caller.organization_id,
                CanonicalAnnouncement.fingerprint == fp,
            )
        )
        if existing.scalar_one_or_none():
            raise IntegrityError("Duplicate announcement fingerprint", None, None)

        # Create announcement
        announcement = CanonicalAnnouncement(
            organization_id=caller.organization_id,
            title=title,
            slug=f"ann-{gen_uuid()[:8]}",
            body=body,
            summary=summary,
            announcement_type=announcement_type,
            category=category,
            tags_json=tags or [],
            scope=scope,
            scope_id=scope_id,
            lifecycle_state=lifecycle_state,
            priority=priority,
            acknowledge_required=acknowledge_required,
            starts_at=starts_at,
            ends_at=ends_at,
            author_id=author_id or caller.employee_id or caller.user_id,
            department_id=department_id,
            team_id=team_id,
            fingerprint=fp,
            content_hash=hashlib.sha256((body or "").encode()).hexdigest()[:64] if body else None,
        )

        db.add(announcement)
        await db.flush()
        return announcement

    async def get_announcement(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        announcement_id: str,
    ) -> Optional[CanonicalAnnouncement]:
        """Get announcement by ID with tenant isolation."""
        result = await db.execute(
            select(CanonicalAnnouncement).where(
                CanonicalAnnouncement.id == announcement_id,
                CanonicalAnnouncement.organization_id == caller.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_announcements(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        announcement_type: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalAnnouncement]:
        """List announcements with filters."""
        query = select(CanonicalAnnouncement).where(
            CanonicalAnnouncement.organization_id == caller.organization_id,
        )

        if announcement_type:
            query = query.where(CanonicalAnnouncement.announcement_type == announcement_type)
        if scope:
            query = query.where(CanonicalAnnouncement.scope == scope)
        if scope_id:
            query = query.where(CanonicalAnnouncement.scope_id == scope_id)
        if lifecycle_state:
            query = query.where(CanonicalAnnouncement.lifecycle_state == lifecycle_state)

        query = query.order_by(CanonicalAnnouncement.updated_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 6. OPERATIONAL COMMUNICATION CONTEXT
    # -------------------------------------------------------------------------

    async def derive_operational_communication_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        context_type: str,  # group|community|announcement|thread|message|meeting
        context_id: str,
        question: Optional[str] = None,
        at_time: Optional[datetime] = None,
    ) -> dict:
        """
        Derive the operational communication context for a specific context.

        This is the core capability: given a context (e.g., a group, community,
        announcement), return the relevant communication context that applies.

        Returns a structured context with epistemic transparency.
        """

        at_time = at_time or utcnow()
        context = {
            "queried_at": utcnow().isoformat(),
            "context_type": context_type,
            "context_id": context_id,
            "at_time": at_time.isoformat(),
            "epistemic_breakdown": {
                "messages": [],           # What messages say
                "claims": [],             # Claims extracted from messages
                "evidence": [],           # Supporting evidence
                "decisions": [],          # Linked decisions
                "commitments": [],        # Linked commitments
                "actions": [],            # Linked actions
                "decisions_pending": [],  # Pending decisions
                "conflicts": [],          # Known conflicts
                "institutional_lessons": [], # What the company has learned
            },
            "groups": [],
            "communities": [],
            "announcements": [],
            "messages": [],
            "relations": [],
            "expertise": [],
            "provenance": [],
        }

        # Implementation would derive context based on context_type
        # This is a placeholder for the full implementation

        return context


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

canonical_communication_collaboration_service = CanonicalCommunicationCollaborationService()