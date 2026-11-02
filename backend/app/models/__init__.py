"""
Models package exports - Minimal exports to avoid circular imports.

Only base classes and core utilities are exported here.
All model classes should be imported directly from their respective modules:
    from app.models.organization import Organization
    from app.models.user import User
    etc.
"""

from app.models.base import Base, TimestampMixin, gen_uuid, utcnow

# Export commonly used models for convenience
from app.models.execution_strategy import (
    CompanyGoal,
    CompanyInitiative,
    CompanyObjective,
    StrategicHistory,
    StrategicLink,
    StrategicOutcome,
    StrategicSnapshot,
    CompanyAuthorization,
    CompanyCommitment,
    COMMITMENT_STATES,
    COMMITMENT_TYPES,
    AUTHORIZATION_TYPES,
    AUTHORIZATION_STATES,
    ObjectiveOutcome,
    ObjectiveOutcomeAssessment,
    ObjectiveContradiction,
    OUTCOME_STATES,
    ASSESSMENT_STATES,
    MEASUREMENT_QUALITY,
    SUPERSESSION_REASON,
    ASSESSMENT_CONFIDENCE,
    ALIGNMENT_TYPES,
    ALIGNMENT_STATES,
    ALIGNMENT_STRENGTH,
    ALIGNMENT_GAP_TYPES,
    ALIGNMENT_GAP_SEVERITY,
    CONTRIBUTION_LEVELS,
    PLANNING_CONTEXT_SECTIONS,
    PLANNING_CONTEXT_EPISTEMIC_STATUS,
    PLANNING_CONTEXT_CONFIDENCE,
    STATE_TRANSITION_TRIGGERS,
    STATE_TRANSITION_KINDS,
    DECISION_INTELLIGENCE_TYPES,
    DECISION_INTELLIGENCE_STATES,
    DECISION_ALTERNATIVE_STATES,
    CONSEQUENCE_TYPES,
    RISK_ASSESSMENT_LEVELS,
    EVIDENCE_QUALITY_LEVELS,
    PRECEDENT_RELEVANCE_LEVELS,
    _compute_fingerprint,
    CompanyPlanningContext,
    CompanyStateTransition,
    PlanningContextProvenance,
    AdaptivePlanningContext,
    AttentionSignal,
    ReplanningProposal,
    DecisionContext,
    AdaptivePlanningTransition,
    DecisionIntelligenceContext,
    DecisionAlternative,
    DecisionConsequence,
    DecisionPrecedentLink,
    DecisionEvidence,
    DecisionRiskAssessment,
    DecisionIntelligenceTransition,
    DECISION_INTELLIGENCE_TYPES,
    DECISION_INTELLIGENCE_STATES,
    DECISION_ALTERNATIVE_STATES,
    CONSEQUENCE_TYPES,
    RISK_ASSESSMENT_LEVELS,
    EVIDENCE_QUALITY_LEVELS,
    PRECEDENT_RELEVANCE_LEVELS,
    _compute_fingerprint,
    CompanyPlanningContext,
    CompanyStateTransition,
    PlanningContextProvenance,
    AdaptivePlanningContext,
    AttentionSignal,
    ReplanningProposal,
    DecisionContext,
    AdaptivePlanningTransition,
    DecisionIntelligenceContext,
    DecisionAlternative,
    DecisionConsequence,
    DecisionPrecedentLink,
    DecisionEvidence,
    DecisionRiskAssessment,
    DecisionIntelligenceTransition,
    DECISION_INTELLIGENCE_TYPES,
    DECISION_INTELLIGENCE_STATES,
    DECISION_ALTERNATIVE_STATES,
    CONSEQUENCE_TYPES,
    RISK_ASSESSMENT_LEVELS,
    EVIDENCE_QUALITY_LEVELS,
    PRECEDENT_RELEVANCE_LEVELS,
)

# Resource Allocation models
from app.models.resource_allocation_intelligence import (
    AllocationDemand,
    CapacityAllocation,
    CapacityHistory,
    CapacitySnapshot,
)

from app.models.role import Role, Permission, RolePermission, UserRoleModel

__all__ = [
    "Base",
    "TimestampMixin",
    "gen_uuid",
    "utcnow",
    "Role",
    "Permission",
    "RolePermission",
    "UserRoleModel",
]