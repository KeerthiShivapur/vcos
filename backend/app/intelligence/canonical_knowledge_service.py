"""Canonical Knowledge, Documents & Institutional Context Fabric Service — Gate 20.

Derives operational knowledge context by composing Gates 6-19 into a single
coherent knowledge fabric. This is a DERIVED PROJECTION layer — it does NOT
create a second knowledge graph/brain/RAG system.

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

Epistemic boundaries preserved:
Document statement ≠ Company fact ≠ Observed behavior ≠ Verified outcome
Policy ≠ Decision ≠ Authorization ≠ Execution ≠ Outcome
Knowledge ≠ Prediction ≠ Recommendation ≠ Decision ≠ Authorization
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import sqlalchemy
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.intelligence.canonical_business_process_service import canonical_business_process_service
from app.intelligence.canonical_economic_intelligence_service import canonical_economic_intelligence_service
from app.intelligence.canonical_procurement_vendor_service import canonical_procurement_vendor_service
from app.intelligence.canonical_resource_asset_service import canonical_resource_asset_service
from app.intelligence.company_brain import company_brain
from app.intelligence.counterfactual_intelligence_service import counterfactual_intelligence_service
from app.intelligence.canonical_digital_twin_service import canonical_digital_twin_service
from app.intelligence.financial_resource_procurement_service import financial_resource_procurement_service
from app.intelligence.learning_engine import learning_engine
from app.intelligence.organizational_responsibility_engine import organizational_responsibility_engine
from app.intelligence.predictive_intelligence_service import predictive_intelligence_service
from app.intelligence.verification_orchestration_engine import verification_orchestration_engine
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
from app.models.company_memory import CompanyMemory
from app.models.decision_history import DecisionHistory
from app.models.employee import Employee
from app.models.execution_strategy import CompanyCommitment, CompanyObjective, CompanyInitiative
from app.models.finance import Budget
from app.models.knowledge import (
    Document,
    Policy,
    SOP,
    Template,
    Decision,
    WikiPage,
    KnowledgeClaim as LegacyKnowledgeClaim,
    KnowledgeEvidence as LegacyKnowledgeEvidence,
    KnowledgeSource,
)
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
    OutcomeAssessment,
)
from app.models.organization import TimestampMixin, gen_uuid
from app.models.project import Project
from app.models.resource_allocation_intelligence import AllocationDemand

logger = logging.getLogger("vcos.intelligence.canonical_knowledge")


# =============================================================================
# UTILITIES
# =============================================================================

def _compute_fingerprint(data: dict) -> str:
    """Compute deterministic fingerprint for exact-once semantics."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:64]


def _compute_artifact_fingerprint(
    org_id: str,
    kind: str,
    title: str,
    content: Optional[str],
    version: int,
    valid_from: datetime,
) -> str:
    """Compute fingerprint for a knowledge artifact."""
    return _compute_fingerprint({
        "org": org_id,
        "kind": kind,
        "title": title,
        "content_hash": hashlib.sha256((content or "").encode()).hexdigest()[:32] if content else None,
        "version": version,
        "valid_from": valid_from.isoformat(),
    })


# =============================================================================
# SERVICE CLASS
# =============================================================================

class CanonicalKnowledgeService:
    """Canonical Knowledge Service — Gate 20."""

    # -------------------------------------------------------------------------
    # 1. KNOWLEDGE ARTIFACT CRUD WITH EXACT-ONCE SEMANTICS
    # -------------------------------------------------------------------------

    async def create_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        kind: str,
        title: str,
        content: Optional[str] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        scope: str = "organization",
        scope_id: Optional[str] = None,
        lifecycle_state: str = "draft",
        owner_id: Optional[str] = None,
        owner_type: Optional[str] = None,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
        review_date: Optional[date] = None,
        review_cadence_days: Optional[int] = None,
        source_type: str = "internal",
        source_id: Optional[str] = None,
        external_ref: Optional[str] = None,
        provenance: Optional[dict] = None,
        supersedes_id: Optional[str] = None,
        primary_topic_id: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> CanonicalKnowledgeArtifact:
        """Create a knowledge artifact with exact-once semantics."""

        if kind not in KNOWLEDGE_ARTIFACT_KINDS:
            raise ValueError(f"Invalid kind: {kind}. Must be one of {KNOWLEDGE_ARTIFACT_KINDS}")
        if scope not in ARTIFACT_SCOPES:
            raise ValueError(f"Invalid scope: {scope}. Must be one of {ARTIFACT_SCOPES}")
        if lifecycle_state not in ARTIFACT_LIFECYCLE_STATES:
            raise ValueError(f"Invalid lifecycle_state: {lifecycle_state}")

        now = utcnow()
        valid_from = valid_from or now

        # Determine version
        version = 1
        if supersedes_id:
            superseded = await db.get(CanonicalKnowledgeArtifact, supersedes_id)
            if superseded:
                version = superseded.version + 1

        # Compute fingerprint for exact-once
        fp = fingerprint or _compute_artifact_fingerprint(
            caller.organization_id, kind, title, content, version, valid_from
        )

# Check for exact duplicate
        existing = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.fingerprint == fp,
            )
        )
        if existing.scalar_one_or_none():
            raise IntegrityError("Duplicate artifact fingerprint", None, None)

        # Load superseded artifact BEFORE creating new one (to update it in same transaction)
        superseded = None
        if supersedes_id:
            superseded = await db.get(CanonicalKnowledgeArtifact, supersedes_id)

        # Create artifact
        artifact = CanonicalKnowledgeArtifact(
            organization_id=caller.organization_id,
            title=title,
            slug=f"{kind}-{gen_uuid()[:8]}",
            content=content,
            summary=summary,
            description=description,
            kind=kind,
            category=category,
            tags_json=tags or [],
            scope=scope,
            scope_id=scope_id,
            lifecycle_state=lifecycle_state,
            version=version,
            valid_from=valid_from,
            valid_to=valid_to,
            owner_id=owner_id,
            owner_type=owner_type,
            author_id=caller.employee_id or caller.user_id,
            review_date=review_date,
            review_cadence_days=review_cadence_days,
            source_type=source_type,
            source_id=source_id,
            external_ref=external_ref,
            provenance_json=provenance or {},
            supersedes_id=supersedes_id,
            primary_topic_id=primary_topic_id,
            fingerprint=fp,
            content_hash=hashlib.sha256((content or "").encode()).hexdigest()[:64] if content else None,
        )

        db.add(artifact)
        await db.flush()  # Flush to get artifact.id

        # Update superseded artifact in same transaction
        if superseded:
            superseded.superseded_by_id = artifact.id
            superseded.lifecycle_state = "superseded"
            superseded.valid_to = valid_from

        # Create version record (now artifact.id is available)
        version_record = KnowledgeArtifactVersion(
            organization_id=caller.organization_id,
            artifact_id=artifact.id,
            version=version,
            title=title,
            content=content,
            summary=summary,
            description=description,
            tags_json=tags or [],
            category=category,
            lifecycle_state=lifecycle_state,
            valid_from=valid_from,
            valid_to=valid_to,
            editor_id=caller.employee_id or caller.user_id,
            change_note=f"Created version {version}",
            change_type="create",
            content_hash=artifact.content_hash,
            provenance_json=provenance or {},
        )
        db.add(version_record)

        await db.flush()

        return artifact

    async def update_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        lifecycle_state: Optional[str] = None,
        valid_to: Optional[datetime] = None,
        review_date: Optional[date] = None,
        change_note: Optional[str] = None,
        version_counter: Optional[int] = None,
    ) -> Optional[CanonicalKnowledgeArtifact]:
        """Update artifact with optimistic concurrency and versioning."""

        artifact = await db.get(CanonicalKnowledgeArtifact, artifact_id)
        if not artifact or artifact.organization_id != caller.organization_id:
            return None

        # Optimistic concurrency check
        if version_counter is not None and artifact.version_counter != version_counter:
            raise IntegrityError("Concurrent modification detected", None, None)

        # Track changes
        changes = {}
        if title is not None and title != artifact.title:
            changes["title"] = {"old": artifact.title, "new": title}
            artifact.title = title
        if content is not None and content != artifact.content:
            changes["content"] = True
            artifact.content = content
            artifact.content_hash = hashlib.sha256(content.encode()).hexdigest()[:64]
        if summary is not None and summary != artifact.summary:
            changes["summary"] = {"old": artifact.summary, "new": summary}
            artifact.summary = summary
        if description is not None and description != artifact.description:
            changes["description"] = {"old": artifact.description, "new": description}
            artifact.description = description
        if category is not None and category != artifact.category:
            changes["category"] = {"old": artifact.category, "new": category}
            artifact.category = category
        if tags is not None and tags != (artifact.tags_json or []):
            changes["tags"] = {"old": artifact.tags_json, "new": tags}
            artifact.tags_json = tags
        if lifecycle_state is not None and lifecycle_state != artifact.lifecycle_state:
            if lifecycle_state not in ARTIFACT_LIFECYCLE_STATES:
                raise ValueError(f"Invalid lifecycle_state: {lifecycle_state}")
            changes["lifecycle_state"] = {"old": artifact.lifecycle_state, "new": lifecycle_state}
            artifact.lifecycle_state = lifecycle_state
        if valid_to is not None and valid_to != artifact.valid_to:
            changes["valid_to"] = {"old": artifact.valid_to, "new": valid_to}
            artifact.valid_to = valid_to
        if review_date is not None and review_date != artifact.review_date:
            changes["review_date"] = {"old": artifact.review_date, "new": review_date}
            artifact.review_date = review_date

        if not changes:
            return artifact

        # Increment version for content changes
        content_changed = any(k in changes for k in ("content", "title", "summary", "description"))
        if content_changed:
            artifact.version += 1
            artifact.valid_from = utcnow()

        artifact.version_counter += 1
        artifact.updated_at = utcnow()

        # Create version record
        version_record = KnowledgeArtifactVersion(
            organization_id=caller.organization_id,
            artifact_id=artifact.id,
            version=artifact.version,
            title=artifact.title,
            content=artifact.content,
            summary=artifact.summary,
            description=artifact.description,
            tags_json=artifact.tags_json,
            category=artifact.category,
            lifecycle_state=artifact.lifecycle_state,
            valid_from=artifact.valid_from,
            valid_to=artifact.valid_to,
            editor_id=caller.employee_id or caller.user_id,
            change_note=change_note or f"Updated: {', '.join(changes.keys())}",
            change_type="update",
            content_hash=artifact.content_hash,
            provenance_json=artifact.provenance_json,
        )
        db.add(version_record)

        return artifact

    async def supersede_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        new_artifact_data: dict,
    ) -> CanonicalKnowledgeArtifact:
        """Create a new version that supersedes the current artifact."""
        artifact = await db.get(CanonicalKnowledgeArtifact, artifact_id)
        if not artifact or artifact.organization_id != caller.organization_id:
            raise ValueError("Artifact not found")

        new_artifact = await self.create_artifact(
            db,
            caller=caller,
            supersedes_id=artifact_id,
            **new_artifact_data,
        )
        return new_artifact

    async def get_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
    ) -> Optional[CanonicalKnowledgeArtifact]:
        """Get artifact by ID with tenant isolation."""
        result = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.id == artifact_id,
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_artifacts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        kind: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        topic_id: Optional[str] = None,
        valid_at: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CanonicalKnowledgeArtifact]:
        """List artifacts with filters and point-in-time validity."""
        query = select(CanonicalKnowledgeArtifact).where(
            CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
        )

        if kind:
            query = query.where(CanonicalKnowledgeArtifact.kind == kind)
        if scope:
            query = query.where(CanonicalKnowledgeArtifact.scope == scope)
        if scope_id:
            query = query.where(CanonicalKnowledgeArtifact.scope_id == scope_id)
        if lifecycle_state:
            query = query.where(CanonicalKnowledgeArtifact.lifecycle_state == lifecycle_state)
        if topic_id:
            query = query.where(CanonicalKnowledgeArtifact.primary_topic_id == topic_id)

        # Point-in-time validity filter
        if valid_at:
            query = query.where(
                and_(
                    CanonicalKnowledgeArtifact.valid_from <= valid_at,
                    or_(
                        CanonicalKnowledgeArtifact.valid_to.is_(None),
                        CanonicalKnowledgeArtifact.valid_to > valid_at,
                    ),
                )
            )
        else:
            # Default: currently valid
            now = utcnow()
            query = query.where(
                and_(
                    CanonicalKnowledgeArtifact.valid_from <= now,
                    or_(
                        CanonicalKnowledgeArtifact.valid_to.is_(None),
                        CanonicalKnowledgeArtifact.valid_to > now,
                    ),
                )
            )

        query = query.order_by(CanonicalKnowledgeArtifact.updated_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_artifact_history(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
    ) -> List[KnowledgeArtifactVersion]:
        """Get full version history of an artifact."""
        result = await db.execute(
            select(KnowledgeArtifactVersion).where(
                KnowledgeArtifactVersion.organization_id == caller.organization_id,
                KnowledgeArtifactVersion.artifact_id == artifact_id,
            ).order_by(KnowledgeArtifactVersion.version.asc())
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 2. KNOWLEDGE CLAIM EXTRACTION & MANAGEMENT
    # -------------------------------------------------------------------------

    async def extract_claims_from_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        claims: List[dict],
    ) -> List[CanonicalKnowledgeClaim]:
        """Extract claims from an artifact. Claims are atomic assertions."""

        artifact = await self.get_artifact(db, caller=caller, artifact_id=artifact_id)
        if not artifact:
            raise ValueError("Artifact not found")

        created_claims = []
        for claim_data in claims:
            fp = _compute_fingerprint({
                "org": caller.organization_id,
                "artifact": artifact_id,
                "subject_type": claim_data["subject_type"],
                "subject_id": claim_data["subject_id"],
                "predicate": claim_data["predicate"],
                "object_text": claim_data["object_text"],
                "valid_from": claim_data.get("valid_from", utcnow()).isoformat(),
            })

            # Check exact-once
            existing = await db.execute(
                select(CanonicalKnowledgeClaim).where(
                    CanonicalKnowledgeClaim.organization_id == caller.organization_id,
                    CanonicalKnowledgeClaim.source_artifact_id == artifact_id,
                    CanonicalKnowledgeClaim.subject_type == claim_data["subject_type"],
                    CanonicalKnowledgeClaim.subject_id == claim_data["subject_id"],
                    CanonicalKnowledgeClaim.predicate == claim_data["predicate"],
                    CanonicalKnowledgeClaim.object_text == claim_data["object_text"],
                    CanonicalKnowledgeClaim.valid_from == claim_data.get("valid_from", utcnow()),
                )
            )
            if existing.scalar_one_or_none():
                continue

            claim = CanonicalKnowledgeClaim(
                organization_id=caller.organization_id,
                subject_type=claim_data["subject_type"],
                subject_id=claim_data["subject_id"],
                predicate=claim_data["predicate"],
                object_text=claim_data["object_text"],
                object_value=claim_data.get("object_value"),
                object_unit=claim_data.get("object_unit"),
                claim_type=claim_data.get("claim_type", "rule"),
                source_artifact_id=artifact_id,
                source_location=claim_data.get("source_location"),
                authority_level=claim_data.get("authority_level", 3),
                confidence=claim_data.get("confidence", 0.8),
                valid_from=claim_data.get("valid_from", utcnow()),
                valid_to=claim_data.get("valid_to"),
                context_type=claim_data.get("context_type"),
                context_id=claim_data.get("context_id"),
                topic_id=claim_data.get("topic_id"),
                extracted_by=claim_data.get("extracted_by", "ai_extraction"),
                extraction_method=claim_data.get("extraction_method", "ai"),
                extraction_confidence=claim_data.get("extraction_confidence", 0.8),
                created_by=caller.employee_id or caller.user_id,
            )
            db.add(claim)
            created_claims.append(claim)

            # Add evidence links if provided
            for evidence in claim_data.get("evidence", []):
                evidence_row = CanonicalKnowledgeEvidence(
                    organization_id=caller.organization_id,
                    claim_id=claim.id,
                    source_type=evidence["source_type"],
                    source_id=evidence["source_id"],
                    excerpt=evidence.get("excerpt"),
                    excerpt_hash=hashlib.sha256((evidence.get("excerpt") or "").encode()).hexdigest()[:64],
                    role=evidence.get("role", "primary"),
                    confidence=evidence.get("confidence", 1.0),
                    extracted_by=evidence.get("extracted_by"),
                    extraction_method=evidence.get("extraction_method", "ai"),
                )
                db.add(evidence_row)

        await db.flush()
        return created_claims

    async def get_claims_for_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        status: Optional[str] = None,
    ) -> List[CanonicalKnowledgeClaim]:
        """Get all claims extracted from an artifact."""
        query = select(CanonicalKnowledgeClaim).where(
            CanonicalKnowledgeClaim.organization_id == caller.organization_id,
            CanonicalKnowledgeClaim.source_artifact_id == artifact_id,
        )
        if status:
            query = query.where(CanonicalKnowledgeClaim.status == status)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def verify_claim(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        claim_id: str,
        verification_result: str,  # verified|contradicted|inconclusive
        evidence: Optional[List[dict]] = None,
        verified_by: Optional[str] = None,
    ) -> Optional[CanonicalKnowledgeClaim]:
        """Verify a claim against evidence. Updates epistemic status."""
        claim = await db.get(CanonicalKnowledgeClaim, claim_id)
        if not claim or claim.organization_id != caller.organization_id:
            return None

        claim.last_verified_at = utcnow()
        claim.verification_result = verification_result
        claim.updated_at = utcnow()

        if evidence:
            for ev in evidence:
                evidence_row = CanonicalKnowledgeEvidence(
                    organization_id=caller.organization_id,
                    claim_id=claim_id,
                    source_type=ev["source_type"],
                    source_id=ev["source_id"],
                    excerpt=ev.get("excerpt"),
                    excerpt_hash=hashlib.sha256((ev.get("excerpt") or "").encode()).hexdigest()[:64],
                    role=ev.get("role", "supporting"),
                    confidence=ev.get("confidence", 1.0),
                    extracted_by=ev.get("extracted_by"),
                    extraction_method=ev.get("extraction_method", "ai"),
                )
                db.add(evidence_row)

        # Update artifact epistemic status
        artifact = await db.get(CanonicalKnowledgeArtifact, claim.source_artifact_id)
        if artifact:
            if verification_result == "verified":
                artifact.epistemic_status = "verified"
            elif verification_result == "contradicted":
                artifact.epistemic_status = "contradicted"
                artifact.has_conflicts = True
                artifact.conflict_count += 1
            elif artifact.epistemic_status == "asserted":
                artifact.epistemic_status = "partially_verified"
            artifact.verification_status = verification_result
            artifact.verified_at = utcnow()
            artifact.verified_by = verified_by or caller.employee_id or caller.user_id

        await db.flush()
        return claim

    # -------------------------------------------------------------------------
    # 3. KNOWLEDGE RELATIONS — Connect knowledge to canonical reality
    # -------------------------------------------------------------------------

    async def create_relation(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: Optional[str] = None,
        claim_id: Optional[str] = None,
        target_type: str,
        target_id: str,
        relation_type: str,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> CanonicalKnowledgeRelation:
        """Create a typed relation between knowledge and canonical reality."""

        if not artifact_id and not claim_id:
            raise ValueError("Either artifact_id or claim_id required")

        source_type = "artifact" if artifact_id else "claim"
        source_id = artifact_id or claim_id

        fp = _compute_fingerprint({
            "org": caller.organization_id,
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "relation_type": relation_type,
        })

        # Check exact-once
        existing_result = await db.execute(
            select(CanonicalKnowledgeRelation).where(
                CanonicalKnowledgeRelation.organization_id == caller.organization_id,
                CanonicalKnowledgeRelation.source_type == source_type,
                CanonicalKnowledgeRelation.source_id == source_id,
                CanonicalKnowledgeRelation.target_type == target_type,
                CanonicalKnowledgeRelation.target_id == target_id,
                CanonicalKnowledgeRelation.relation_type == relation_type,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing

        relation = CanonicalKnowledgeRelation(
            organization_id=caller.organization_id,
            artifact_id=artifact_id,
            claim_id=claim_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relation_type=relation_type,
            created_by=caller.employee_id or caller.user_id,
            confidence=confidence,
            metadata_json=metadata or {},
        )
        db.add(relation)
        await db.flush()
        return relation

    async def get_relations_for_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        target_type: Optional[str] = None,
    ) -> List[CanonicalKnowledgeRelation]:
        """Get all relations from an artifact to canonical reality."""
        query = select(CanonicalKnowledgeRelation).where(
            CanonicalKnowledgeRelation.organization_id == caller.organization_id,
            CanonicalKnowledgeRelation.artifact_id == artifact_id,
        )
        if target_type:
            query = query.where(CanonicalKnowledgeRelation.target_type == target_type)
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
    ) -> List[CanonicalKnowledgeRelation]:
        """Get all knowledge relations pointing to a canonical entity."""
        query = select(CanonicalKnowledgeRelation).where(
            CanonicalKnowledgeRelation.organization_id == caller.organization_id,
            CanonicalKnowledgeRelation.target_type == target_type,
            CanonicalKnowledgeRelation.target_id == target_id,
        )
        if relation_type:
            query = query.where(CanonicalKnowledgeRelation.relation_type == relation_type)
        result = await db.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 4. TEMPORAL KNOWLEDGE QUERIES — "What policy applied when?"
    # -------------------------------------------------------------------------

    async def get_applicable_artifacts_at_time(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        at_time: datetime,
        kind: Optional[str] = None,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        topic_id: Optional[str] = None,
    ) -> List[CanonicalKnowledgeArtifact]:
        """Get all artifacts that were valid at a specific point in time."""
        return await self.list_artifacts(
            db,
            caller=caller,
            kind=kind,
            scope=scope,
            scope_id=scope_id,
            topic_id=topic_id,
            valid_at=at_time,
        )

    async def get_claims_valid_at_time(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        at_time: datetime,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
    ) -> List[CanonicalKnowledgeClaim]:
        """Get claims that were valid at a specific point in time."""
        query = select(CanonicalKnowledgeClaim).where(
            CanonicalKnowledgeClaim.organization_id == caller.organization_id,
            CanonicalKnowledgeClaim.valid_from <= at_time,
            or_(
                CanonicalKnowledgeClaim.valid_to.is_(None),
                CanonicalKnowledgeClaim.valid_to > at_time,
            ),
        )
        if subject_type:
            query = query.where(CanonicalKnowledgeClaim.subject_type == subject_type)
        if subject_id:
            query = query.where(CanonicalKnowledgeClaim.subject_id == subject_id)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_policy_for_process_at_time(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        process_id: str,
        at_time: datetime,
    ) -> List[CanonicalKnowledgeArtifact]:
        """Get all policies that governed a process at a specific time."""
        # Get relations from policies to this process
        relations = await db.execute(
            select(CanonicalKnowledgeRelation).where(
                CanonicalKnowledgeRelation.organization_id == caller.organization_id,
                CanonicalKnowledgeRelation.target_type == "process",
                CanonicalKnowledgeRelation.target_id == process_id,
                CanonicalKnowledgeRelation.relation_type.in_(["governs", "documents", "specifies"]),
            )
        )
        artifact_ids = [r.artifact_id for r in relations.scalars().all() if r.artifact_id]

        if not artifact_ids:
            return []

        # Filter to those valid at the given time
        artifacts = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.id.in_(artifact_ids),
                CanonicalKnowledgeArtifact.kind == "policy",
                CanonicalKnowledgeArtifact.valid_from <= at_time,
                or_(
                    CanonicalKnowledgeArtifact.valid_to.is_(None),
                    CanonicalKnowledgeArtifact.valid_to > at_time,
                ),
            )
        )
        return list(artifacts.scalars().all())

    async def get_sop_for_step_at_time(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        step_id: str,
        at_time: datetime,
    ) -> List[CanonicalKnowledgeArtifact]:
        """Get SOPs that defined a process step at a specific time."""
        relations = await db.execute(
            select(CanonicalKnowledgeRelation).where(
                CanonicalKnowledgeRelation.organization_id == caller.organization_id,
                CanonicalKnowledgeRelation.target_type == "step",
                CanonicalKnowledgeRelation.target_id == step_id,
                CanonicalKnowledgeRelation.relation_type.in_(["defines_procedure_for", "provides_checklist_for"]),
            )
        )
        artifact_ids = [r.artifact_id for r in relations.scalars().all() if r.artifact_id]

        if not artifact_ids:
            return []

        artifacts = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.id.in_(artifact_ids),
                CanonicalKnowledgeArtifact.kind == "sop",
                CanonicalKnowledgeArtifact.valid_from <= at_time,
                or_(
                    CanonicalKnowledgeArtifact.valid_to.is_(None),
                    CanonicalKnowledgeArtifact.valid_to > at_time,
                ),
            )
        )
        return list(artifacts.scalars().all())

    # -------------------------------------------------------------------------
    # 5. OPERATIONAL KNOWLEDGE CONTEXT — "How do I approve this procurement?"
    # -------------------------------------------------------------------------

    async def derive_operational_knowledge_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        context_type: str,  # process|step|approval|transaction|task|project|decision|meeting
        context_id: str,
        question: Optional[str] = None,
        at_time: Optional[datetime] = None,
    ) -> dict:
        """
        Derive the operational knowledge context for a specific piece of work.

        This is the core capability: given a context (e.g., a process execution
        at a specific step), return the relevant knowledge (policies, SOPs,
        thresholds, templates, decision records, lessons) that applies.

        Returns a structured context with epistemic transparency.
        """

        at_time = at_time or utcnow()
        context = {
            "queried_at": utcnow().isoformat(),
            "context_type": context_type,
            "context_id": context_id,
            "at_time": at_time.isoformat(),
            "epistemic_breakdown": {
                "document_states": [],      # What documents say
                "company_facts": [],        # What the company actually does
                "observed_behavior": [],    # What evidence shows
                "verified_outcomes": [],    # What verification confirmed
                "conflicts": [],            # Known conflicts
                "institutional_lessons": [], # What the company has learned
            },
            "artifacts": [],
            "claims": [],
            "relations": [],
            "expertise": [],
            "provenance": [],
        }

        # 1. Get artifacts directly related to this context
        relations = await self.get_relations_to_target(
            db, caller=caller, target_type=context_type, target_id=context_id
        )
        artifact_ids = list({r.artifact_id for r in relations if r.artifact_id})

        # 2. If it's a process/step, also get governing policies/SOPs
        if context_type in ("process", "step", "execution"):
            # Get process if step/execution
            process_id = context_id
            if context_type == "step":
                step = await db.get(ProcessStep, context_id)
                if step:
                    execution = await db.get(ProcessExecution, step.execution_id)
                    process_id = execution.process_id if execution else context_id
            elif context_type == "execution":
                exec_obj = await db.get(ProcessExecution, context_id)
                process_id = exec_obj.process_id if exec_obj else context_id

            # Get policies governing this process
            policy_artifacts = await self.get_policy_for_process_at_time(
                db, caller=caller, process_id=process_id, at_time=at_time
            )
            artifact_ids.extend([a.id for a in policy_artifacts])

            # Get SOPs for steps
            if context_type in ("step", "execution"):
                step_ids = []
                if context_type == "step":
                    step_ids = [context_id]
                else:
                    steps_result = await db.execute(
                        select(ProcessStep).where(ProcessStep.execution_id == process_id)
                    )
                    step_ids = [s.id for s in steps_result.scalars().all()]

                for sid in step_ids:
                    sop_artifacts = await self.get_sop_for_step_at_time(
                        db, caller=caller, step_id=sid, at_time=at_time
                    )
                    artifact_ids.extend([a.id for a in sop_artifacts])

        # 3. Get financial thresholds if applicable (Gate 15/18 integration)
        if context_type in ("approval", "transaction", "procurement"):
            claims = await self.get_claims_valid_at_time(
                db, caller=caller, at_time=at_time, subject_type="approval_threshold"
            )
            # Also get claims for financial thresholds
            threshold_claims = await self.get_claims_valid_at_time(
                db, caller=caller, at_time=at_time, subject_type="financial_threshold"
            )
            context["claims"].extend([{
                "id": c.id,
                "subject_type": c.subject_type,
                "subject_id": c.subject_id,
                "predicate": c.predicate,
                "object_text": c.object_text,
                "object_value": c.object_value,
                "object_unit": c.object_unit,
                "claim_type": c.claim_type,
                "status": c.status,
                "authority_level": c.authority_level,
                "confidence": c.confidence,
                "source_artifact_id": c.source_artifact_id,
            } for c in claims + threshold_claims])

        # 4. Get artifacts with details
        artifacts = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.id.in_(artifact_ids) if artifact_ids else sqlalchemy.false(),
            )
        )
        artifact_list = list(artifacts.scalars().all())

        for artifact in artifact_list:
            context["artifacts"].append({
                "id": artifact.id,
                "kind": artifact.kind,
                "title": artifact.title,
                "summary": artifact.summary,
                "lifecycle_state": artifact.lifecycle_state,
                "version": artifact.version,
                "valid_from": artifact.valid_from.isoformat(),
                "valid_to": artifact.valid_to.isoformat() if artifact.valid_to else None,
                "epistemic_status": artifact.epistemic_status,
                "verification_status": artifact.verification_status,
                "has_conflicts": artifact.has_conflicts,
                "owner_id": artifact.owner_id,
                "owner_type": artifact.owner_type,
            })
            context["epistemic_breakdown"]["document_states"].append({
                "artifact_id": artifact.id,
                "kind": artifact.kind,
                "title": artifact.title,
                "states": f"{artifact.kind} says: {artifact.summary or artifact.content[:200] if artifact.content else 'No content'}",
                "epistemic_status": artifact.epistemic_status,
                "version": artifact.version,
                "valid_at": at_time.isoformat(),
            })

        # 5. Get claims for these artifacts
        for artifact in artifact_list:
            claims = await self.get_claims_for_artifact(db, caller=caller, artifact_id=artifact.id)
            for claim in claims:
                claim_valid_from = claim.valid_from
                if claim_valid_from.tzinfo is None:
                    claim_valid_from = claim_valid_from.replace(tzinfo=timezone.utc)
                claim_valid_to = claim.valid_to
                if claim_valid_to and claim_valid_to.tzinfo is None:
                    claim_valid_to = claim_valid_to.replace(tzinfo=timezone.utc)
                if claim_valid_from <= at_time and (claim_valid_to is None or claim_valid_to > at_time):
                    context["claims"].append({
                        "id": claim.id,
                        "subject_type": claim.subject_type,
                        "subject_id": claim.subject_id,
                        "predicate": claim.predicate,
                        "object_text": claim.object_text,
                        "object_value": claim.object_value,
                        "object_unit": claim.object_unit,
                        "claim_type": claim.claim_type,
                        "status": claim.status,
                        "authority_level": claim.authority_level,
                        "confidence": claim.confidence,
                        "verification_result": claim.verification_result,
                    })

        # 6. Get conflicts for these artifacts/topics
        topic_ids = [a.primary_topic_id for a in artifact_list if a.primary_topic_id]
        if topic_ids:
            conflicts = await db.execute(
                select(KnowledgeConflict).where(
                    KnowledgeConflict.organization_id == caller.organization_id,
                    KnowledgeConflict.topic_id.in_(topic_ids),
                )
            )
            for conflict in conflicts.scalars().all():
                context["epistemic_breakdown"]["conflicts"].append({
                    "id": conflict.id,
                    "type": conflict.conflict_type,
                    "severity": conflict.severity,
                    "status": conflict.status,
                    "title": conflict.title,
                    "description": conflict.description,
                    "primary_artifact_id": conflict.primary_artifact_id,
                    "conflicting_artifact_ids": conflict.conflicting_artifact_ids_json,
                })

        # 7. Get institutional lessons related to this context (Gate 9)
        lessons = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.status == "active",
                or_(
                    OrganizationalLearning.source_type == context_type,
                    OrganizationalLearning.topic_id.in_(topic_ids) if topic_ids else sqlalchemy.false(),
                ),
            ).limit(10)
        )
        for lesson in lessons.scalars().all():
            context["epistemic_breakdown"]["institutional_lessons"].append({
                "id": lesson.id,
                "kind": lesson.kind,
                "title": lesson.title,
                "lesson": lesson.lesson,
                "confidence": lesson.confidence,
                "observation": lesson.observation,
                "expectation": lesson.expectation,
            })

        # 8. Get responsible people/expertise (Gate 8 integration)
        if artifact_list:
            owner_ids = []
            for a in artifact_list:
                if a.owner_id and a.owner_type == "person":
                    owner_ids.append(a.owner_id)
                elif a.author_id:
                    owner_ids.append(a.author_id)

            if owner_ids:
                employees = await db.execute(
                    select(Employee).where(
                        Employee.organization_id == caller.organization_id,
                        Employee.id.in_(owner_ids),
                    )
                )
                for emp in employees.scalars().all():
                    context["expertise"].append({
                        "employee_id": emp.id,
                        "display_name": emp.display_name,
                        "role": "owner" if emp.id in owner_ids else "author",
                        "artifact_ids": [a.id for a in artifact_list if a.owner_id == emp.id or a.author_id == emp.id],
                    })

        # 9. Add provenance
        for artifact in artifact_list:
            context["provenance"].append({
                "artifact_id": artifact.id,
                "source_type": artifact.source_type,
                "source_id": artifact.source_id,
                "external_ref": artifact.external_ref,
                "author_id": artifact.author_id,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                "ingested_at": artifact.ingested_at.isoformat() if artifact.ingested_at else None,
                "last_synced_at": artifact.last_synced_at.isoformat() if artifact.last_synced_at else None,
                "sync_status": artifact.sync_status,
            })

        # 10. Log the query for audit trail
        query_record = KnowledgeContextQuery(
            organization_id=caller.organization_id,
            employee_id=caller.employee_id or "",
            user_id=caller.user_id,
            role_at_time=caller.employee_id,
            permissions_at_time_json={},
            question=question or f"Operational context for {context_type}:{context_id}",
            question_type="operational_context",
            context_type=context_type,
            context_id=context_id,
            answer=json.dumps(context, default=str),
            answer_confidence=0.9,
            answer_type="direct",
            artifact_ids_used_json=[a.id for a in artifact_list],
            claim_ids_used_json=[c.get("id") for c in context["claims"] if c.get("id")],
            answer_epistemic_breakdown_json=context["epistemic_breakdown"],
            queried_at=utcnow(),
            response_time_ms=0,  # Would be measured in API layer
        )
        db.add(query_record)

        return context

    # -------------------------------------------------------------------------
    # 6. KNOWLEDGE CONFLICT DETECTION & PRESERVATION
    # -------------------------------------------------------------------------

    async def detect_knowledge_conflicts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
    ) -> List[KnowledgeConflict]:
        """Detect and persist knowledge conflicts. Returns newly created conflicts."""

        conflicts_created = []

        # 1. Policy vs Policy conflicts (same topic, different rules)
        policies = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.kind == "policy",
                CanonicalKnowledgeArtifact.lifecycle_state == "published",
            )
        )
        policy_list = list(policies.scalars().all())

        # Group by topic
        topic_policies: Dict[str, List[CanonicalKnowledgeArtifact]] = {}
        for p in policy_list:
            if p.primary_topic_id:
                topic_policies.setdefault(p.primary_topic_id, []).append(p)

        for topic_id, policies_in_topic in topic_policies.items():
            if len(policies_in_topic) < 2:
                continue

            # Check for conflicting claims
            for i in range(len(policies_in_topic)):
                for j in range(i + 1, len(policies_in_topic)):
                    p1, p2 = policies_in_topic[i], policies_in_topic[j]

                    # Get claims for both
                    claims1 = await self.get_claims_for_artifact(db, caller=caller, artifact_id=p1.id)
                    claims2 = await self.get_claims_for_artifact(db, caller=caller, artifact_id=p2.id)

                    for c1 in claims1:
                        for c2 in claims2:
                            if (c1.predicate == c2.predicate and
                                c1.subject_type == c2.subject_type and
                                c1.subject_id == c2.subject_id and
                                c1.object_text != c2.object_text):

                                # Check if conflict already exists
                                fp = _compute_fingerprint({
                                    "org": caller.organization_id,
                                    "type": "policy_vs_policy",
                                    "topic": topic_id,
                                    "predicate": c1.predicate,
                                    "subject": f"{c1.subject_type}:{c1.subject_id}",
                                    "values": sorted([c1.object_text, c2.object_text]),
                                })

                                existing = await db.execute(
                                    select(KnowledgeConflict).where(
                                        KnowledgeConflict.organization_id == caller.organization_id,
                                        KnowledgeConflict.fingerprint == fp,
                                    )
                                )
                                if existing.scalar_one_or_none():
                                    continue

                                conflict = KnowledgeConflict(
                                    organization_id=caller.organization_id,
                                    conflict_type="policy_vs_policy",
                                    severity="critical",
                                    status="open",
                                    primary_artifact_id=p1.id,
                                    conflicting_artifact_ids_json=[p2.id],
                                    conflicting_claim_ids_json=[c1.id, c2.id],
                                    topic_id=topic_id,
                                    title=f"Conflicting policies on {c1.predicate} for {c1.subject_type}:{c1.subject_id}",
                                    description=f"Policy '{p1.title}' states {c1.object_text} but policy '{p2.title}' states {c2.object_text}",
                                    evidence_json={
                                        "claim_1": {"artifact_id": p1.id, "claim_id": c1.id, "value": c1.object_text},
                                        "claim_2": {"artifact_id": p2.id, "claim_id": c2.id, "value": c2.object_text},
                                    },
                                    detected_at=utcnow(),
                                    detected_by="system",
                                    detection_method="derived",
                                    fingerprint=fp,
                                )
                                db.add(conflict)
                                conflicts_created.append(conflict)

                                # Mark artifacts as having conflicts
                                p1.has_conflicts = True
                                p1.conflict_count += 1
                                p2.has_conflicts = True
                                p2.conflict_count += 1

        # 2. Documented vs Observed behavior conflicts
        # Get claims about procedures/processes
        proc_claims = await db.execute(
            select(CanonicalKnowledgeClaim).where(
                CanonicalKnowledgeClaim.organization_id == caller.organization_id,
                CanonicalKnowledgeClaim.claim_type.in_(["procedure", "rule", "threshold"]),
                CanonicalKnowledgeClaim.status.in_(["supported", "authoritative"]),
            )
        )
        for claim in proc_claims.scalars().all():
            # Check if there's evidence contradicting this claim
            contradicting_evidence = await db.execute(
                select(CanonicalKnowledgeEvidence).where(
                    CanonicalKnowledgeEvidence.organization_id == caller.organization_id,
                    CanonicalKnowledgeEvidence.claim_id == claim.id,
                    CanonicalKnowledgeEvidence.role == "contradicting",
                )
            )
            if contradicting_evidence.scalar_one_or_none():
                artifact = await db.get(CanonicalKnowledgeArtifact, claim.source_artifact_id)
                if artifact and artifact.has_conflicts is False:
                    artifact.has_conflicts = True
                    artifact.conflict_count += 1

        await db.flush()
        return conflicts_created

    async def get_conflicts_for_artifact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
    ) -> List[KnowledgeConflict]:
        """Get all conflicts involving an artifact."""
        result = await db.execute(
            select(KnowledgeConflict).where(
                KnowledgeConflict.organization_id == caller.organization_id,
                or_(
                    KnowledgeConflict.primary_artifact_id == artifact_id,
                    KnowledgeConflict.conflicting_artifact_ids_json.contains([artifact_id]),
                ),
            )
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 7. EXTERNAL SOURCE INTEGRATION
    # -------------------------------------------------------------------------

    async def register_external_source(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        source_type: str,
        external_id: str,
        title: str,
        external_url: Optional[str] = None,
        external_path: Optional[str] = None,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        content_hash: Optional[str] = None,
        permissions: Optional[dict] = None,
        access_level: str = "read",
        imported_by: Optional[str] = None,
        import_method: str = "api",
    ) -> ExternalKnowledgeSource:
        """Register an external knowledge source."""

        if source_type not in EXTERNAL_SOURCES:
            raise ValueError(f"Invalid source_type: {source_type}")

        # Check exact-once
        existing = await db.execute(
            select(ExternalKnowledgeSource).where(
                ExternalKnowledgeSource.organization_id == caller.organization_id,
                ExternalKnowledgeSource.source_type == source_type,
                ExternalKnowledgeSource.external_id == external_id,
            )
        )
        existing_source = existing.scalar_one_or_none()
        if existing_source:
            # Update sync status
            existing_source.last_synced_at = utcnow()
            existing_source.sync_status = "synced"
            existing_source.last_synced_hash = content_hash
            await db.flush()
            return existing_source

        source = ExternalKnowledgeSource(
            organization_id=caller.organization_id,
            source_type=source_type,
            external_id=external_id,
            title=title,
            external_url=external_url,
            external_path=external_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
            permissions_json=permissions or {},
            access_level=access_level,
            imported_by=imported_by or caller.employee_id or caller.user_id,
            import_method=import_method,
            sync_status="synced",
            last_synced_at=utcnow(),
            last_synced_hash=content_hash,
        )
        db.add(source)
        await db.flush()
        return source

    async def create_artifact_from_external(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        source_id: str,
        artifact_data: dict,
    ) -> CanonicalKnowledgeArtifact:
        """Create a canonical artifact from an external source."""
        source = await db.get(ExternalKnowledgeSource, source_id)
        if not source or source.organization_id != caller.organization_id:
            raise ValueError("External source not found")

        # Merge provenance
        provenance = artifact_data.get("provenance", {})
        provenance.update({
            "external_source": {
                "source_type": source.source_type,
                "external_id": source.external_id,
                "external_url": source.external_url,
                "imported_at": utcnow().isoformat(),
            }
        })

        artifact = await self.create_artifact(
            db,
            caller=caller,
            source_type=source.source_type,
            source_id=source.external_id,
            external_ref=source.external_url,
            provenance=provenance,
            **artifact_data,
        )

        # Update source mapping
        if artifact.id not in (source.mapped_artifact_ids_json or []):
            source.mapped_artifact_ids_json = (source.mapped_artifact_ids_json or []) + [artifact.id]
            source.mapping_status = "mapped"

        await db.flush()
        return artifact

    async def sync_external_source(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        source_id: str,
        new_content_hash: str,
        new_title: Optional[str] = None,
        new_content: Optional[str] = None,
    ) -> Optional[CanonicalKnowledgeArtifact]:
        """Sync an external source - detect changes and create new version if needed."""
        source = await db.get(ExternalKnowledgeSource, source_id)
        if not source or source.organization_id != caller.organization_id:
            return None

        # Check if content changed
        if source.last_synced_hash == new_content_hash:
            source.last_synced_at = utcnow()
            source.sync_status = "synced"
            await db.flush()
            return None

        # Content changed - find mapped artifacts
        artifact_ids = source.mapped_artifact_ids_json or []
        if not artifact_ids:
            source.last_synced_at = utcnow()
            source.sync_status = "conflict"  # No mapping exists
            source.sync_error = "No mapped artifacts found"
            await db.flush()
            return None

        # For simplicity, assume 1:1 mapping
        artifact_id = artifact_ids[0]
        artifact = await db.get(CanonicalKnowledgeArtifact, artifact_id)
        if not artifact:
            return None

        # Create new superseding version
        new_artifact = await self.supersede_artifact(
            db,
            caller=caller,
            artifact_id=artifact_id,
            new_artifact_data={
                "kind": artifact.kind,
                "title": new_title or artifact.title,
                "content": new_content or artifact.content,
                "summary": artifact.summary,
                "description": artifact.description,
                "category": artifact.category,
                "tags": artifact.tags_json,
                "scope": artifact.scope,
                "scope_id": artifact.scope_id,
                "lifecycle_state": "published" if artifact.lifecycle_state == "published" else artifact.lifecycle_state,
                "owner_id": artifact.owner_id,
                "owner_type": artifact.owner_type,
                "review_date": artifact.review_date,
                "review_cadence_days": artifact.review_cadence_days,
            },
        )

        # Update source
        source.last_synced_at = utcnow()
        source.last_synced_hash = new_content_hash
        source.sync_status = "synced"
        source.sync_error = None

        await db.flush()
        return new_artifact

    # -------------------------------------------------------------------------
    # 8. KNOWLEDGE ↔️ PROCESS INTEGRATION (Gate 19)
    # -------------------------------------------------------------------------

    async def link_policy_to_process(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        process_id: str,
        relation_type: str = "governs",
    ) -> CanonicalKnowledgeRelation:
        """Link a policy/SOP artifact to a canonical business process."""
        return await self.create_relation(
            db, caller=caller, artifact_id=artifact_id, target_type="process",
            target_id=process_id, relation_type=relation_type
        )

    async def link_sop_to_step(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        step_id: str,
        relation_type: str = "defines_procedure_for",
    ) -> CanonicalKnowledgeRelation:
        """Link an SOP artifact to a process step."""
        return await self.create_relation(
            db, caller=caller, artifact_id=artifact_id, target_type="step",
            target_id=step_id, relation_type=relation_type
        )

    async def link_approval_rule_to_approval(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        approval_id: str,
        relation_type: str = "defines_approval_rule_for",
    ) -> CanonicalKnowledgeRelation:
        """Link a policy artifact defining approval rules to a process approval."""
        return await self.create_relation(
            db, caller=caller, artifact_id=artifact_id, target_type="approval",
            target_id=approval_id, relation_type=relation_type
        )

    # -------------------------------------------------------------------------
    # 9. KNOWLEDGE ↔️ PEOPLE/EXPERTISE INTEGRATION (Gate 8)
    # -------------------------------------------------------------------------

    async def find_experts_for_topic(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        topic_id: str,
        limit: int = 10,
    ) -> List[dict]:
        """Find people with expertise on a knowledge topic."""
        # Get artifacts for this topic
        artifacts = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.primary_topic_id == topic_id,
            )
        )
        artifact_list = list(artifacts.scalars().all())

        # Get owners/authors
        person_ids = set()
        for a in artifact_list:
            if a.owner_id and a.owner_type == "person":
                person_ids.add(a.owner_id)
            if a.author_id:
                person_ids.add(a.author_id)

        if not person_ids:
            return []

        # Get employee details
        employees = await db.execute(
            select(Employee).where(
                Employee.organization_id == caller.organization_id,
                Employee.id.in_(person_ids),
            )
        )

        experts = []
        for emp in employees.scalars().all():
            # Get their artifacts for this topic
            emp_artifacts = [a.id for a in artifact_list
                           if (a.owner_id == emp.id and a.owner_type == "person") or a.author_id == emp.id]
            experts.append({
                "employee_id": emp.id,
                "display_name": emp.display_name,
                "email": emp.email,
                "artifact_count": len(emp_artifacts),
                "artifact_ids": emp_artifacts,
            })

        return sorted(experts, key=lambda x: x["artifact_count"], reverse=True)[:limit]

    async def get_knowledge_for_responsibility(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        responsibility_id: str,
    ) -> List[CanonicalKnowledgeArtifact]:
        """Get knowledge artifacts relevant to a responsibility."""
        relations = await db.execute(
            select(CanonicalKnowledgeRelation).where(
                CanonicalKnowledgeRelation.organization_id == caller.organization_id,
                CanonicalKnowledgeRelation.target_type == "responsibility",
                CanonicalKnowledgeRelation.target_id == responsibility_id,
            )
        )
        artifact_ids = [r.artifact_id for r in relations.scalars().all() if r.artifact_id]

        if not artifact_ids:
            return []

        artifacts = await db.execute(
            select(CanonicalKnowledgeArtifact).where(
                CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                CanonicalKnowledgeArtifact.id.in_(artifact_ids),
            )
        )
        return list(artifacts.scalars().all())

    # -------------------------------------------------------------------------
    # 10. KNOWLEDGE ↔️ DECISION/MEETING/EVIDENCE INTEGRATION (Gates 6, 9)
    # -------------------------------------------------------------------------

    async def link_decision_to_knowledge(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        decision_id: str,
        artifact_ids: List[str],
        relation_type: str = "informed",
    ) -> List[CanonicalKnowledgeRelation]:
        """Link a decision to the knowledge that informed it."""
        relations = []
        for artifact_id in artifact_ids:
            relation = await self.create_relation(
                db, caller=caller, artifact_id=artifact_id, target_type="decision",
                target_id=decision_id, relation_type=relation_type
            )
            relations.append(relation)
        return relations

    async def link_meeting_to_knowledge(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        meeting_id: str,
        artifact_ids: List[str],
        relation_type: str = "discussed_in",
    ) -> List[CanonicalKnowledgeRelation]:
        """Link a meeting to knowledge artifacts discussed/decided."""
        relations = []
        for artifact_id in artifact_ids:
            relation = await self.create_relation(
                db, caller=caller, artifact_id=artifact_id, target_type="meeting",
                target_id=meeting_id, relation_type=relation_type
            )
            relations.append(relation)
        return relations

    async def get_knowledge_for_decision(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        decision_id: str,
    ) -> dict:
        """Get all knowledge context for a decision (policies, evidence, lessons)."""
        relations = await db.execute(
            select(CanonicalKnowledgeRelation).where(
                CanonicalKnowledgeRelation.organization_id == caller.organization_id,
                CanonicalKnowledgeRelation.target_type == "decision",
                CanonicalKnowledgeRelation.target_id == decision_id,
            )
        )
        relation_list = list(relations.scalars().all())

        artifact_ids = list({r.artifact_id for r in relation_list if r.artifact_id})
        claim_ids = list({r.claim_id for r in relation_list if r.claim_id})

        artifacts = []
        if artifact_ids:
            result = await db.execute(
                select(CanonicalKnowledgeArtifact).where(
                    CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                    CanonicalKnowledgeArtifact.id.in_(artifact_ids),
                )
            )
            artifacts = list(result.scalars().all())

        claims = []
        if claim_ids:
            result = await db.execute(
                select(CanonicalKnowledgeClaim).where(
                    CanonicalKnowledgeClaim.organization_id == caller.organization_id,
                    CanonicalKnowledgeClaim.id.in_(claim_ids),
                )
            )
            claims = list(result.scalars().all())

        return {
            "decision_id": decision_id,
            "artifacts": artifacts,
            "claims": claims,
            "relations": relation_list,
        }

    # -------------------------------------------------------------------------
    # 11. KNOWLEDGE ↔️ COMPANY BRAIN INTEGRATION
    # -------------------------------------------------------------------------

    async def provide_knowledge_context_to_brain(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        question: str,
        context_type: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> dict:
        """
        Provide knowledge context to Company Brain for reasoning.
        
        Returns structured knowledge with epistemic transparency.
        """
        # Use the operational knowledge context if context provided
        if context_type and context_id:
            return await self.derive_operational_knowledge_context(
                db, caller=caller, context_type=context_type, context_id=context_id,
                question=question
            )

        # Otherwise, search for relevant artifacts
        # Use Company Brain's search capabilities
        brain_result = await company_brain.answer(
            db, caller=caller, question=question
        )

        # Enhance with knowledge-specific epistemic breakdown
        return {
            "brain_answer": brain_result,
            "knowledge_context": await self._search_relevant_knowledge(
                db, caller=caller, question=question
            ),
        }

    async def _search_relevant_knowledge(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        question: str,
        limit: int = 10,
    ) -> dict:
        """Search for knowledge artifacts relevant to a question."""
        # Simple keyword-based search for now
        # In production, would use the semantic search infrastructure
        keywords = question.lower().split()

        query = select(CanonicalKnowledgeArtifact).where(
            CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
            CanonicalKnowledgeArtifact.lifecycle_state == "published",
        )

        # Add keyword filters
        for kw in keywords[:5]:  # Limit to 5 keywords
            query = query.where(
                or_(
                    CanonicalKnowledgeArtifact.title.ilike(f"%{kw}%"),
                    CanonicalKnowledgeArtifact.content.ilike(f"%{kw}%"),
                    CanonicalKnowledgeArtifact.summary.ilike(f"%{kw}%"),
                )
            )

        query = query.limit(limit)
        result = await db.execute(query)
        artifacts = list(result.scalars().all())

        return {
            "artifacts": [{
                "id": a.id,
                "kind": a.kind,
                "title": a.title,
                "summary": a.summary,
                "epistemic_status": a.epistemic_status,
                "verification_status": a.verification_status,
                "has_conflicts": a.has_conflicts,
            } for a in artifacts],
            "epistemic_note": "These are document statements. They may not reflect actual company behavior. See verification_status and conflicts.",
        }

    # -------------------------------------------------------------------------
    # 12. INSTITUTIONAL LEARNING INTEGRATION (Gate 9)
    # -------------------------------------------------------------------------

    async def create_lesson_from_outcome(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        outcome_assessment_id: str,
        lesson_text: str,
        confidence: float = 0.7,
        related_artifact_ids: Optional[List[str]] = None,
    ) -> OrganizationalLearning:
        """Create an institutional lesson from an outcome assessment."""
        assessment = await db.get(OutcomeAssessment, outcome_assessment_id)
        if not assessment or assessment.organization_id != caller.organization_id:
            raise ValueError("Outcome assessment not found")

        fp = _compute_fingerprint({
            "org": caller.organization_id,
            "kind": "outcome_learning",
            "assessment_id": outcome_assessment_id,
            "lesson": lesson_text,
        })

        existing = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.kind == "outcome_learning",
                OrganizationalLearning.fingerprint == fp,
            )
        )
        if existing.scalar_one_or_none():
            return existing.scalar_one()

        lesson = OrganizationalLearning(
            organization_id=caller.organization_id,
            kind="outcome_learning",
            fingerprint=fp,
            title=f"Lesson from {assessment.subject_type} {assessment.subject_id}",
            lesson=lesson_text,
            status="active",
            lifecycle="discovered",
            confidence=confidence,
            source_type=assessment.subject_type,
            source_id=assessment.subject_id,
            topic_name=assessment.subject_type,
            evidence_json=json.dumps({
                "assessment_id": outcome_assessment_id,
                "expected": assessment.expected_value,
                "actual": assessment.actual_value,
                "variance_pct": assessment.variance_pct,
                "factors": assessment.factors_json,
            }),
            observation=f"Expected {assessment.expected_value} {assessment.expected_units}, got {assessment.actual_value}",
            expectation=f"Expected {assessment.expected_value} {assessment.expected_units}",
            recorded_by=caller.employee_id or caller.user_id,
            observed_at=utcnow(),
        )
        db.add(lesson)

        # Link to related artifacts
        if related_artifact_ids:
            for artifact_id in related_artifact_ids:
                await self.create_relation(
                    db, caller=caller, artifact_id=artifact_id,
                    target_type="learning", target_id=lesson.id,
                    relation_type="produced_lesson"
                )

        await db.flush()
        return lesson

    async def get_lessons_for_context(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        context_type: str,
        context_id: str,
    ) -> List[OrganizationalLearning]:
        """Get institutional lessons relevant to a context."""
        result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.status == "active",
                or_(
                    OrganizationalLearning.source_type == context_type,
                    OrganizationalLearning.source_id == context_id,
                ),
            ).order_by(OrganizationalLearning.confidence.desc())
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 13. PREDICTION/COUNTERFACTUAL/DIGITAL TWIN INTEGRATION (Gates 10-12)
    # -------------------------------------------------------------------------

    async def provide_knowledge_for_prediction(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        prediction_context: str,  # e.g., "capacity_pressure", "commitment_risk"
        entity_type: str,
        entity_id: str,
    ) -> dict:
        """Provide knowledge context as input to predictive intelligence."""
        # Get relevant policies/SOPs for this entity
        relations = await self.get_relations_to_target(
            db, caller=caller, target_type=entity_type, target_id=entity_id
        )

        policy_artifacts = []
        for r in relations:
            if r.artifact_id:
                artifact = await db.get(CanonicalKnowledgeArtifact, r.artifact_id)
                if artifact and artifact.kind in ("policy", "sop", "guideline", "standard"):
                    policy_artifacts.append(artifact)

        return {
            "prediction_context": prediction_context,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "governing_policies": [{
                "id": a.id,
                "title": a.title,
                "kind": a.kind,
                "summary": a.summary,
                "epistemic_status": a.epistemic_status,
            } for a in policy_artifacts],
            "epistemic_note": "Policy documents used as contextual input. Prediction ≠ Truth.",
        }

    async def provide_knowledge_for_counterfactual(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scenario_id: str,
        changed_policy_id: Optional[str] = None,
        changed_sop_id: Optional[str] = None,
    ) -> dict:
        """Provide knowledge context for counterfactual scenario."""
        context = {
            "scenario_id": scenario_id,
            "knowledge_context": {
                "current_policies": [],
                "proposed_changes": [],
                "affected_processes": [],
                "epistemic_note": "Counterfactual scenario. Knowledge changes are hypothetical.",
            },
        }

        if changed_policy_id:
            artifact = await self.get_artifact(db, caller=caller, artifact_id=changed_policy_id)
            if artifact:
                context["knowledge_context"]["proposed_changes"].append({
                    "artifact_id": artifact.id,
                    "kind": artifact.kind,
                    "title": artifact.title,
                    "current_content": artifact.content,
                    "proposed_content": "See scenario parameters",
                })

        return context

    async def provide_knowledge_for_digital_twin(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        twin_scope: str,  # org|team|project|person
        scope_id: str,
    ) -> dict:
        """Provide knowledge context for Digital Twin projection."""
        # Get all policies/SOPs applicable to this scope
        artifacts = await self.list_artifacts(
            db, caller=caller,
            kind="policy", scope=twin_scope, scope_id=scope_id,
        )
        artifacts += await self.list_artifacts(
            db, caller=caller, kind="sop", scope=twin_scope, scope_id=scope_id,
        )

        return {
            "twin_scope": twin_scope,
            "scope_id": scope_id,
            "governing_knowledge": [{
                "id": a.id,
                "kind": a.kind,
                "title": a.title,
                "summary": a.summary,
                "version": a.version,
                "valid_from": a.valid_from.isoformat(),
                "valid_to": a.valid_to.isoformat() if a.valid_to else None,
                "epistemic_status": a.epistemic_status,
            } for a in artifacts],
            "epistemic_note": "Digital Twin projection. Knowledge represents documented state, not necessarily actual behavior.",
        }

    # -------------------------------------------------------------------------
    # 14. EXACT-ONCE SEMANTICS FOR BULK OPERATIONS
    # -------------------------------------------------------------------------

    async def bulk_import_artifacts(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifacts: List[dict],
    ) -> dict:
        """Bulk import artifacts with exact-once semantics."""

        created = 0
        skipped = 0
        errors = []

        for i, artifact_data in enumerate(artifacts):
            try:
                fp = _compute_artifact_fingerprint(
                    caller.organization_id,
                    artifact_data["kind"],
                    artifact_data["title"],
                    artifact_data.get("content"),
                    artifact_data.get("version", 1),
                    artifact_data.get("valid_from", utcnow()),
                )

                existing = await db.execute(
                    select(CanonicalKnowledgeArtifact).where(
                        CanonicalKnowledgeArtifact.organization_id == caller.organization_id,
                        CanonicalKnowledgeArtifact.fingerprint == fp,
                    )
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

                await self.create_artifact(db, caller=caller, fingerprint=fp, **artifact_data)
                created += 1

            except Exception as e:
                errors.append({"index": i, "error": str(e)})

        return {"created": created, "skipped": skipped, "errors": errors}

    # -------------------------------------------------------------------------
    # 15. GOVERNANCE & TENANT ISOLATION
    # -------------------------------------------------------------------------

    async def verify_knowledge_access(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        artifact_id: str,
        required_permission: str = "knowledge:read",
    ) -> bool:
        """Verify caller has access to a knowledge artifact."""
        artifact = await self.get_artifact(db, caller=caller, artifact_id=artifact_id)
        if not artifact:
            return False

        # Check scope-based access
        if artifact.scope == "personal":
            return artifact.owner_id == caller.employee_id or artifact.author_id == caller.employee_id

        if artifact.scope == "project":
            # Check project membership
            from app.models.project import ProjectMember
            member = await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == artifact.scope_id,
                    ProjectMember.employee_id == caller.employee_id,
                )
            )
            return member.scalar_one_or_none() is not None

        if artifact.scope == "team":
            from app.models.team import TeamMember
            member = await db.execute(
                select(TeamMember).where(
                    TeamMember.team_id == artifact.scope_id,
                    TeamMember.employee_id == caller.employee_id,
                )
            )
            return member.scalar_one_or_none() is not None

        if artifact.scope == "department":
            # Check department membership via employee
            emp = await db.get(Employee, caller.employee_id)
            return emp and emp.department_id == artifact.scope_id

        # Organization scope - all members have read access
        return True


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

canonical_knowledge_service = CanonicalKnowledgeService()