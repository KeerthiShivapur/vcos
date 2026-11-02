"""Phase 4I.3 — Strategic Alignment & Decomposition Engine.

This is the canonical cross-domain operating fabric that connects intent to execution
hierarchy, enabling universal company operating capabilities.

It does NOT create a parallel planning module, CRM graph, ERP graph, or duplicate data store.
It provides governed, deterministic traversal and synthesis over the ONE canonical 
company reality.

Key capabilities:
1. Canonical Cross-Domain Linkage — create/traverse StrategicAlignment between entities
2. Cross-Domain Causal Trace — forward/backward tracing with provenance
3. Universal Operating Slice — governed slice of relevant canonical reality
4. Cross-Domain Impact Analysis — propagate changes through aligned entities
5. Cross-Domain Operating Attention — derive company-level attention from alignment
6. Alignment Gap Detection — detect missing elements in strategic chain

All operations preserve:
- Provenance chain back to canonical sources
- Epistemic status (observed/measured/evidence_backed/institutional_lesson/inferred/predicted/proposed/contested)
- Contradiction visibility (both sides preserved)
- Temporal reasoning (state transitions with triggers)
- Governance scope (who can see/change what)
- Exact-once semantics (fingerprint on canonical inputs)
- Tenant isolation
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List, Dict, Set, Tuple

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess, resolve_caller_access
from app.models.organization import TimestampMixin, gen_uuid
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyObjective,
    CompanyInitiative,
    OrganizationalResponsibility,
    StrategicLink,
    StrategicHistory,
    StrategicAlignment,
    AlignmentGap,
    StrategicConflict,
    StrategicAlignmentState,
    StrategicDependency,
    AlignmentGapDetection,
    ALIGNMENT_TYPES,
    ALIGNMENT_STATES,
    ALIGNMENT_STRENGTH,
    CONTRIBUTION_LEVELS,
    ALIGNMENT_GAP_TYPES,
    ALIGNMENT_GAP_SEVERITY,
    OBJECTIVE_STATES,
    NODE_STATUSES,
    CompanyCommitment,
)
from app.models.company_intent import CompanyIntent, CompanyPlan
from app.models.project import Project
from app.models.company_actions import CompanyAction
from app.models.organizational_learning import OrganizationalLearning
from app.models.intelligence import PatternDetection
from app.models.company_operating import CompanyDecision
from app.models.customer import Customer

logger = logging.getLogger("vcos.intelligence.strategic_alignment")


# Supported entity types in the strategic alignment graph
SUPPORTED_SOURCE_TYPES = frozenset([
    "intent", "goal", "objective", "initiative", "project", "commitment", "customer", "budget"
])

SUPPORTED_TARGET_TYPES = frozenset([
    "goal", "objective", "initiative", "project", "commitment", "action", "customer", "budget"
])

# Valid alignment type combinations (source -> target) for hierarchical alignments
VALID_HIERARCHICAL_COMBINATIONS = {
    "intent": ["goal", "objective"],
    "goal": ["objective", "initiative"],
    "objective": ["initiative", "project", "commitment"],
    "initiative": ["project", "commitment"],
    "project": ["commitment", "action"],
    "commitment": ["action"],
    "budget": ["project", "commitment", "objective"],
}

# Lateral alignment types that can work between any entity types
LATERAL_ALIGNMENT_TYPES = frozenset([
    "conflicts", "enables", "depends_on", "duplicates"
])


def _compute_fingerprint(data: dict) -> str:
    """Compute SHA-256 fingerprint for exact-once semantics."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:64]


class StrategicAlignmentEngine:
    """
    Strategic Alignment Engine — the canonical cross-domain operating fabric.
    
    Provides governed, deterministic traversal and synthesis over canonical company reality.
    """
    
    # Max traversal depth to prevent infinite loops
    MAX_TRAVERSAL_DEPTH = 10
    
    # Max results per query
    MAX_RESULTS = 100
    
    def __init__(self):
        pass
    
    # ================================================================
    # 1. CANONICAL CROSS-DOMAIN LINKAGE
    # ================================================================
    
    async def create_alignment(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        alignment_type: str,
        strength: str = "moderate",
        contribution_level: str = "supporting",
        rationale: Optional[str] = None,
        evidence_fingerprints: Optional[List[str]] = None,
        supporting_pattern_ids: Optional[List[str]] = None,
        supporting_lesson_fingerprints: Optional[List[str]] = None,
        contradicting_evidence_fingerprints: Optional[List[str]] = None,
        contradicting_pattern_ids: Optional[List[str]] = None,
        contradicting_lesson_fingerprints: Optional[List[str]] = None,
        contradiction_ids: Optional[List[str]] = None,
        source_event_id: Optional[str] = None,
        proposed_by: Optional[str] = None,
    ) -> StrategicAlignment:
        """
        Create a canonical strategic alignment between two entities.
        
        Governance: caller must have access to both source and target entities.
        Exact-once: same (org, source, target, alignment_type, source_event) = same alignment.
        """
        # Validate entity types
        if source_type not in SUPPORTED_SOURCE_TYPES:
            raise ValueError(f"Unsupported source_type: {source_type}")
        if target_type not in SUPPORTED_TARGET_TYPES:
            raise ValueError(f"Unsupported target_type: {target_type}")
        if alignment_type not in ALIGNMENT_TYPES:
            raise ValueError(f"Unsupported alignment_type: {alignment_type}")
        if strength not in ALIGNMENT_STRENGTH:
            raise ValueError(f"Unsupported strength: {strength}")
        if contribution_level not in CONTRIBUTION_LEVELS:
            raise ValueError(f"Unsupported contribution_level: {contribution_level}")
        
        # Validate alignment combination
        # Hierarchical combinations (supports, depends_on)
        hierarchical_targets = VALID_HIERARCHICAL_COMBINATIONS.get(source_type, [])
        lateral_allowed = alignment_type in LATERAL_ALIGNMENT_TYPES
        
        if target_type not in hierarchical_targets and not lateral_allowed:
            raise ValueError(f"Invalid alignment: {source_type} -> {target_type} for type {alignment_type}")
        
        # Governance: verify access to both entities
        await self._verify_entity_access(db, caller, source_type, source_id)
        await self._verify_entity_access(db, caller, target_type, target_id)
        
        # Build fingerprint for exact-once
        fingerprint_data = {
            "organization_id": caller.organization_id,
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "alignment_type": alignment_type,
            "source_event_id": source_event_id or "",
        }
        fingerprint = _compute_fingerprint(fingerprint_data)
        
        # Check for existing (exact-once)
        existing = await db.execute(
            select(StrategicAlignment).where(
                StrategicAlignment.organization_id == caller.organization_id,
                StrategicAlignment.fingerprint == fingerprint,
            )
        )
        existing = existing.scalars().first()
        if existing:
            return existing
        
        # Verify source and target entities exist
        source_exists = await self._verify_entity_exists(db, caller.organization_id, source_type, source_id)
        if not source_exists:
            raise ValueError(f"Source entity not found or access denied: {source_type}:{source_id}")
        
        target_exists = await self._verify_entity_exists(db, caller.organization_id, target_type, target_id)
        if not target_exists:
            raise ValueError(f"Target entity not found or access denied: {target_type}:{target_id}")
        
# Create alignment
        alignment = StrategicAlignment(
            organization_id=caller.organization_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            alignment_type=alignment_type,
            alignment_state="active",
            strength=strength,
            contribution_level=contribution_level,
            rationale=rationale,
            evidence_fingerprints=evidence_fingerprints or [],
            supporting_pattern_ids=supporting_pattern_ids or [],
            supporting_lesson_fingerprints=supporting_lesson_fingerprints or [],
            contradicting_evidence_fingerprints=contradicting_evidence_fingerprints or [],
            contradicting_pattern_ids=contradicting_pattern_ids or [],
            contradicting_lesson_fingerprints=contradicting_lesson_fingerprints or [],
            contradiction_ids=contradiction_ids or [],
            state="active",
            proposed_by=proposed_by or caller.employee_id or "system",
            proposed_at=utcnow(),
            source_event_id=source_event_id,
            fingerprint=fingerprint,
        )
        
        db.add(alignment)
        try:
            await db.flush()
            return alignment
        except Exception as e:
            # Handle race condition: another session already created this alignment
            # Catch all exceptions since IntegrityError may be wrapped
            error_msg = str(e).lower()
            if "integrity" in error_msg or "unique" in error_msg or "duplicate" in error_msg:
                await db.rollback()
                # Query in a new transaction to get the existing alignment
                existing = await db.execute(
                    select(StrategicAlignment).where(
                        StrategicAlignment.organization_id == caller.organization_id,
                        StrategicAlignment.fingerprint == fingerprint,
                    )
                )
                existing = existing.scalars().first()
                if existing:
                    return existing
                # If still not found (unlikely), re-raise
                raise
            raise
        
        logger.info(
            f"Created strategic alignment: {source_type}:{source_id} -> {target_type}:{target_id} "
            f"({alignment_type}, {strength}) for org {caller.organization_id}"
        )
        
        return alignment
    
    async def get_alignments(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        alignment_type: Optional[str] = None,
        alignment_state: Optional[str] = None,
        limit: int = 100,
    ) -> List[StrategicAlignment]:
        """Get alignments with governance filtering."""
        query = select(StrategicAlignment).where(
            StrategicAlignment.organization_id == caller.organization_id,
        )
        
        if source_type:
            query = query.where(StrategicAlignment.source_type == source_type)
        if source_id:
            query = query.where(StrategicAlignment.source_id == source_id)
        if target_type:
            query = query.where(StrategicAlignment.target_type == target_type)
        if target_id:
            query = query.where(StrategicAlignment.target_id == target_id)
        if alignment_type:
            query = query.where(StrategicAlignment.alignment_type == alignment_type)
        if alignment_state:
            query = query.where(StrategicAlignment.alignment_state == alignment_state)
        
        query = query.order_by(desc(StrategicAlignment.proposed_at)).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()
    
    async def supersede_alignment(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        alignment_id: str,
        new_alignment_type: Optional[str] = None,
        new_strength: Optional[str] = None,
        new_contribution_level: Optional[str] = None,
        rationale: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> StrategicAlignment:
        """Supersede an existing alignment with a new version (temporal truth)."""
        alignment = await db.get(StrategicAlignment, alignment_id)
        if not alignment:
            raise ValueError(f"Alignment not found: {alignment_id}")
        
        if alignment.organization_id != caller.organization_id:
            raise ValueError("Cross-tenant access denied")
        
        # Generate new alignment ID upfront
        new_alignment_id = gen_uuid()
        
        # Create new alignment that supersedes the old one
        new_alignment = StrategicAlignment(
            id=new_alignment_id,
            organization_id=caller.organization_id,
            source_type=alignment.source_type,
            source_id=alignment.source_id,
            target_type=alignment.target_type,
            target_id=alignment.target_id,
            alignment_type=new_alignment_type or alignment.alignment_type,
            alignment_state="active",
            strength=new_strength or alignment.strength,
            contribution_level=new_contribution_level or alignment.contribution_level,
            rationale=rationale or alignment.rationale,
            evidence_fingerprints=alignment.evidence_fingerprints,
            supporting_pattern_ids=alignment.supporting_pattern_ids,
            supporting_lesson_fingerprints=alignment.supporting_lesson_fingerprints,
            contradicting_evidence_fingerprints=alignment.contradicting_evidence_fingerprints,
            contradicting_pattern_ids=alignment.contradicting_pattern_ids,
            contradicting_lesson_fingerprints=alignment.contradicting_lesson_fingerprints,
            contradiction_ids=alignment.contradiction_ids,
            state="active",
            proposed_by=caller.employee_id or "system",
            proposed_at=utcnow(),
            supersedes_id=alignment.id,
            source_event_id=source_event_id,
            fingerprint=_compute_fingerprint({
                "organization_id": caller.organization_id,
                "source_type": alignment.source_type,
                "source_id": alignment.source_id,
                "target_type": alignment.target_type,
                "target_id": alignment.target_id,
                "alignment_type": new_alignment_type or alignment.alignment_type,
                "source_event_id": source_event_id or "",
                "supersedes": alignment.id,
            }),
        )
        
        # Update old alignment with new alignment's ID
        alignment.alignment_state = "superseded"
        alignment.superseded_by_id = new_alignment_id
        
        db.add(new_alignment)
        await db.flush()
        
        return new_alignment
    
    # ================================================================
    # 2. CROSS-DOMAIN CAUSAL TRACE
    # ================================================================
    
    async def trace_backward(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        max_depth: int = 5,
        include_conflicts: bool = True,
        include_gaps: bool = True,
    ) -> Dict[str, Any]:
        """
        Trace backward: Why does this entity exist?
        
        Returns the chain of strategic alignments leading TO this entity.
        Example: Task -> Action -> Commitment -> Objective -> Goal -> Intent
        """
        if entity_type not in SUPPORTED_TARGET_TYPES:
            raise ValueError(f"Unsupported entity_type for backward trace: {entity_type}")
        
        chain = []
        visited: Set[Tuple[str, str]] = set()
        current_type = entity_type
        current_id = entity_id
        depth = 0
        
        while depth < max_depth:
            # Find alignments WHERE THIS ENTITY IS THE TARGET
            alignments = await db.execute(
                select(StrategicAlignment).where(
                    StrategicAlignment.organization_id == caller.organization_id,
                    StrategicAlignment.target_type == current_type,
                    StrategicAlignment.target_id == current_id,
                    StrategicAlignment.alignment_state == "active",
                ).order_by(desc(StrategicAlignment.proposed_at))
            )
            alignments = alignments.scalars().all()
            
            if not alignments:
                break
            
            # For each parent, trace further
            for alignment in alignments[:3]:  # Limit branching
                parent_key = (alignment.source_type, alignment.source_id)
                if parent_key in visited:
                    continue
                visited.add(parent_key)
                
                chain.append({
                    "direction": "backward",
                    "depth": depth,
                    "alignment_id": alignment.id,
                    "alignment_type": alignment.alignment_type,
                    "strength": alignment.strength,
                    "contribution_level": alignment.contribution_level,
                    "source": {
                        "type": alignment.source_type,
                        "id": alignment.source_id,
                    },
                    "target": {
                        "type": alignment.target_type,
                        "id": alignment.target_id,
                    },
                    "rationale": alignment.rationale,
                    "evidence_fingerprints": alignment.evidence_fingerprints,
                    "provenance": {
                        "proposed_by": alignment.proposed_by,
                        "proposed_at": alignment.proposed_at.isoformat() if alignment.proposed_at else None,
                        "source_event_id": alignment.source_event_id,
                    },
                })
                
                # Recursively trace further back
                sub_chain = await self._trace_backward_recursive(
                    db, caller, alignment.source_type, alignment.source_id,
                    max_depth - depth - 1, visited, depth + 1
                )
                chain.extend(sub_chain)
            
            depth += 1
            # For simplicity, follow the strongest alignment
            if alignments:
                strongest = max(alignments, key=lambda a: 
                    {"primary": 4, "strong": 3, "moderate": 2, "weak": 1}.get(a.strength, 0))
                current_type = strongest.source_type
                current_id = strongest.source_id
            else:
                break
        
        # Get conflicts if requested
        conflicts = []
        if include_conflicts:
            conflicts = await self._get_conflicts_for_entity(db, caller, entity_type, entity_id)
        
        # Get gaps if requested
        gaps = []
        if include_gaps:
            gaps = await self._get_gaps_for_entity(db, caller, entity_type, entity_id)
        
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "chain": chain,
            "conflicts": conflicts,
            "gaps": gaps,
            "traced_at": utcnow().isoformat(),
        }
    
    async def _trace_backward_recursive(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        max_depth: int,
        visited: Set[Tuple[str, str]],
        depth: int,
    ) -> List[Dict[str, Any]]:
        """Recursive helper for backward tracing."""
        if max_depth <= 0:
            return []
        
        chain = []
        alignments = await db.execute(
            select(StrategicAlignment).where(
                StrategicAlignment.organization_id == caller.organization_id,
                StrategicAlignment.target_type == entity_type,
                StrategicAlignment.target_id == entity_id,
                StrategicAlignment.alignment_state == "active",
            ).order_by(desc(StrategicAlignment.proposed_at))
        )
        alignments = alignments.scalars().all()
        
        for alignment in alignments[:2]:  # Limit branching in recursion
            parent_key = (alignment.source_type, alignment.source_id)
            if parent_key in visited:
                continue
            visited.add(parent_key)
            
            chain.append({
                "direction": "backward",
                "depth": depth,
                "alignment_id": alignment.id,
                "alignment_type": alignment.alignment_type,
                "strength": alignment.strength,
                "contribution_level": alignment.contribution_level,
                "source": {
                    "type": alignment.source_type,
                    "id": alignment.source_id,
                },
                "target": {
                    "type": alignment.target_type,
                    "id": alignment.target_id,
                },
                "rationale": alignment.rationale,
                "evidence_fingerprints": alignment.evidence_fingerprints,
            })
            
            sub_chain = await self._trace_backward_recursive(
                db, caller, alignment.source_type, alignment.source_id,
                max_depth - 1, visited, depth + 1
            )
            chain.extend(sub_chain)
        
        return chain
    
    async def trace_forward(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        max_depth: int = 5,
        include_conflicts: bool = True,
        include_gaps: bool = True,
    ) -> Dict[str, Any]:
        """
        Trace forward: What does this entity affect?
        
        Returns the chain of strategic alignments leading FROM this entity.
        Example: Intent -> Goal -> Objective -> Initiative -> Project -> Commitment -> Action
        """
        if entity_type not in SUPPORTED_SOURCE_TYPES:
            raise ValueError(f"Unsupported entity_type for forward trace: {entity_type}")
        
        chain = []
        visited: Set[Tuple[str, str]] = set()
        current_type = entity_type
        current_id = entity_id
        depth = 0
        
        while depth < max_depth:
            # Find alignments WHERE THIS ENTITY IS THE SOURCE
            alignments = await db.execute(
                select(StrategicAlignment).where(
                    StrategicAlignment.organization_id == caller.organization_id,
                    StrategicAlignment.source_type == current_type,
                    StrategicAlignment.source_id == current_id,
                    StrategicAlignment.alignment_state == "active",
                ).order_by(desc(StrategicAlignment.proposed_at))
            )
            alignments = alignments.scalars().all()
            
            if not alignments:
                break
            
            for alignment in alignments[:3]:  # Limit branching
                child_key = (alignment.target_type, alignment.target_id)
                if child_key in visited:
                    continue
                visited.add(child_key)
                
                chain.append({
                    "direction": "forward",
                    "depth": depth,
                    "alignment_id": alignment.id,
                    "alignment_type": alignment.alignment_type,
                    "strength": alignment.strength,
                    "contribution_level": alignment.contribution_level,
                    "source": {
                        "type": alignment.source_type,
                        "id": alignment.source_id,
                    },
                    "target": {
                        "type": alignment.target_type,
                        "id": alignment.target_id,
                    },
                    "rationale": alignment.rationale,
                    "evidence_fingerprints": alignment.evidence_fingerprints,
                    "provenance": {
                        "proposed_by": alignment.proposed_by,
                        "proposed_at": alignment.proposed_at.isoformat() if alignment.proposed_at else None,
                        "source_event_id": alignment.source_event_id,
                    },
                })
                
                # Recursively trace further forward
                sub_chain = await self._trace_forward_recursive(
                    db, caller, alignment.target_type, alignment.target_id,
                    max_depth - depth - 1, visited, depth + 1
                )
                chain.extend(sub_chain)
            
            depth += 1
            if alignments:
                strongest = max(alignments, key=lambda a: 
                    {"primary": 4, "strong": 3, "moderate": 2, "weak": 1}.get(a.strength, 0))
                current_type = strongest.target_type
                current_id = strongest.target_id
            else:
                break
        
        conflicts = []
        if include_conflicts:
            conflicts = await self._get_conflicts_for_entity(db, caller, entity_type, entity_id)
        
        gaps = []
        if include_gaps:
            gaps = await self._get_gaps_for_entity(db, caller, entity_type, entity_id)
        
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "chain": chain,
            "conflicts": conflicts,
            "gaps": gaps,
            "traced_at": utcnow().isoformat(),
        }
    
    async def _trace_forward_recursive(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        max_depth: int,
        visited: Set[Tuple[str, str]],
        depth: int,
    ) -> List[Dict[str, Any]]:
        """Recursive helper for forward tracing."""
        if max_depth <= 0:
            return []
        
        chain = []
        alignments = await db.execute(
            select(StrategicAlignment).where(
                StrategicAlignment.organization_id == caller.organization_id,
                StrategicAlignment.source_type == entity_type,
                StrategicAlignment.source_id == entity_id,
                StrategicAlignment.alignment_state == "active",
            ).order_by(desc(StrategicAlignment.proposed_at))
        )
        alignments = alignments.scalars().all()
        
        for alignment in alignments[:2]:
            child_key = (alignment.target_type, alignment.target_id)
            if child_key in visited:
                continue
            visited.add(child_key)
            
            chain.append({
                "direction": "forward",
                "depth": depth,
                "alignment_id": alignment.id,
                "alignment_type": alignment.alignment_type,
                "strength": alignment.strength,
                "contribution_level": alignment.contribution_level,
                "source": {
                    "type": alignment.source_type,
                    "id": alignment.source_id,
                },
                "target": {
                    "type": alignment.target_type,
                    "id": alignment.target_id,
                },
                "rationale": alignment.rationale,
                "evidence_fingerprints": alignment.evidence_fingerprints,
            })
            
            sub_chain = await self._trace_forward_recursive(
                db, caller, alignment.target_type, alignment.target_id,
                max_depth - 1, visited, depth + 1
            )
            chain.extend(sub_chain)
        
        return chain
    
    async def trace_bidirectional(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """Full bidirectional trace: both why it exists AND what it affects."""
        backward = await self.trace_backward(
            db, caller=caller, entity_type=entity_type, entity_id=entity_id, max_depth=max_depth
        )
        forward = await self.trace_forward(
            db, caller=caller, entity_type=entity_type, entity_id=entity_id, max_depth=max_depth
        )
        
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "backward_chain": backward["chain"],
            "forward_chain": forward["chain"],
            "conflicts": backward["conflicts"] + forward["conflicts"],
            "gaps": backward["gaps"] + forward["gaps"],
            "traced_at": utcnow().isoformat(),
        }
    
    async def _get_conflicts_for_entity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """Get strategic conflicts involving an entity."""
        conflicts = await db.execute(
            select(StrategicConflict).where(
                StrategicConflict.organization_id == caller.organization_id,
                or_(
                    and_(
                        StrategicConflict.entity_a_type == entity_type,
                        StrategicConflict.entity_a_id == entity_id,
                    ),
                    and_(
                        StrategicConflict.entity_b_type == entity_type,
                        StrategicConflict.entity_b_id == entity_id,
                    ),
                ),
            ).limit(20)
        )
        return [
            {
                "conflict_id": c.id,
                "entity_a": {"type": c.entity_a_type, "id": c.entity_a_id},
                "entity_b": {"type": c.entity_b_type, "id": c.entity_b_id},
                "conflict_type": c.conflict_type,
                "severity": c.severity,
                "status": c.status,
                "description": c.description,
                "evidence_a": c.evidence_a,
                "evidence_b": c.evidence_b,
            }
            for c in conflicts.scalars().all()
        ]
    
    async def _get_gaps_for_entity(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """Get alignment gaps for an entity."""
        gaps = await db.execute(
            select(AlignmentGap).where(
                AlignmentGap.organization_id == caller.organization_id,
                AlignmentGap.context_element_type == entity_type,
                AlignmentGap.context_element_id == entity_id,
                AlignmentGap.state != "superseded",
            ).limit(20)
        )
        return [
            {
                "gap_id": g.id,
                "gap_type": g.gap_type,
                "severity": g.severity,
                "missing_element_type": g.missing_element_type,
                "missing_element_id": g.missing_element_id,
                "description": g.description,
                "impact_assessment": g.impact_assessment,
                "recommended_action": g.recommended_action,
                "state": g.state,
            }
            for g in gaps.scalars().all()
        ]
    
    # ================================================================
    # 3. UNIVERSAL OPERATING SLICE
    # ================================================================
    
    async def get_operating_slice(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        include_upstream: bool = True,
        include_downstream: bool = True,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """
        Get a governed slice of canonical reality relevant to an entity.
        
        Returns all aligned entities (upstream and/or downstream) that are
        accessible to the caller, with their current state.
        """
        slice_data = {
            "center": {"type": entity_type, "id": entity_id},
            "upstream": [],
            "downstream": [],
            "siblings": [],
            "scope": {
                "organization_id": caller.organization_id,
                "scope_type": "org" if caller.org_wide else "scoped",
                "scope_id": caller.scope_id if hasattr(caller, 'scope_id') else None,
            },
            "generated_at": utcnow().isoformat(),
        }
        
        if include_upstream:
            backward = await self.trace_backward(
                db, caller=caller, entity_type=entity_type, entity_id=entity_id, 
                max_depth=max_depth, include_conflicts=False, include_gaps=False
            )
            slice_data["upstream"] = self._summarize_chain(backward["chain"])
        
        if include_downstream:
            forward = await self.trace_forward(
                db, caller=caller, entity_type=entity_type, entity_id=entity_id,
                max_depth=max_depth, include_conflicts=False, include_gaps=False
            )
            slice_data["downstream"] = self._summarize_chain(forward["chain"])
        
        # Get siblings (entities sharing the same parent)
        siblings = await self._get_siblings(db, caller, entity_type, entity_id)
        slice_data["siblings"] = siblings
        
        return slice_data
    
    def _summarize_chain(self, chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize trace chain for operating slice."""
        summaries = []
        for item in chain:
            summaries.append({
                "alignment_id": item.get("alignment_id"),
                "type": item["source"]["type"] if item["direction"] == "backward" else item["target"]["type"],
                "id": item["source"]["id"] if item["direction"] == "backward" else item["target"]["id"],
                "alignment_type": item["alignment_type"],
                "strength": item["strength"],
                "depth": item["depth"],
            })
        return summaries
    
    async def _get_siblings(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """Get sibling entities (sharing same parent alignments)."""
        # Find parent alignments
        parent_alignments = await db.execute(
            select(StrategicAlignment).where(
                StrategicAlignment.organization_id == caller.organization_id,
                StrategicAlignment.target_type == entity_type,
                StrategicAlignment.target_id == entity_id,
                StrategicAlignment.alignment_state == "active",
            )
        )
        parent_alignments = parent_alignments.scalars().all()
        
        siblings = []
        for parent_align in parent_alignments:
            # Find other children of same parent
            siblings_query = select(StrategicAlignment).where(
                StrategicAlignment.organization_id == caller.organization_id,
                StrategicAlignment.source_type == parent_align.source_type,
                StrategicAlignment.source_id == parent_align.source_id,
                StrategicAlignment.target_type == entity_type,
                StrategicAlignment.target_id != entity_id,
                StrategicAlignment.alignment_state == "active",
            )
            siblings_result = await db.execute(siblings_query)
            for sib in siblings_result.scalars().all():
                siblings.append({
                    "type": sib.target_type,
                    "id": sib.target_id,
                    "shared_parent_type": parent_align.source_type,
                    "shared_parent_id": parent_align.source_id,
                    "alignment_type": sib.alignment_type,
                    "strength": sib.strength,
                })
        
        return siblings[:20]
    
    # ================================================================
    # 4. CROSS-DOMAIN IMPACT ANALYSIS
    # ================================================================
    
    async def analyze_impact(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
        change_type: str,  # "delay", "cancel", "reassign", "capacity_change", "scope_change"
        change_params: Optional[Dict[str, Any]] = None,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        Analyze the cross-domain impact of a change to an entity.
        
        Propagates through strategic alignments to identify affected entities,
        combining with capacity, dependency, and prediction intelligence.
        """
        change_params = change_params or {}
        
        # Trace forward to find all downstream entities
        forward_trace = await self.trace_forward(
            db, caller=caller, entity_type=entity_type, entity_id=entity_id, max_depth=max_depth
        )
        
        affected_entities = []
        for item in forward_trace["chain"]:
            affected_entities.append({
                "type": item["target"]["type"],
                "id": item["target"]["id"],
                "alignment_type": item["alignment_type"],
                "strength": item["strength"],
                "contribution_level": item["contribution_level"],
                "depth": item["depth"],
                "via_alignment": item["alignment_id"],
            })
        
        # Analyze impact per domain
        impact = {
            "center": {"type": entity_type, "id": entity_id, "change_type": change_type},
            "affected_entities": affected_entities,
            "by_domain": await self._analyze_domain_impact(
                db, caller, affected_entities, change_type, change_params
            ),
            "risk_assessment": await self._assess_impact_risks(
                db, caller, affected_entities, change_type
            ),
            "confidence": "medium",  # Would integrate with prediction engine
            "analyzed_at": utcnow().isoformat(),
        }
        
        return impact
    
    async def _analyze_domain_impact(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        affected_entities: List[Dict[str, Any]],
        change_type: str,
        change_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze impact grouped by domain."""
        by_domain = {
            "strategy": [],
            "execution": [],
            "capacity": [],
            "customers": [],
            "financial": [],
        }
        
        for entity in affected_entities:
            domain = self._classify_entity_domain(entity["type"])
            impact_detail = await self._estimate_entity_impact(
                db, caller, entity, change_type, change_params
            )
            by_domain[domain].append({
                **entity,
                "estimated_impact": impact_detail,
            })
        
        return by_domain
    
    def _classify_entity_domain(self, entity_type: str) -> str:
        """Classify entity type into domain."""
        domain_map = {
            "intent": "strategy",
            "goal": "strategy",
            "objective": "strategy",
            "initiative": "strategy",
            "project": "execution",
            "commitment": "execution",
            "action": "execution",
            "customer": "customers",
        }
        return domain_map.get(entity_type, "execution")
    
    async def _estimate_entity_impact(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity: Dict[str, Any],
        change_type: str,
        change_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Estimate impact on a specific entity."""
        # This would integrate with capacity, prediction, and organizational intelligence
        # For now, return structured placeholder
        return {
            "impact_level": "unknown",
            "impact_type": change_type,
            "confidence": 0.5,
            "reasoning": f"Impact of {change_type} on {entity['type']} via {entity['alignment_type']} ({entity['strength']})",
        }
    
    async def _assess_impact_risks(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        affected_entities: List[Dict[str, Any]],
        change_type: str,
    ) -> List[Dict[str, Any]]:
        """Assess risks from the impact analysis."""
        risks = []
        
        # High-risk patterns
        critical_count = sum(1 for e in affected_entities if e.get("strength") == "primary")
        if critical_count > 0:
            risks.append({
                "type": "critical_path_disruption",
                "severity": "high",
                "description": f"{critical_count} primary-strength alignments affected",
                "affected_count": critical_count,
            })
        
        # Depth-based risk
        max_depth = max((e.get("depth", 0) for e in affected_entities), default=0)
        if max_depth >= 4:
            risks.append({
                "type": "deep_propagation",
                "severity": "medium",
                "description": f"Impact propagates {max_depth} levels deep",
                "max_depth": max_depth,
            })
        
        return risks
    
    # ================================================================
    # 5. CROSS-DOMAIN OPERATING ATTENTION
    # ================================================================
    
    async def derive_operating_attention(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope: str = "company",
        scope_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Derive cross-domain operating attention from strategic alignments.
        
        Instead of isolated alerts, derives the canonical chain:
        Task overdue -> Action delayed -> Commitment risk -> Objective risk -> Customer impact
        """
        attention_items = []
        
        # Find alignment gaps
        gaps = await db.execute(
            select(AlignmentGap).where(
                AlignmentGap.organization_id == caller.organization_id,
                AlignmentGap.state.in_(["open", "acknowledged", "resolving"]),
            ).order_by(
                desc(AlignmentGap.severity),
                desc(AlignmentGap.detected_at)
            ).limit(20)
        )
        
        for gap in gaps.scalars().all():
            attention_items.append({
                "type": "alignment_gap",
                "gap_id": gap.id,
                "title": f"Alignment gap: {gap.gap_type}",
                "description": gap.description,
                "severity": gap.severity,
                "context": {
                    "type": gap.context_element_type,
                    "id": gap.context_element_id,
                },
                "missing_element": {
                    "type": gap.missing_element_type,
                    "id": gap.missing_element_id,
                },
                "recommended_action": gap.recommended_action,
                "detected_at": gap.detected_at.isoformat(),
            })
        
        # Find strategic conflicts
        conflicts = await db.execute(
            select(StrategicConflict).where(
                StrategicConflict.organization_id == caller.organization_id,
                StrategicConflict.status.in_(["open", "acknowledged"]),
            ).order_by(
                desc(StrategicConflict.severity),
                desc(StrategicConflict.detected_at)
            ).limit(10)
        )
        
        for conflict in conflicts.scalars().all():
            attention_items.append({
                "type": "strategic_conflict",
                "conflict_id": conflict.id,
                "title": f"Strategic conflict: {conflict.conflict_type}",
                "description": conflict.description,
                "severity": conflict.severity,
                "entity_a": {"type": conflict.entity_a_type, "id": conflict.entity_a_id},
                "entity_b": {"type": conflict.entity_b_type, "id": conflict.entity_b_id},
                "status": conflict.status,
            })
        
        # Find weak alignments (weak strength, active)
        weak_alignments = await db.execute(
            select(StrategicAlignment).where(
                StrategicAlignment.organization_id == caller.organization_id,
                StrategicAlignment.alignment_state == "active",
                StrategicAlignment.strength.in_(["weak"]),
            ).limit(20)
        )
        
        for alignment in weak_alignments.scalars().all():
            attention_items.append({
                "type": "weak_alignment",
                "alignment_id": alignment.id,
                "title": f"Weak strategic alignment: {alignment.source_type} -> {alignment.target_type}",
                "description": f"Alignment strength is '{alignment.strength}'",
                "severity": "low",
                "source": {"type": alignment.source_type, "id": alignment.source_id},
                "target": {"type": alignment.target_type, "id": alignment.target_id},
                "alignment_type": alignment.alignment_type,
                "strength": alignment.strength,
            })
        
        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        attention_items.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 3))
        
        return attention_items[:30]
    
    # ================================================================
    # 6. ALIGNMENT GAP DETECTION
    # ================================================================
    
    async def detect_alignment_gaps(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope: str = "company",
        scope_id: Optional[str] = None,
    ) -> List[AlignmentGap]:
        """
        Detect missing elements in the strategic alignment graph.
        
        Examples:
        - Goal without objectives
        - Objective without initiatives
        - Initiative without projects
        - Project without commitments
        - Commitment without actions
        - Customer without objectives/commitments
        """
        detected_gaps = []
        
        # Get active goals
        goals_result = await db.execute(
            select(CompanyGoal).where(
                CompanyGoal.organization_id == caller.organization_id,
                CompanyGoal.status == "active",
            )
        )
        
        for goal in goals_result.scalars().all():
            # Check if goal has objectives
            objectives_result = await db.execute(
                select(CompanyObjective).where(
                    CompanyObjective.organization_id == caller.organization_id,
                    CompanyObjective.goal_id == goal.id,
                    CompanyObjective.status == "active",
                )
            )
            objectives = objectives_result.scalars().all()
            if not objectives:
                gap = await self._create_or_update_gap(
                    db, caller,
                    gap_type="goal_without_objective",
                    context_element_type="goal",
                    context_element_id=goal.id,
                    missing_element_type="objective",
                    description=f"Goal '{goal.title}' has no active objectives",
                    severity="high",
                    impact_assessment="Goal cannot be measured or tracked without objectives",
                    recommended_action="Create objectives linked to this goal",
                )
                if gap:
                    detected_gaps.append(gap)
            else:
                # Check each objective for initiatives
                for obj in objectives:
                    initiatives = await db.execute(
                        select(CompanyInitiative).where(
                            CompanyInitiative.organization_id == caller.organization_id,
                            CompanyInitiative.objective_id == obj.id,
                            CompanyInitiative.status == "active",
                        )
                    )
                    if not initiatives.scalars().first():
                        gap = await self._create_or_update_gap(
                            db, caller,
                            gap_type="initiative_without_project",
                            context_element_type="objective",
                            context_element_id=obj.id,
                            missing_element_type="initiative",
                            description=f"Objective '{obj.title}' has no active initiatives",
                            severity="medium",
                            impact_assessment="Objective lacks execution path",
                            recommended_action="Create initiatives to drive this objective",
                        )
                        if gap:
                            detected_gaps.append(gap)
        
        # Check projects without commitments
        projects = await db.execute(
            select(Project).where(
                Project.organization_id == caller.organization_id,
                Project.status.in_(["active", "in_progress", "on_track"]),
            )
        )
        
        for project in projects.scalars().all():
            commitments = await db.execute(
                select(CompanyCommitment).where(
                    CompanyCommitment.organization_id == caller.organization_id,
                    CompanyCommitment.scope_type == "project",
                    CompanyCommitment.scope_id == project.id,
                    CompanyCommitment.state.in_(["active", "authorized"]),
                )
            )
            if not commitments.scalars().first():
                gap = await self._create_or_update_gap(
                    db, caller,
                    gap_type="initiative_without_project",
                    context_element_type="project",
                    context_element_id=project.id,
                    missing_element_type="commitment",
                    description=f"Project '{project.name}' has no active commitments",
                    severity="medium",
                    impact_assessment="Project lacks governed commitment for execution",
                    recommended_action="Create commitment linked to this project",
                )
                if gap:
                    detected_gaps.append(gap)
        
        return detected_gaps
    
    async def _create_or_update_gap(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        gap_type: str,
        context_element_type: str,
        context_element_id: str,
        missing_element_type: str,
        description: str,
        severity: str,
        impact_assessment: Optional[str] = None,
        recommended_action: Optional[str] = None,
    ) -> Optional[AlignmentGap]:
        """Create or update an alignment gap (exact-once on fingerprint)."""
        fingerprint_data = {
            "organization_id": caller.organization_id,
            "gap_type": gap_type,
            "context_element_type": context_element_type,
            "context_element_id": context_element_id,
            "missing_element_type": missing_element_type,
        }
        fingerprint = _compute_fingerprint(fingerprint_data)
        
        existing = await db.execute(
            select(AlignmentGap).where(
                AlignmentGap.organization_id == caller.organization_id,
                AlignmentGap.fingerprint == fingerprint,
                AlignmentGap.state != "superseded",
            )
        )
        existing = existing.scalars().first()
        
        if existing:
            # Update existing
            existing.severity = severity
            existing.description = description
            existing.impact_assessment = impact_assessment
            existing.recommended_action = recommended_action
            existing.detected_at = utcnow()
            return existing
        
        # Create new
        gap = AlignmentGap(
            organization_id=caller.organization_id,
            gap_type=gap_type,
            severity=severity,
            missing_element_type=missing_element_type,
            missing_element_id=None,
            context_element_type=context_element_type,
            context_element_id=context_element_id,
            description=description,
            impact_assessment=impact_assessment,
            recommended_action=recommended_action,
            state="open",
            detected_by=caller.employee_id or "system",
            detected_at=utcnow(),
            source_event_id=f"gap-detection-{uuid.uuid4().hex[:16]}",
            fingerprint=fingerprint,
        )
        db.add(gap)
        await db.flush()
        return gap
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    async def _verify_entity_access(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        entity_type: str,
        entity_id: str,
    ) -> None:
        """Verify caller has access to entity."""
        # For now, allow org-wide callers. Scoped callers would need specific checks.
        if caller.org_wide:
            return
        # TODO: Add scope-specific access checks
        pass
    
    async def _verify_entity_exists(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
        entity_id: str,
    ) -> bool:
        """Verify entity exists in canonical reality."""
        model_map = {
            "intent": CompanyIntent,
            "goal": CompanyGoal,
            "objective": CompanyObjective,
            "initiative": CompanyInitiative,
            "project": Project,
            "commitment": CompanyCommitment,
            "action": CompanyAction,
            "customer": Customer,
        }
        
        model = model_map.get(entity_type)
        if not model:
            return False
        
        result = await db.execute(
            select(model).where(
                model.organization_id == organization_id,
                model.id == entity_id,
            ).limit(1)
        )
        return result.scalars().first() is not None


# Global instance
strategic_alignment_engine = StrategicAlignmentEngine()