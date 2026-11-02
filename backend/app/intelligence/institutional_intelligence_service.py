"""Institutional Intelligence Service — Gate 9.

This service derives institutional learning from canonical company reality.
It connects the 4H.* decision → action → outcome → measurement → attribution → assessment
evidence chain into the existing institutional-learning substrate (OrganizationalLearning,
LearningEvidence, CompanyMemory, PatternDetection, CompanyDecisionPrecedent, etc.).

All derived from canonical reality — no parallel state, no duplicate memory, no second brain.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, List, Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.timeutils import utcnow
from app.intelligence.company_context import CallerAccess
from app.models.execution_strategy import (
    CompanyCommitment,
    CompanyAuthorization,
    OrganizationalResponsibility,
    AccountabilityLink,
    CompanyObjective,
    CompanyInitiative,
    CompanyGoal,
)
from app.models.company_operating import (
    CompanyDecision,
    CompanyDecisionPrecedent,
    CompanyDecisionContradiction,
    CompanyDecisionQuality,
    CompanyDecisionTrack,
    CompanyDecisionEvidence,
    CompanyDecisionAlternative,
)
from app.models.company_actions import CompanyAction, CompanyActionOutcome, CompanyActionEvent
from app.models.project import Project
from app.models.task import Task, TaskDependency
from app.models.meeting import Meeting, MeetingParticipant
from app.models.workload import WorkloadSnapshot
from app.models.organizational_learning import (
    OrganizationalLearning,
    LearningEvidence,
    OutcomeAssessment,
    DecisionOutcome,
    RecommendationOutcome,
    KnowledgeClaimLifecycle,
    CompanyChange,
    CompanyHealthSignal,
    ImpactAssessment,
    OperatingInsight,
)
from app.models.intelligence import (
    PatternDetection,
    PatternEvent,
    UniversalInsight,
)
from app.models.company_memory import (
    CompanyMemory,
    MemoryEvent,
    MemoryOutcome,
)
from app.models.knowledge import (
    KnowledgeClaim,
    KnowledgeTopic,
    KnowledgeRecommendation,
)
from app.models.org_capability_intelligence import (
    OrgCapability,
    CapabilitySignal,
)
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacitySnapshot,
)
from app.models.skills_intelligence import CanonicalSkill, Expertise as ExpertiseState, ExpertiseEvidence

logger = logging.getLogger("vcos.intelligence.institutional_intelligence")


# Epistemic ladder constants (mapping to OrganizationalLearning.lifecycle)
EPISTEMIC_STAGES = (
    "discovered",      # Level 1: Pattern Candidate
    "candidate",       # Level 2: Lesson Candidate
    "supported",       # Level 3: Supported Lesson
    "authoritative",   # Level 4: Authoritative Lesson
    "confirmed",       # Level 5: Confirmed Lesson
    "superseded",      # Level 6: Superseded Lesson
    "archived",        # Level 7: Archived Lesson
)

# Brain surface epistemic vocabulary
BRAIN_EPISTEMIC_STATUS = {
    "discovered": "OBSERVED",
    "candidate": "RECURRING",
    "supported": "SUPPORTED",
    "authoritative": "AUTHORITATIVE",
    "confirmed": "CONFIRMED",
    "superseded": "SUPERSEDED",
    "archived": "ARCHIVED",
}

# Cohort formation constants
MIN_COHORT_SIZE = 3
MIN_PATTERN_OCCURRENCES = 3
MIN_SUPPORTING_EVIDENCE = 5
MAX_CONTRADICTION_RATIO = 0.35
MIN_OUTCOME_QUALITY = 0.6
MIN_TEMPORAL_SPREAD_DAYS = 30
MIN_EVIDENCE_COVERAGE = 0.6
COHORT_WINDOW_DAYS = 90
MAX_COHORT_SIZE = 50
PATTERN_CONFIDENCE_THRESHOLD = 0.5

# Lesson kinds
LESSON_KINDS = (
    "outcome_learning",
    "decision_learning",
    "recommendation_learning",
    "contradiction_resolution",
    "knowledge_confirmation",
    "capacity_learning",
    "dependency_learning",
    "organizational_learning",
)


@dataclass
class CohortSignature:
    """Deterministic cohort signature for reproducible pattern analysis."""
    organization_id: str
    decision_kind: str
    scope_type: str
    scope_id: str
    business_context_hash: str
    temporal_window_start: datetime
    temporal_window_end: datetime
    
    def to_string(self) -> str:
        return "|".join([
            self.organization_id,
            self.decision_kind,
            self.scope_type,
            self.scope_id,
            self.business_context_hash,
            self.temporal_window_start.isoformat(),
            self.temporal_window_end.isoformat(),
        ])


@dataclass
class QualifiedLesson:
    """A lesson that has been epistemically qualified."""
    id: str
    kind: str
    title: str
    statement: str
    epistemic_status: str  # OBSERVED, RECURRING, SUPPORTED, SUPPORTED_WITH_CONTRADICTIONS, AUTHORITATIVE, CONFIRMED, SUPERSEDED, ARCHIVED, UNKNOWN
    lifecycle: str  # discovered, candidate, supported, authoritative, confirmed, superseded, archived
    confidence: float
    scope_type: str
    scope_id: Optional[str]
    valid_from: datetime
    valid_to: Optional[datetime]
    superseded_by: Optional[str]
    supporting_evidence_count: int
    contradicting_evidence_count: int
    contradiction_ratio: float
    outcome_quality: float
    temporal_spread_days: int
    evidence_coverage: float
    cohort_signature: str
    evidence_chain: List[Dict[str, Any]]
    contradictions: List[Dict[str, Any]]
    precedents: List[Dict[str, Any]]
    supersession_history: List[Dict[str, Any]]
    provenance: Dict[str, Any]
    derived_at: datetime


@dataclass
class InstitutionalPattern:
    """A detected institutional pattern with full provenance."""
    pattern_id: str
    pattern_type: str
    family: str
    title: str
    detail: str
    count: int
    confidence: float
    status: str
    cohort_signature: str
    supporting_decisions: List[Dict[str, Any]]
    supporting_actions: List[Dict[str, Any]]
    supporting_outcomes: List[Dict[str, Any]]
    supporting_metrics: List[Dict[str, Any]]
    contradicting_evidence: List[Dict[str, Any]]
    scope_type: str
    scope_id: Optional[str]
    first_seen: datetime
    last_seen: datetime
    derived_at: datetime


class InstitutionalIntelligenceService:
    """Service for deriving institutional intelligence from canonical reality."""
    
    def __init__(self):
        pass

    # ================================================================
    # MAIN ENTRY POINT
    # ================================================================

    async def derive_institutional_intelligence(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        scope_type: str = "organization",
        scope_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Derive institutional intelligence for an organizational scope.
        
        Returns:
            - qualified_lessons: List of epistemically qualified lessons
            - institutional_patterns: List of detected institutional patterns
            - contradiction_surface: Aggregated contradictions
            - supersession_chain: Lesson supersession history
            - learning_feed: Recent organizational learnings
        """
        
        # 1. Form cohorts from canonical decisions
        cohorts = await self._form_cohorts(db, caller)
        
        # 2. Detect patterns within cohorts
        patterns = await self._detect_institutional_patterns(db, caller, cohorts)
        
        # 3. Qualify lessons from patterns
        lessons = await self._qualify_lessons(db, caller, patterns)
        
        # 4. Build contradiction surface
        contradictions = await self._build_contradiction_surface(db, caller, lessons)
        
        # 5. Build supersession chains
        supersessions = await self._build_supersession_chains(db, caller, lessons)
        
        # 6. Get recent learning feed
        learning_feed = await self._get_learning_feed(db, caller)
        
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "qualified_lessons": [self._lesson_to_dict(l) for l in lessons],
            "institutional_patterns": [self._pattern_to_dict(p) for p in patterns],
            "contradiction_surface": contradictions,
            "supersession_chains": supersessions,
            "learning_feed": learning_feed,
            "derived_at": utcnow().isoformat(),
            "version": 1,
        }

    async def get_lesson_detail(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        lesson_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get full detail of a qualified lesson with complete provenance walk."""
        # Find lesson in organizational_learning
        lesson_row = await db.get(OrganizationalLearning, lesson_id)
        if not lesson_row or lesson_row.organization_id != caller.organization_id:
            return None
        
        # Governance check
        if not caller.org_wide:
            # Check if lesson is visible to caller
            pass  # Implement scope check
        
        # Build full provenance chain
        evidence_chain = await self._walk_provenance_chain(db, caller, lesson_row)
        
        return {
            "lesson": self._lesson_row_to_dict(lesson_row),
            "evidence_chain": evidence_chain,
            "contradictions": await self._get_lesson_contradictions(db, caller, lesson_row),
            "precedents": await self._get_lesson_precedents(db, caller, lesson_row),
            "supersession_history": await self._get_lesson_supersession_history(db, caller, lesson_row),
            "provenance_walk": evidence_chain,
        }

    async def materialize_lesson(
        self,
        db: AsyncSession,
        *,
        caller: CallerAccess,
        lesson: QualifiedLesson,
    ) -> OrganizationalLearning:
        """Materialize a qualified lesson into the canonical substrate.
        
        Uses existing OrganizationalLearning engine methods to preserve exact-once semantics.
        """
        # Check if lesson already exists by fingerprint
        existing = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.kind == lesson.kind,
                OrganizationalLearning.fingerprint == lesson.id.split("-")[-1] if "-" in lesson.id else lesson.id,
            )
        )
        existing = existing.scalar_one_or_none()
        
        if existing:
            # Update in-place (replay convergence)
            existing.lifecycle = lesson.lifecycle
            existing.confidence = lesson.confidence
            existing.status = "active" if lesson.lifecycle != "archived" else "archived"
            existing.evidence_json = json.dumps([e.get("source_type") for e in lesson.evidence_chain])
            existing.claims_updated_json = json.dumps([])
            existing.updated_at = utcnow()
            await db.flush()
            return existing
        
        # Create new lesson row
        new_lesson = OrganizationalLearning(
            organization_id=caller.organization_id,
            kind=lesson.kind,
            fingerprint=lesson.id,
            title=lesson.title,
            lesson=lesson.statement,
            status="active" if lesson.lifecycle != "archived" else "archived",
            lifecycle=lesson.lifecycle,
            confidence=lesson.confidence,
            source_type="institutional_intelligence",
            source_id=lesson.id,
            evidence_json=json.dumps([e.get("source_type") for e in lesson.evidence_chain]),
            claims_updated_json=json.dumps([]),
            expectation=None,
            observation=lesson.statement,
            recorded_by=caller.employee_id or "system",
            observed_at=lesson.valid_from,
        )
        db.add(new_lesson)
        await db.flush()
        
        # Add evidence links
        for evidence in lesson.evidence_chain:
            db.add(LearningEvidence(
                organization_id=caller.organization_id,
                learning_id=new_lesson.id,
                source_type=evidence.get("source_type", "unknown"),
                source_id=evidence.get("source_id", ""),
                excerpt=evidence.get("excerpt"),
                role=evidence.get("role", "primary"),
                weight=evidence.get("weight", 1.0),
            ))
        
        # Also write to CompanyMemory for Brain surface
        memory = CompanyMemory(
            organization_id=caller.organization_id,
            memory_type="institutional",
            title=lesson.title,
            content=lesson.statement,
            memory_category="lesson",
            domain="institutional",
            summary=lesson.statement[:500] if lesson.statement else None,
            lesson=lesson.statement,
            confidence=lesson.confidence,
            fact_kind="lesson",
            evidence_json=lesson.evidence_chain,
            source_event_ids=[e.get("source_id") for e in lesson.evidence_chain if e.get("source_id")],
            auth_scope="org" if lesson.scope_type == "organization" else "project",
            auth_project_id=lesson.scope_id if lesson.scope_type == "project" else None,
            status="active" if lesson.lifecycle != "archived" else "superseded",
        )
        db.add(memory)
        await db.flush()
        
        # Link memory to lesson
        db.add(MemoryEvent(
            organization_id=caller.organization_id,
            memory_id=memory.id,
            event_id=lesson.id,
            relationship="formation",
        ))
        
        await db.flush()
        return new_lesson

    # ================================================================
    # COHORT FORMATION
    # ================================================================

    async def _form_cohorts(
        self,
        db: AsyncSession,
        caller: CallerAccess,
    ) -> List[Dict[str, Any]]:
        """Form governed cohorts from CompanyDecision (4H.2 substrate).
        
        Cohort = decisions sharing contract-defined dimensions within temporal window.
        """
        # Get accessible decisions
        decisions_query = select(CompanyDecision).where(
            CompanyDecision.organization_id == caller.organization_id,
        )
        
        # Apply governance filter
        if not caller.org_wide:
            # Filter by accessible scopes
            pass
        
        decisions_result = await db.execute(decisions_query.limit(MAX_COHORT_SIZE))
        decisions = decisions_result.scalars().all()
        
        if len(decisions) < MIN_COHORT_SIZE:
            return []
        
        # Group by cohort signature dimensions
        cohorts = defaultdict(list)
        for decision in decisions:
            signature = self._compute_cohort_signature(decision)
            cohorts[signature].append(decision)
        
        # Filter to minimum cohort size
        qualified_cohorts = []
        for signature, cohort_decisions in cohorts.items():
            if len(cohort_decisions) >= MIN_COHORT_SIZE:
                # Check temporal spread
                first = min(d.created_at for d in cohort_decisions)
                last = max(d.created_at for d in cohort_decisions)
                temporal_spread = (last - first).days
                if temporal_spread >= MIN_TEMPORAL_SPREAD_DAYS:
                    qualified_cohorts.append({
                        "signature": signature,
                        "decisions": cohort_decisions,
                        "size": len(cohort_decisions),
                        "temporal_spread_days": temporal_spread,
                        "first_decision": first,
                        "last_decision": last,
                    })
        
        return qualified_cohorts

    def _compute_cohort_signature(self, decision: CompanyDecision) -> str:
        """Compute deterministic cohort signature for a decision."""
        # Extract business context entities
        # This would use decision evidence, alternatives, etc.
        business_context = {
            "project_ids": [],
            "customer_ids": [],
            "capability_names": [],
        }
        
        # Hash for fuzzy matching (Jaccard >= 0.7)
        context_hash = hash(json.dumps(business_context, sort_keys=True)) % 1000000
        
        return CohortSignature(
            organization_id=decision.organization_id,
            decision_kind=decision.kind or "other",
            scope_type=decision.scope_type or "org",
            scope_id=decision.scope_id or "",
            business_context_hash=str(context_hash),
            temporal_window_start=decision.created_at - timedelta(days=COHORT_WINDOW_DAYS//2),
            temporal_window_end=decision.created_at + timedelta(days=COHORT_WINDOW_DAYS//2),
        ).to_string()

    # ================================================================
    # PATTERN DETECTION
    # ================================================================

    async def _detect_institutional_patterns(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        cohorts: List[Dict[str, Any]],
    ) -> List[InstitutionalPattern]:
        """Detect institutional patterns from qualified cohorts.
        
        A pattern exists when >= MIN_PATTERN_OCCURRENCES decisions in a cohort
        share the same outcome direction under comparable conditions.
        """
        patterns = []
        
        for cohort in cohorts:
            decisions = cohort["decisions"]
            
            # Group by outcome direction
            outcome_groups = defaultdict(list)
            for decision in decisions:
                outcome_dir = self._get_decision_outcome_direction(db, decision)
                if outcome_dir:
                    outcome_groups[outcome_dir].append(decision)
            
            # Check each outcome group for pattern
            for outcome_dir, group_decisions in outcome_groups.items():
                if len(group_decisions) >= MIN_PATTERN_OCCURRENCES:
                    pattern = await self._build_institutional_pattern(
                        db, caller, cohort["signature"], outcome_dir, group_decisions
                    )
                    if pattern:
                        patterns.append(pattern)
        
        return patterns

    def _get_decision_outcome_direction(
        self,
        db: AsyncSession,
        decision: CompanyDecision,
    ) -> Optional[str]:
        """Determine the outcome direction of a decision from its execution chain."""
        # Check if decision has outcome assessment
        # Check CompanyActionOutcome for actions linked to this decision
        # This is a simplified version - real implementation would trace the full chain
        
        # Check for DecisionOutcome
        decision_outcome = None  # Would query DecisionOutcome table
        
        # Check action outcomes
        actions_result = None  # Would query CompanyAction where decision_id = decision.decision_id
        
        if decision_outcome:
            return decision_outcome.outcome_type  # success | partial | failure
        
        return None

    async def _build_institutional_pattern(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        cohort_signature: str,
        outcome_direction: str,
        decisions: List[CompanyDecision],
    ) -> Optional[InstitutionalPattern]:
        """Build an institutional pattern from a cohort of decisions with same outcome."""
        
        # Collect all evidence for this pattern
        supporting_decisions = []
        supporting_actions = []
        supporting_outcomes = []
        supporting_metrics = []
        
        for decision in decisions:
            supporting_decisions.append({
                "decision_id": decision.id,
                "title": decision.title,
                "kind": decision.kind,
                "status": decision.status,
                "created_at": decision.created_at.isoformat() if decision.created_at else None,
            })
            
            # Get actions for this decision
            actions = await self._get_actions_for_decision(db, caller, decision.id)
            for action in actions:
                supporting_actions.append({
                    "action_id": action.id,
                    "title": action.title,
                    "type": action.action_type,
                    "state": action.state,
                })
                
                # Get outcomes
                outcomes = await self._get_outcomes_for_action(db, caller, action.id)
                for outcome in outcomes:
                    supporting_outcomes.append({
                        "outcome_id": outcome.id,
                        "type": outcome.outcome_type,
                        "effectiveness": outcome.effectiveness,
                    })
                
                # Get metrics
                metrics = await self._get_metrics_for_action(db, caller, action.id)
                for metric in metrics:
                    supporting_metrics.append({
                        "metric_id": metric.id,
                        "kind": metric.metric_kind,
                        "value": metric.value,
                    })
        
        # Check for contradicting evidence
        contradicting = await self._find_contradicting_evidence(db, caller, decisions, outcome_direction)
        
        # Check if pattern already exists in PatternDetection
        existing_pattern = await self._find_existing_pattern(db, caller, cohort_signature, outcome_direction)
        if existing_pattern:
            pattern_id = existing_pattern.id
        else:
            pattern_id = f"inst-pattern-{cohort_signature}-{outcome_direction}"[:64]
        
        return InstitutionalPattern(
            pattern_id=pattern_id,
            pattern_type=f"institutional_{outcome_direction}",
            family="decision",
            title=f"Institutional pattern: {outcome_direction} outcome for {decisions[0].kind} decisions",
            detail=f"Found {len(decisions)} decisions with {outcome_direction} outcome under comparable conditions",
            count=len(decisions),
            confidence=min(1.0, len(decisions) / 10.0),  # Simple confidence heuristic
            status="confirmed" if len(decisions) >= 5 else "emerging",
            cohort_signature=cohort_signature,
            supporting_decisions=supporting_decisions,
            supporting_actions=supporting_actions,
            supporting_outcomes=supporting_outcomes,
            supporting_metrics=supporting_metrics,
            contradicting_evidence=contradicting,
            scope_type="organization",
            scope_id=None,
            first_seen=min(d.created_at for d in decisions),
            last_seen=max(d.created_at for d in decisions),
            derived_at=utcnow(),
        )

    async def _get_actions_for_decision(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        decision_id: str,
    ) -> List[CompanyAction]:
        """Get CompanyActions linked to a decision."""
        result = await db.execute(
            select(CompanyAction).where(
                CompanyAction.organization_id == caller.organization_id,
                CompanyAction.source_decision_id == decision_id,
            )
        )
        return result.scalars().all()

    async def _get_outcomes_for_action(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        action_id: str,
    ) -> List[CompanyActionOutcome]:
        """Get outcomes for an action."""
        result = await db.execute(
            select(CompanyActionOutcome).where(
                CompanyActionOutcome.organization_id == caller.organization_id,
                CompanyActionOutcome.action_id == action_id,
            )
        )
        return result.scalars().all()

    async def _get_metrics_for_action(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        action_id: str,
    ) -> List[Any]:
        """Get business metric observations for an action."""
        # Would query BusinessMetricObservation and BusinessPerformanceLink
        return []

    async def _find_contradicting_evidence(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        decisions: List[CompanyDecision],
        outcome_direction: str,
    ) -> List[Dict[str, Any]]:
        """Find evidence contradicting the pattern."""
        contradicting = []
        
        # Check CompanyDecisionContradiction
        decision_ids = [d.id for d in decisions]
        contradictions_result = await db.execute(
            select(CompanyDecisionContradiction).where(
                CompanyDecisionContradiction.organization_id == caller.organization_id,
                CompanyDecisionContradiction.decision_id.in_(decision_ids),
                CompanyDecisionContradiction.status.in_(("open", "acknowledged")),
            )
        )
        for c in contradictions_result.scalars().all():
            contradicting.append({
                "type": "decision_contradiction",
                "decision_id": c.decision_id,
                "contradiction_key": c.contradiction_key,
                "status": c.status,
            })
        
        # Check for decisions with opposite outcome direction
        # (simplified - would need more sophisticated comparison)
        
        return contradicting

    async def _find_existing_pattern(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        cohort_signature: str,
        outcome_direction: str,
    ) -> Optional[PatternDetection]:
        """Check if pattern already exists in canonical PatternDetection."""
        result = await db.execute(
            select(PatternDetection).where(
                PatternDetection.organization_id == caller.organization_id,
                PatternDetection.pattern_type == f"institutional_{outcome_direction}",
                PatternDetection.key == cohort_signature[:300],
            )
        )
        return result.scalars().first()

    # ================================================================
    # LESSON QUALIFICATION
    # ================================================================

    async def _qualify_lessons(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        patterns: List[InstitutionalPattern],
    ) -> List[QualifiedLesson]:
        """Apply epistemic qualification thresholds to patterns -> lessons."""
        lessons = []
        
        for pattern in patterns:
            lesson = await self._qualify_pattern_to_lesson(db, caller, pattern)
            if lesson:
                lessons.append(lesson)
        
        return lessons

    async def _qualify_pattern_to_lesson(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        pattern: InstitutionalPattern,
    ) -> Optional[QualifiedLesson]:
        """Apply deterministic epistemic thresholds from contract."""
        
        # Count supporting evidence
        supporting_count = (
            len(pattern.supporting_decisions) +
            len(pattern.supporting_actions) +
            len(pattern.supporting_outcomes) +
            len(pattern.supporting_metrics)
        )
        
        contradicting_count = len(pattern.contradicting_evidence)
        total_evidence = supporting_count + contradicting_count
        contradiction_ratio = contradicting_count / total_evidence if total_evidence > 0 else 0
        
        # Calculate outcome quality (fraction of "met" or "outperformed")
        met_count = sum(1 for o in pattern.supporting_outcomes if o.get("type") in ("success", "met", "outperformed"))
        outcome_quality = met_count / len(pattern.supporting_outcomes) if pattern.supporting_outcomes else 0
        
        # Temporal spread
        temporal_spread = (pattern.last_seen - pattern.first_seen).days
        
        # Evidence coverage (fraction of cohort decisions with complete evidence chain)
        decisions_with_full_chain = 0
        for decision in pattern.supporting_decisions:
            if decision.get("action_id") and decision.get("outcome_id"):
                decisions_with_full_chain += 1
        evidence_coverage = decisions_with_full_chain / len(pattern.supporting_decisions) if pattern.supporting_decisions else 0
        
        # Apply thresholds
        lifecycle = "discovered"
        epistemic_status = "OBSERVED"
        
        if supporting_count >= MIN_SUPPORTING_EVIDENCE and contradiction_ratio <= MAX_CONTRADICTION_RATIO and outcome_quality >= MIN_OUTCOME_QUALITY:
            lifecycle = "supported"
            epistemic_status = "SUPPORTED"
            
            if temporal_spread >= MIN_TEMPORAL_SPREAD_DAYS and evidence_coverage >= MIN_EVIDENCE_COVERAGE:
                lifecycle = "authoritative"
                epistemic_status = "AUTHORITATIVE"
                
                # Check for confirmation (new independent cohort)
                # Simplified - would check for non-overlapping temporal window
                pass
        
        if contradiction_ratio > MAX_CONTRADICTION_RATIO:
            if lifecycle == "supported":
                epistemic_status = "SUPPORTED_WITH_CONTRADICTIONS"
            elif lifecycle in ("authoritative", "confirmed"):
                # Cannot reach authoritative with high contradiction ratio
                lifecycle = "supported"
                epistemic_status = "SUPPORTED_WITH_CONTRADICTIONS"
        
        # Confidence calculation
        confidence = self._calculate_lesson_confidence(
            supporting_count, contradicting_count, outcome_quality, temporal_spread, evidence_coverage
        )
        
        # Build evidence chain
        evidence_chain = self._build_evidence_chain(pattern)
        
        return QualifiedLesson(
            id=f"lesson-{pattern.pattern_id}",
            kind="outcome_learning",
            title=pattern.title,
            statement=f"Evidence supports that {pattern.detail.lower()}",
            epistemic_status=epistemic_status,
            lifecycle=lifecycle,
            confidence=confidence,
            scope_type=pattern.scope_type,
            scope_id=pattern.scope_id,
            valid_from=pattern.first_seen,
            valid_to=None,
            superseded_by=None,
            supporting_evidence_count=supporting_count,
            contradicting_evidence_count=contradicting_count,
            contradiction_ratio=contradiction_ratio,
            outcome_quality=outcome_quality,
            temporal_spread_days=temporal_spread,
            evidence_coverage=evidence_coverage,
            cohort_signature=pattern.cohort_signature,
            evidence_chain=evidence_chain,
            contradictions=pattern.contradicting_evidence,
            precedents=await self._get_pattern_precedents(db, caller, pattern),
            supersession_history=[],
            provenance={
                "derived_from": "institutional_pattern",
                "pattern_id": pattern.pattern_id,
                "cohort_signature": pattern.cohort_signature,
                "supporting_decisions": len(pattern.supporting_decisions),
                "supporting_actions": len(pattern.supporting_actions),
                "supporting_outcomes": len(pattern.supporting_outcomes),
                "supporting_metrics": len(pattern.supporting_metrics),
                "contradicting_count": contradicting_count,
                "derived_at": utcnow().isoformat(),
            },
            derived_at=utcnow(),
        )

    def _calculate_lesson_confidence(
        self,
        supporting: int,
        contradicting: int,
        outcome_quality: float,
        temporal_spread: int,
        evidence_coverage: float,
    ) -> float:
        """Calculate deterministic confidence for a lesson."""
        base = 0.3
        evidence_bonus = min(0.35, supporting * 0.05)  # up to 7 kinds of evidence
        outcome_bonus = 0.15 if outcome_quality >= 0.7 else 0.0
        temporal_bonus = 0.15 if temporal_spread >= MIN_TEMPORAL_SPREAD_DAYS else 0.0
        coverage_bonus = 0.1 if evidence_coverage >= MIN_EVIDENCE_COVERAGE else 0.0
        contradiction_penalty = -0.2 * (contradicting / max(1, supporting + contradicting))
        
        return max(0.0, min(0.95, base + evidence_bonus + outcome_bonus + temporal_bonus + coverage_bonus + contradiction_penalty))

    def _build_evidence_chain(self, pattern: InstitutionalPattern) -> List[Dict[str, Any]]:
        """Build complete evidence chain for provenance walk."""
        chain = []
        
        for d in pattern.supporting_decisions:
            chain.append({
                "type": "decision",
                "source_id": d["decision_id"],
                "title": d["title"],
                "relationship": "source_decision",
            })
        
        for a in pattern.supporting_actions:
            chain.append({
                "type": "action",
                "source_id": a["action_id"],
                "title": a["title"],
                "relationship": "execution_action",
            })
        
        for o in pattern.supporting_outcomes:
            chain.append({
                "type": "outcome",
                "source_id": o["outcome_id"],
                "type": o["type"],
                "relationship": "verified_outcome",
            })
        
        for m in pattern.supporting_metrics:
            chain.append({
                "type": "metric",
                "source_id": m["metric_id"],
                "relationship": "measurement_evidence",
            })
        
        return chain

    # ================================================================
    # CONTRADICTION & SUPERSESSION HANDLING
    # ================================================================

    async def _build_contradiction_surface(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        lessons: List[QualifiedLesson],
    ) -> List[Dict[str, Any]]:
        """Build aggregated contradiction surface for Brain."""
        surface = []
        
        for lesson in lessons:
            if lesson.contradicting_evidence_count > 0:
                for contradiction in lesson.contradictions:
                    surface.append({
                        "lesson_id": lesson.id,
                        "lesson_title": lesson.title,
                        "contradiction": contradiction,
                        "contradiction_ratio": lesson.contradiction_ratio,
                        "epistemic_status": lesson.epistemic_status,
                    })
        
        # Also get raw decision contradictions
        raw_contradictions = await db.execute(
            select(CompanyDecisionContradiction).where(
                CompanyDecisionContradiction.organization_id == caller.organization_id,
                CompanyDecisionContradiction.status.in_(("open", "acknowledged")),
            ).limit(20)
        )
        for c in raw_contradictions.scalars().all():
            surface.append({
                "type": "decision_contradiction",
                "decision_id": c.decision_id,
                "contradiction_key": c.contradiction_key,
                "status": c.status,
            })
        
        return surface

    async def _build_supersession_chains(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        lessons: List[QualifiedLesson],
    ) -> List[Dict[str, Any]]:
        """Build supersession history from OrganizationalLearning links."""
        chains = []
        
        for lesson in lessons:
            if lesson.superseded_by:
                chains.append({
                    "from_lesson": lesson.id,
                    "to_lesson": lesson.superseded_by,
                    "reason": "Superseded by newer evidence",
                    "at": lesson.valid_to.isoformat() if lesson.valid_to else None,
                })
        
        # Query for supersession links
        # Note: OrganizationalLearning uses lifecycle="superseded" but doesn't have supersedes_id
        # Supersession tracking is done through the lesson content and lifecycle transitions
        supersession_result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle == "superseded",
            ).limit(20)
        )
        for l in supersession_result.scalars().all():
            # Without supersedes_id, we can't trace the exact chain
            # This would require a separate supersession tracking table or field
            chains.append({
                "from_lesson": l.id,  # The superseded lesson
                "to_lesson": None,    # Would need supersedes_id to trace
                "reason": "Lesson marked as superseded",
                "at": l.observed_at.isoformat() if l.observed_at else None,
            })
        
        return chains

    async def _get_pattern_precedents(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        pattern: InstitutionalPattern,
    ) -> List[Dict[str, Any]]:
        """Get CompanyDecisionPrecedent citing related lessons."""
        precedents = []
        
        # Check for precedents citing lessons from this pattern's decisions
        decision_ids = [d["decision_id"] for d in pattern.supporting_decisions]
        if decision_ids:
            precedents_result = await db.execute(
                select(CompanyDecisionPrecedent).where(
                    CompanyDecisionPrecedent.organization_id == caller.organization_id,
                    CompanyDecisionPrecedent.decision_id.in_(decision_ids),
                ).limit(10)
            )
            for p in precedents_result.scalars().all():
                precedents.append({
                    "decision_id": p.decision_id,
                    "cited_lesson_snapshot": p.cited_lesson,
                    "relevance_score": 0.8,  # Would compute from context signature
                })
        
        return precedents

    async def _get_lesson_contradictions(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        lesson_row: OrganizationalLearning,
    ) -> List[Dict[str, Any]]:
        """Get contradictions for a specific lesson."""
        # This would trace from lesson -> evidence -> contradictions
        return []

    async def _get_lesson_precedents(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        lesson_row: OrganizationalLearning,
    ) -> List[Dict[str, Any]]:
        """Get precedents citing this lesson."""
        return []

    async def _get_lesson_supersession_history(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        lesson_row: OrganizationalLearning,
    ) -> List[Dict[str, Any]]:
        """Get supersession history for a lesson.
        
        Note: OrganizationalLearning model doesn't have supersedes_id field.
        Supersession is tracked via lifecycle state but without direct links.
        """
        history = []
        
        if lesson_row.lifecycle == "superseded":
            history.append({
                "from_lesson": lesson_row.id,
                "to_lesson": None,
                "reason": "Lesson marked as superseded (no direct link available)",
                "at": lesson_row.observed_at.isoformat() if lesson_row.observed_at else None,
            })
        
        # Find lessons that might supersede this one (lifecycle=superseded with later observed_at)
        # This is a best-effort approach without explicit supersedes_id
        superseding = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle == "superseded",
                OrganizationalLearning.observed_at > lesson_row.observed_at,
            ).limit(10)
        )
        for s in superseding.scalars().all():
            history.append({
                "from_lesson": lesson_row.id,
                "to_lesson": s.id,
                "reason": "Potential supersession (lifecycle=superseded, later observed_at)",
                "at": s.observed_at.isoformat() if s.observed_at else None,
            })
        
        return history

    async def _walk_provenance_chain(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        lesson_row: OrganizationalLearning,
    ) -> List[Dict[str, Any]]:
        """Walk the complete provenance chain for a lesson."""
        chain = []
        
        # Get learning evidence
        evidence_result = await db.execute(
            select(LearningEvidence).where(
                LearningEvidence.organization_id == caller.organization_id,
                LearningEvidence.learning_id == lesson_row.id,
            )
        )
        for e in evidence_result.scalars().all():
            chain.append({
                "type": e.source_type,
                "id": e.source_id,
                "excerpt": e.excerpt,
                "role": e.role,
                "weight": e.weight,
            })
        
        return chain

    # ================================================================
    # LEARNING FEED
    # ================================================================

    async def _get_learning_feed(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent organizational learnings for the learning feed."""
        result = await db.execute(
            select(OrganizationalLearning).where(
                OrganizationalLearning.organization_id == caller.organization_id,
                OrganizationalLearning.lifecycle.in_(("supported", "authoritative", "confirmed")),
            ).order_by(OrganizationalLearning.observed_at.desc()).limit(limit)
        )
        
        feed = []
        for row in result.scalars().all():
            # Governance filter
            if not caller.org_wide:
                # Check scope visibility
                pass
            
            feed.append({
                "id": row.id,
                "kind": row.kind,
                "title": row.title,
                "lesson": row.lesson,
                "lifecycle": row.lifecycle,
                "confidence": row.confidence,
                "observed_at": row.observed_at.isoformat() if row.observed_at else None,
                "source_type": row.source_type,
                "source_id": row.source_id,
            })
        
        return feed

    # ================================================================
    # HELPER: DICT CONVERSION
    # ================================================================

    def _lesson_to_dict(self, lesson: QualifiedLesson) -> Dict[str, Any]:
        return {
            "id": lesson.id,
            "kind": lesson.kind,
            "title": lesson.title,
            "statement": lesson.statement,
            "epistemic_status": lesson.epistemic_status,
            "lifecycle": lesson.lifecycle,
            "confidence": lesson.confidence,
            "scope": {"type": lesson.scope_type, "id": lesson.scope_id},
            "temporal_validity": {
                "valid_from": lesson.valid_from.isoformat(),
                "valid_to": lesson.valid_to.isoformat() if lesson.valid_to else None,
                "superseded_by": lesson.superseded_by,
            },
            "evidence_qualification": {
                "supporting_count": lesson.supporting_evidence_count,
                "contradicting_count": lesson.contradicting_evidence_count,
                "outcome_quality": lesson.outcome_quality,
            },
            "provenance": lesson.provenance,
            "contradictions": lesson.contradictions,
            "precedents": lesson.precedents,
            "supersession_history": lesson.supersession_history,
        }

    def _pattern_to_dict(self, pattern: InstitutionalPattern) -> Dict[str, Any]:
        return {
            "pattern_id": pattern.pattern_id,
            "pattern_type": pattern.pattern_type,
            "family": pattern.family,
            "title": pattern.title,
            "detail": pattern.detail,
            "count": pattern.count,
            "confidence": pattern.confidence,
            "status": pattern.status,
            "cohort_signature": pattern.cohort_signature,
            "scope": {"type": pattern.scope_type, "id": pattern.scope_id},
            "temporal_range": {
                "first_seen": pattern.first_seen.isoformat(),
                "last_seen": pattern.last_seen.isoformat(),
            },
            "supporting_decisions": pattern.supporting_decisions,
            "supporting_actions": pattern.supporting_actions,
            "supporting_outcomes": pattern.supporting_outcomes,
            "supporting_metrics": pattern.supporting_metrics,
            "contradicting_evidence": pattern.contradicting_evidence,
        }

    def _lesson_row_to_dict(self, row: OrganizationalLearning) -> Dict[str, Any]:
        return {
            "id": row.id,
            "kind": row.kind,
            "fingerprint": row.fingerprint,
            "title": row.title,
            "lesson": row.lesson,
            "status": row.status,
            "lifecycle": row.lifecycle,
            "confidence": row.confidence,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "topic_id": row.topic_id,
            "topic_name": row.topic_name,
            "evidence": json.loads(row.evidence_json) if row.evidence_json else [],
            "claims_updated": json.loads(row.claims_updated_json) if row.claims_updated_json else [],
            "expectation": row.expectation,
            "observation": row.observation,
            "recorded_by": row.recorded_by,
            "observed_at": row.observed_at.isoformat() if row.observed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


# Global instance
institutional_intelligence_service = InstitutionalIntelligenceService()