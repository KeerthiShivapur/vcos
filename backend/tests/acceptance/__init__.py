"""Universal Acceptance Matrix Test Infrastructure.

This package provides the test infrastructure for validating VCOS universality
across company types, scales, structures, industries, geographies, and operating models.
"""

from .dimensions import (
    DimensionId,
    EquivalenceClass,
    Dimension,
    ALL_DIMENSIONS,
    DIMENSIONS_BY_ID,
    get_dimension,
    get_all_equivalence_classes,
    get_representative_profiles,
    CANONICAL_INVARIANTS,
)

from .scenario_builder import (
    ScenarioType,
    ScenarioPhase,
    ScenarioStep,
    UniversalScenario,
    CompanyProfileBuilder,
    UniversalScenarioBuilder,
    create_scenario_builder,
)

from .matrix_runner import (
    ScenarioStatus,
    InvariantStatus,
    StepResult,
    InvariantResult,
    ScenarioResult,
    ProfileResult,
    AcceptanceMatrixResult,
    ActionRegistry,
    InvariantVerifier,
    AcceptanceMatrixRunner,
    run_acceptance_matrix,
)

from .universal_evidence import (
    UniversalityEvidence,
    ScaleMatrixEvidence,
    OrgStructureEvidence,
    IndustryEvidence,
    GeographyEvidence,
    MultiCompanyEvidence,
    IdentityEvidence,
    WorkEvidence,
    GovernanceEvidence,
    IntegrationEvidence,
    CompanyBrainEvidence,
    MemoryEvidence,
    PredictionEvidence,
    CounterfactualEvidence,
    AutonomyEvidence,
    ContinuityEvidence,
    MigrationEvidence,
    MAEvidence,
    FailureUniversalityEvidence,
    LongitudinalUniversalityEvidence,
    DeploymentDREvidence,
    SecurityEvidence,
    APIEvidence,
    UniversalAcceptanceEvidence,
    create_universal_acceptance_evidence,
)

__all__ = [
    # Dimensions
    "DimensionId",
    "EquivalenceClass", 
    "Dimension",
    "ALL_DIMENSIONS",
    "DIMENSIONS_BY_ID",
    "get_dimension",
    "get_all_equivalence_classes",
    "get_representative_profiles",
    "CANONICAL_INVARIANTS",
    
    # Scenario Builder
    "ScenarioType",
    "ScenarioPhase",
    "ScenarioStep",
    "UniversalScenario",
    "CompanyProfileBuilder",
    "UniversalScenarioBuilder",
    "create_scenario_builder",
    
    # Matrix Runner
    "ScenarioStatus",
    "InvariantStatus",
    "StepResult",
    "InvariantResult",
    "ScenarioResult",
    "ProfileResult",
    "AcceptanceMatrixResult",
    "ActionRegistry",
    "InvariantVerifier",
    "AcceptanceMatrixRunner",
    "run_acceptance_matrix",
    
    # Universal Evidence
    "UniversalityEvidence",
    "ScaleMatrixEvidence",
    "OrgStructureEvidence",
    "IndustryEvidence",
    "GeographyEvidence",
    "MultiCompanyEvidence",
    "IdentityEvidence",
    "WorkEvidence",
    "GovernanceEvidence",
    "IntegrationEvidence",
    "CompanyBrainEvidence",
    "MemoryEvidence",
    "PredictionEvidence",
    "CounterfactualEvidence",
    "AutonomyEvidence",
    "ContinuityEvidence",
    "MigrationEvidence",
    "MAEvidence",
    "FailureUniversalityEvidence",
    "LongitudinalUniversalityEvidence",
    "DeploymentDREvidence",
    "SecurityEvidence",
    "APIEvidence",
    "UniversalAcceptanceEvidence",
    "create_universal_acceptance_evidence",
]