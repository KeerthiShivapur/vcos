"""Universal Acceptance Matrix Dimensions.

Defines the 26 dimensions (A-Z) and their representative equivalence classes
for universal acceptance testing. This is TEST INFRASTRUCTURE - NOT a business model.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


class DimensionId(str, Enum):
    """26 Universal Acceptance Dimensions."""
    A_SCALE = "A"
    B_ORG_STRUCTURE = "B"
    C_INDUSTRY = "C"
    D_GEOGRAPHY = "D"
    E_LEGAL_ENTITY = "E"
    F_MULTI_COMPANY = "F"
    G_LOCALIZATION = "G"
    H_IDENTITY = "H"
    I_GOVERNANCE = "I"
    J_WORK = "J"
    K_FINANCE = "K"
    L_PEOPLE = "L"
    M_COMMUNICATION = "M"
    N_KNOWLEDGE = "N"
    O_INTEGRATIONS = "O"
    P_COMPANY_BRAIN = "P"
    Q_MEMORY = "Q"
    R_PREDICTION = "R"
    S_COUNTERFACTUAL = "S"
    T_GOVERNED_AUTONOMY = "T"
    U_COMPANY_CONTINUITY = "U"
    V_MIGRATION = "V"
    W_MA = "W"
    X_SECURITY = "X"
    Y_DISASTER_RECOVERY = "Y"
    Z_ACCESSIBILITY_API = "Z"


@dataclass(frozen=True)
class EquivalenceClass:
    """A representative equivalence class within a dimension."""
    id: str
    name: str
    description: str
    properties: Dict[str, Any] = field(default_factory=dict)
    representative_scale: Optional[str] = None
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Dimension:
    """A universal acceptance dimension with equivalence classes."""
    id: DimensionId
    name: str
    description: str
    equivalence_classes: List[EquivalenceClass]
    canonical_invariants: List[str] = field(default_factory=list)


# ============================================================
# DIMENSION A: COMPANY SCALE
# ============================================================
SCALE_CLASSES = [
    EquivalenceClass(
        id="startup_5",
        name="Startup (5 employees)",
        description="5-person early-stage company",
        properties={"employee_count": 5, "departments": 1, "teams": 1},
        representative_scale="5",
        constraints={"max_departments": 2, "max_teams": 3},
    ),
    EquivalenceClass(
        id="small_50",
        name="Small Company (50 employees)",
        description="50-person growing company",
        properties={"employee_count": 50, "departments": 5, "teams": 10},
        representative_scale="50",
        constraints={"max_departments": 10, "max_teams": 20},
    ),
    EquivalenceClass(
        id="medium_500",
        name="Medium Company (500 employees)",
        description="500-person established company",
        properties={"employee_count": 500, "departments": 15, "teams": 50},
        representative_scale="500",
        constraints={"max_departments": 30, "max_teams": 100},
    ),
    EquivalenceClass(
        id="large_5k",
        name="Large Company (5,000 employees)",
        description="5,000-person enterprise",
        properties={"employee_count": 5000, "departments": 50, "teams": 200},
        representative_scale="5k",
        constraints={"max_departments": 100, "max_teams": 500},
    ),
    EquivalenceClass(
        id="enterprise_50k",
        name="Enterprise (50,000 employees)",
        description="50,000-person enterprise",
        properties={"employee_count": 50000, "departments": 200, "teams": 1000},
        representative_scale="50k",
        constraints={"max_departments": 500, "max_teams": 2000},
    ),
    EquivalenceClass(
        id="mega_500k",
        name="Mega Enterprise (500,000+ employees)",
        description="500,000+ person global enterprise",
        properties={"employee_count": 500000, "departments": 1000, "teams": 5000},
        representative_scale="500k+",
        constraints={"max_departments": 2000, "max_teams": 10000},
    ),
]

DIMENSION_A = Dimension(
    id=DimensionId.A_SCALE,
    name="Company Scale",
    description="Company size from 5 to 500,000+ employees",
    equivalence_classes=SCALE_CLASSES,
    canonical_invariants=[
        "Identity model remains stable at all scales",
        "Governance passes through canonical mutation",
        "Temporal truth is reconstructable",
        "Tenant isolation holds",
        "Company Brain is projection over canonical reality",
    ],
)


# ============================================================
# DIMENSION B: ORGANIZATIONAL STRUCTURE
# ============================================================
ORG_STRUCTURE_CLASSES = [
    EquivalenceClass(
        id="hierarchical",
        name="Hierarchical",
        description="Traditional top-down hierarchy: CEO → VP → Director → Manager → Employee",
        properties={
            "structure_type": "hierarchical",
            "levels": 5,
            "span_of_control": 7,
            "reporting_lines": "single",
        },
    ),
    EquivalenceClass(
        id="flat",
        name="Flat",
        description="Minimal hierarchy: Founder → Team Leads → Contributors",
        properties={
            "structure_type": "flat",
            "levels": 3,
            "span_of_control": 15,
            "reporting_lines": "single",
        },
    ),
    EquivalenceClass(
        id="matrix",
        name="Matrix",
        description="Dual reporting: functional manager + project manager",
        properties={
            "structure_type": "matrix",
            "levels": 4,
            "span_of_control": 8,
            "reporting_lines": "dual",
            "dimensions": ["functional", "project"],
        },
    ),
    EquivalenceClass(
        id="functional",
        name="Functional",
        description="Organized by function: Engineering, Sales, Marketing, Finance, HR",
        properties={
            "structure_type": "functional",
            "levels": 4,
            "functions": ["engineering", "sales", "marketing", "finance", "hr", "operations"],
        },
    ),
    EquivalenceClass(
        id="divisional",
        name="Divisional",
        description="Organized by product/division: Cloud, AI, Platform, Services",
        properties={
            "structure_type": "divisional",
            "divisions": ["cloud", "ai", "platform", "services"],
            "levels": 4,
        },
    ),
    EquivalenceClass(
        id="geographic",
        name="Geographic",
        description="Organized by region: Americas, EMEA, APAC",
        properties={
            "structure_type": "geographic",
            "regions": ["americas", "emea", "apac"],
            "levels": 4,
        },
    ),
    EquivalenceClass(
        id="product",
        name="Product",
        description="Organized by product line: Product A, Product B, Platform",
        properties={
            "structure_type": "product",
            "products": ["product_a", "product_b", "platform"],
            "levels": 4,
        },
    ),
    EquivalenceClass(
        id="hybrid",
        name="Hybrid",
        description="Combination: functional at top, divisional below",
        properties={
            "structure_type": "hybrid",
            "top_level": "functional",
            "lower_level": "divisional",
            "levels": 5,
        },
    ),
    EquivalenceClass(
        id="project_based",
        name="Project-Based",
        description="Temporary project structures over stable functional base",
        properties={
            "structure_type": "project_based",
            "base": "functional",
            "projects": ["project_alpha", "project_beta", "project_gamma"],
            "project_duration_months": 6,
        },
    ),
    EquivalenceClass(
        id="federated",
        name="Federated",
        description="Autonomous units with shared services: Business Unit A, B, C + Shared Services",
        properties={
            "structure_type": "federated",
            "business_units": ["bu_a", "bu_b", "bu_c"],
            "shared_services": ["hr", "finance", "it", "legal"],
            "autonomy_level": "high",
        },
    ),
    EquivalenceClass(
        id="holding_company",
        name="Holding Company",
        description="Parent with independent subsidiaries",
        properties={
            "structure_type": "holding",
            "subsidiaries": ["sub_a", "sub_b", "sub_c"],
            "parent_control": "financial",
        },
    ),
    EquivalenceClass(
        id="multi_subsidiary",
        name="Multi-Subsidiary",
        description="Parent with operationally integrated subsidiaries",
        properties={
            "structure_type": "multi_subsidiary",
            "subsidiaries": ["sub_a", "sub_b", "sub_c"],
            "integration_level": "operational",
        },
    ),
    EquivalenceClass(
        id="post_acquisition",
        name="Post-Acquisition",
        description="Acquirer + acquired company in integration",
        properties={
            "structure_type": "post_acquisition",
            "acquirer": "parent",
            "acquired": "target",
            "integration_stage": "partial",
        },
    ),
    EquivalenceClass(
        id="post_merger",
        name="Post-Merger",
        description="Two companies merged into new entity",
        properties={
            "structure_type": "post_merger",
            "legacy_a": "company_a",
            "legacy_b": "company_b",
            "integration_stage": "full",
        },
    ),
]

DIMENSION_B = Dimension(
    id=DimensionId.B_ORG_STRUCTURE,
    name="Organizational Structure",
    description="14 organizational structure patterns",
    equivalence_classes=ORG_STRUCTURE_CLASSES,
    canonical_invariants=[
        "Identity model unchanged across structures",
        "Membership/role/governance uses same primitives",
        "Reporting relationships are temporal edges",
        "No structure-specific identity engines",
    ],
)


# ============================================================
# DIMENSION C: INDUSTRY
# ============================================================
INDUSTRY_CLASSES = [
    EquivalenceClass(
        id="software",
        name="Software / Technology",
        description="SaaS, platforms, developer tools",
        properties={
            "industry": "software",
            "work_types": ["project", "ticket", "objective", "continuous"],
            "key_entities": ["feature", "release", "incident", "deployment"],
            "regulatory": ["SOC2", "GDPR"],
        },
    ),
    EquivalenceClass(
        id="manufacturing",
        name="Manufacturing",
        description="Physical goods production",
        properties={
            "industry": "manufacturing",
            "work_types": ["manufacturing_process", "work_order", "quality_check", "shift"],
            "key_entities": ["bom", "work_center", "production_line", "inventory"],
            "regulatory": ["ISO9001", "OSHA"],
        },
    ),
    EquivalenceClass(
        id="healthcare",
        name="Healthcare",
        description="Hospitals, clinics, health systems",
        properties={
            "industry": "healthcare",
            "work_types": ["patient_case", "procedure", "shift", "care_plan"],
            "key_entities": ["patient", "provider", "encounter", "clinical_decision"],
            "regulatory": ["HIPAA", "HITECH", "Joint Commission"],
        },
    ),
    EquivalenceClass(
        id="financial_services",
        name="Financial Services",
        description="Banking, insurance, capital markets",
        properties={
            "industry": "financial_services",
            "work_types": ["transaction", "compliance_check", "risk_assessment", "audit"],
            "key_entities": ["account", "transaction", "portfolio", "risk_model"],
            "regulatory": ["SOX", "Basel III", "GDPR", "PCI-DSS"],
        },
    ),
    EquivalenceClass(
        id="retail",
        name="Retail",
        description="E-commerce, brick-and-mortar, omnichannel",
        properties={
            "industry": "retail",
            "work_types": ["order", "fulfillment", "inventory", "merchandising"],
            "key_entities": ["product", "store", "customer_order", "inventory_unit"],
            "regulatory": ["PCI-DSS", "GDPR", "CCPA"],
        },
    ),
    EquivalenceClass(
        id="logistics",
        name="Logistics / Supply Chain",
        description="Transportation, warehousing, freight",
        properties={
            "industry": "logistics",
            "work_types": ["shipment", "route", "warehouse_op", "customs"],
            "key_entities": ["shipment", "vehicle", "warehouse", "route"],
            "regulatory": ["DOT", "Customs", "IATA"],
        },
    ),
    EquivalenceClass(
        id="education",
        name="Education",
        description="Universities, schools, ed-tech",
        properties={
            "industry": "education",
            "work_types": ["course", "enrollment", "assessment", "research_grant"],
            "key_entities": ["student", "faculty", "course", "program"],
            "regulatory": ["FERPA", "Title IV", "Accreditation"],
        },
    ),
    EquivalenceClass(
        id="professional_services",
        name="Professional Services",
        description="Consulting, legal, accounting, agencies",
        properties={
            "industry": "professional_services",
            "work_types": ["engagement", "deliverable", "timesheet", "proposal"],
            "key_entities": ["client", "engagement", "consultant", "deliverable"],
            "regulatory": ["SOX", "GDPR", "Professional Standards"],
        },
    ),
    EquivalenceClass(
        id="agriculture",
        name="Agriculture",
        description="Farming, agribusiness, food production",
        properties={
            "industry": "agriculture",
            "work_types": ["season", "harvest", "field_op", "livestock"],
            "key_entities": ["field", "crop", "livestock", "equipment"],
            "regulatory": ["USDA", "FDA", "EPA"],
        },
    ),
    EquivalenceClass(
        id="construction",
        name="Construction",
        description="Commercial, residential, infrastructure",
        properties={
            "industry": "construction",
            "work_types": ["project", "phase", "subcontractor", "inspection"],
            "key_entities": ["project", "site", "subcontractor", "permit"],
            "regulatory": ["OSHA", "Building Codes", "Environmental"],
        },
    ),
    EquivalenceClass(
        id="media",
        name="Media / Entertainment",
        description="Content production, broadcasting, streaming",
        properties={
            "industry": "media",
            "work_types": ["production", "campaign", "distribution", "rights"],
            "key_entities": ["asset", "campaign", "rights", "audience"],
            "regulatory": ["FCC", "Copyright", "GDPR"],
        },
    ),
    EquivalenceClass(
        id="research",
        name="Research / R&D",
        description="Pharma, biotech, scientific research",
        properties={
            "industry": "research",
            "work_types": ["study", "experiment", "trial", "publication"],
            "key_entities": ["protocol", "subject", "sample", "finding"],
            "regulatory": ["FDA", "IRB", "GCP", "GDPR"],
        },
    ),
    EquivalenceClass(
        id="multinational",
        name="Multinational Enterprise",
        description="Cross-industry global conglomerate",
        properties={
            "industry": "multinational",
            "work_types": ["all"],
            "key_entities": ["subsidiary", "joint_venture", "holding"],
            "regulatory": ["Multiple jurisdictions"],
        },
    ),
]

DIMENSION_C = Dimension(
    id=DimensionId.C_INDUSTRY,
    name="Industry",
    description="12 industry verticals with different operational realities",
    equivalence_classes=INDUSTRY_CLASSES,
    canonical_invariants=[
        "Same canonical primitives compose for all industries",
        "Work/action/outcome architecture is universal",
        "Governance model is industry-agnostic",
        "Provenance tracks industry-specific sources",
    ],
)


# ============================================================
# DIMENSION D: GEOGRAPHY
# ============================================================
GEOGRAPHY_CLASSES = [
    EquivalenceClass(
        id="india",
        name="India",
        description="Single-region India operations",
        properties={
            "region": "india",
            "timezone": "Asia/Kolkata",
            "currency": "INR",
            "fiscal_year_start": "04-01",
            "languages": ["en", "hi"],
        },
    ),
    EquivalenceClass(
        id="united_states",
        name="United States",
        description="Single-region US operations",
        properties={
            "region": "us",
            "timezone": "America/New_York",
            "currency": "USD",
            "fiscal_year_start": "01-01",
            "languages": ["en"],
        },
    ),
    EquivalenceClass(
        id="europe",
        name="Europe",
        description="Single-region EU operations",
        properties={
            "region": "eu",
            "timezone": "Europe/Berlin",
            "currency": "EUR",
            "fiscal_year_start": "01-01",
            "languages": ["en", "de", "fr", "es"],
        },
    ),
    EquivalenceClass(
        id="middle_east",
        name="Middle East",
        description="GCC/MENA operations",
        properties={
            "region": "me",
            "timezone": "Asia/Dubai",
            "currency": "AED",
            "fiscal_year_start": "01-01",
            "languages": ["en", "ar"],
        },
    ),
    EquivalenceClass(
        id="asia_pacific",
        name="Asia-Pacific",
        description="APAC regional operations",
        properties={
            "region": "apac",
            "timezone": "Asia/Singapore",
            "currency": "SGD",
            "fiscal_year_start": "04-01",
            "languages": ["en", "zh", "ja"],
        },
    ),
    EquivalenceClass(
        id="multi_region",
        name="Multi-Region Enterprise",
        description="Global operations across 3+ regions",
        properties={
            "region": "global",
            "regions": ["us", "eu", "apac", "me"],
            "timezones": ["America/New_York", "Europe/London", "Asia/Singapore", "Asia/Dubai"],
            "currencies": ["USD", "EUR", "SGD", "AED"],
            "fiscal_calendars": ["calendar", "uk", "india", "custom"],
            "languages": ["en", "de", "fr", "es", "zh", "ja", "ar", "hi"],
        },
    ),
]

DIMENSION_D = Dimension(
    id=DimensionId.D_GEOGRAPHY,
    name="Geography / Localization",
    description="6 geographic configurations including multi-region",
    equivalence_classes=GEOGRAPHY_CLASSES,
    canonical_invariants=[
        "Single canonical temporal model handles all timezones",
        "Currency is provenance-tracked attribute",
        "Fiscal calendar is organizational configuration",
        "No region-specific canonical reality",
    ],
)


# ============================================================
# DIMENSION E: LEGAL / ENTITY STRUCTURE
# ============================================================
LEGAL_CLASSES = [
    EquivalenceClass(
        id="single_entity",
        name="Single Legal Entity",
        description="One legal entity, one tax ID",
        properties={"entities": 1, "structure": "single"},
    ),
    EquivalenceClass(
        id="parent_subsidiary",
        name="Parent + Subsidiaries",
        description="Parent company with wholly-owned subsidiaries",
        properties={"entities": 4, "structure": "parent_subsidiary", "ownership": "100%"},
    ),
    EquivalenceClass(
        id="joint_venture",
        name="Joint Venture",
        description="Shared ownership entity",
        properties={"entities": 3, "structure": "joint_venture", "ownership": "50/50"},
    ),
    EquivalenceClass(
        id="franchise",
        name="Franchise Network",
        description="Franchisor + franchisees",
        properties={"entities": 10, "structure": "franchise", "control": "brand_standards"},
    ),
    EquivalenceClass(
        id="partnership",
        name="Partnership / LLP",
        description="Partner-owned professional services",
        properties={"entities": 1, "structure": "partnership", "partners": 20},
    ),
    EquivalenceClass(
        id="nonprofit",
        name="Nonprofit / NGO",
        description="Tax-exempt organization",
        properties={"entities": 1, "structure": "nonprofit", "board_governed": True},
    ),
    EquivalenceClass(
        id="government",
        name="Government Agency",
        description="Public sector entity",
        properties={"entities": 1, "structure": "government", "appropriations": True},
    ),
]

DIMENSION_E = Dimension(
    id=DimensionId.E_LEGAL_ENTITY,
    name="Legal / Entity Structure",
    description="7 legal entity configurations",
    equivalence_classes=LEGAL_CLASSES,
    canonical_invariants=[
        "Legal entity is provenance-tracked attribute",
        "Governance respects legal boundaries",
        "Identity spans legal entities via canonical model",
    ],
)


# ============================================================
# DIMENSION F: MULTI-COMPANY
# ============================================================
MULTI_COMPANY_CLASSES = [
    EquivalenceClass(
        id="parent_subsidiary_2",
        name="Parent + 2 Subsidiaries",
        description="Parent company with two subsidiaries",
        properties={"parent": "parent", "subsidiaries": ["sub_a", "sub_b"]},
    ),
    EquivalenceClass(
        id="parent_subsidiary_jv",
        name="Parent + Subsidiary + JV",
        description="Parent with subsidiary and joint venture",
        properties={"parent": "parent", "subsidiaries": ["sub_a"], "joint_ventures": ["jv_1"]},
    ),
    EquivalenceClass(
        id="holding_3_subs",
        name="Holding Company + 3 Subsidiaries",
        description="Holding company with three operating subsidiaries",
        properties={"holding": "holdco", "subsidiaries": ["sub_a", "sub_b", "sub_c"]},
    ),
    EquivalenceClass(
        id="acquisition_in_progress",
        name="Acquisition in Progress",
        description="Acquirer integrating target company",
        properties={"acquirer": "parent", "target": "target", "stage": "integration"},
    ),
    EquivalenceClass(
        id="post_merger_2",
        name="Post-Merger Integration",
        description="Two companies merged into new entity",
        properties={"legacy_a": "co_a", "legacy_b": "co_b", "newco": "merged"},
    ),
    EquivalenceClass(
        id="complex_group",
        name="Complex Group (5+ entities)",
        description="Multi-layer group with mixed entity types",
        properties={"entities": 6, "structure": "mixed", "layers": 3},
    ),
]

DIMENSION_F = Dimension(
    id=DimensionId.F_MULTI_COMPANY,
    name="Multi-Company Reality",
    description="6 multi-company configurations",
    equivalence_classes=MULTI_COMPANY_CLASSES,
    canonical_invariants=[
        "Tenant isolation is absolute",
        "Cross-company queries are explicitly scoped",
        "M&A lineage preserves historical truth",
        "Governance respects entity boundaries",
    ],
)


# ============================================================
# DIMENSION G: LOCALIZATION
# ============================================================
LOCALIZATION_CLASSES = [
    EquivalenceClass(
        id="en_us_only",
        name="English US Only",
        description="Single locale English US",
        properties={"locales": ["en-US"], "rtl": False},
    ),
    EquivalenceClass(
        id="multilingual_eu",
        name="Multilingual EU",
        description="Multiple European languages",
        properties={"locales": ["en-GB", "de-DE", "fr-FR", "es-ES"], "rtl": False},
    ),
    EquivalenceClass(
        id="multilingual_global",
        name="Global Multilingual",
        description="Global languages including RTL",
        properties={"locales": ["en-US", "zh-CN", "ja-JP", "ar-SA", "hi-IN"], "rtl": True},
    ),
    EquivalenceClass(
        id="accessibility_wcag",
        name="WCAG 2.1 AA Compliant",
        description="Accessibility compliant configuration",
        properties={"accessibility": "wcag_2_1_aa", "screen_reader": True},
    ),
]

DIMENSION_G = Dimension(
    id=DimensionId.G_LOCALIZATION,
    name="Localization / Accessibility",
    description="4 localization/accessibility configurations",
    equivalence_classes=LOCALIZATION_CLASSES,
    canonical_invariants=[
        "Locale is metadata, not canonical structure",
        "Accessibility is projection concern",
        "RTL is presentation-layer only",
    ],
)


# ============================================================
# DIMENSION H: IDENTITY
# ============================================================
IDENTITY_CLASSES = [
    EquivalenceClass(
        id="single_role",
        name="Single Role per Person",
        description="One role per person, no concurrent employment",
        properties={"roles_per_person": 1, "concurrent_employment": False},
    ),
    EquivalenceClass(
        id="multi_role",
        name="Multiple Concurrent Roles",
        description="Person holds multiple roles simultaneously",
        properties={"roles_per_person": 3, "concurrent_employment": True},
    ),
    EquivalenceClass(
        id="cross_subsidiary",
        name="Cross-Subsidiary Identity",
        description="Identity spans subsidiary boundaries",
        properties={"roles_per_person": 2, "entities": 2, "shared_identity": True},
    ),
    EquivalenceClass(
        id="contractor_employee",
        name="Contractor → Employee Transition",
        description="Contractor converted to employee",
        properties={"transitions": ["contractor", "employee"], "identity_continuous": True},
    ),
    EquivalenceClass(
        id="leave_reentry",
        name="Leave and Re-entry",
        description="Person takes leave and returns",
        properties={"events": ["leave", "reentry"], "identity_preserved": True},
    ),
    EquivalenceClass(
        id="acquisition_transfer",
        name="Acquisition Identity Transfer",
        description="Identity transfers through acquisition",
        properties={"events": ["acquisition", "transfer"], "identity_continuous": True},
    ),
]

DIMENSION_H = Dimension(
    id=DimensionId.H_IDENTITY,
    name="Universal Identity",
    description="6 identity scenarios testing canonical identity stability",
    equivalence_classes=IDENTITY_CLASSES,
    canonical_invariants=[
        "One canonical person identity across all contexts",
        "Roles are temporal relationships, not identity",
        "No duplicate person graphs",
        "Provenance tracks all identity events",
    ],
)


# ============================================================
# DIMENSION I: GOVERNANCE
# ============================================================
GOVERNANCE_CLASSES = [
    EquivalenceClass(
        id="startup_governance",
        name="Startup Governance",
        description="Simple governance for early-stage company",
        properties={"policies": 5, "approvers": 2, "delegation": "simple"},
    ),
    EquivalenceClass(
        id="enterprise_governance",
        name="Enterprise Governance",
        description="Hierarchical governance for large enterprise",
        properties={"policies": 50, "approvers": 10, "delegation": "hierarchical"},
    ),
    EquivalenceClass(
        id="matrix_governance",
        name="Matrix Governance",
        description="Dual-axis governance for matrix organization",
        properties={"policies": 20, "approvers": 8, "delegation": "dual_axis"},
    ),
    EquivalenceClass(
        id="federated_governance",
        name="Federated Governance",
        description="Business unit autonomy with shared services",
        properties={"policies": 30, "approvers": 15, "delegation": "bu_autonomy"},
    ),
    EquivalenceClass(
        id="regulated_governance",
        name="Highly Regulated Governance",
        description="Strict governance for regulated industries",
        properties={"policies": 100, "approvers": 20, "delegation": "strict", "audit": "full"},
    ),
    EquivalenceClass(
        id="autonomy_policy",
        name="Governed Autonomy Policy",
        description="Governance with autonomous operation rules",
        properties={"policies": 15, "autonomy_rules": 10, "human_gate": True},
    ),
]

DIMENSION_I = Dimension(
    id=DimensionId.I_GOVERNANCE,
    name="Universal Governance",
    description="6 governance configurations",
    equivalence_classes=GOVERNANCE_CLASSES,
    canonical_invariants=[
        "Single governance engine, configurable policies",
        "Authorization always through canonical mutation",
        "Delegation is temporal, revocable",
        "No parallel governance engines",
    ],
)


# ============================================================
# DIMENSION J: WORK
# ============================================================
WORK_CLASSES = [
    EquivalenceClass(
        id="project_work",
        name="Project-Based Work",
        description="Work organized as projects with tasks and milestones",
        properties={"work_types": ["project", "task", "milestone"]},
    ),
    EquivalenceClass(
        id="program_work",
        name="Program Management",
        description="Work organized as programs containing projects",
        properties={"work_types": ["program", "project", "workstream"]},
    ),
    EquivalenceClass(
        id="continuous_ops",
        name="Continuous Operations",
        description="24/7 operational work with shifts and incidents",
        properties={"work_types": ["shift", "incident", "runbook", "deployment"]},
    ),
    EquivalenceClass(
        id="case_work",
        name="Case Management",
        description="Work organized as cases with investigations",
        properties={"work_types": ["case", "investigation", "resolution"]},
    ),
    EquivalenceClass(
        id="workflow_work",
        name="Workflow-Driven",
        description="Work driven by defined workflows",
        properties={"work_types": ["workflow", "step", "approval", "handoff"]},
    ),
    EquivalenceClass(
        id="ticket_work",
        name="Ticket/Service Management",
        description="Service management with tickets and SLAs",
        properties={"work_types": ["ticket", "sla", "escalation", "resolution"]},
    ),
    EquivalenceClass(
        id="objective_work",
        name="Objective/OKR Driven",
        description="Work driven by objectives and key results",
        properties={"work_types": ["objective", "key_result", "initiative"]},
    ),
    EquivalenceClass(
        id="contract_work",
        name="Contract Delivery",
        description="Work organized around contract deliverables",
        properties={"work_types": ["contract", "deliverable", "milestone", "acceptance"]},
    ),
    EquivalenceClass(
        id="research_work",
        name="Research/Experimentation",
        description="Research work with studies and experiments",
        properties={"work_types": ["study", "experiment", "trial", "analysis"]},
    ),
    EquivalenceClass(
        id="manufacturing_work",
        name="Manufacturing Process",
        description="Manufacturing work orders and operations",
        properties={"work_types": ["work_order", "operation", "quality_gate", "batch"]},
    ),
]

DIMENSION_J = Dimension(
    id=DimensionId.J_WORK,
    name="Universal Work Model",
    description="10 work type compositions",
    equivalence_classes=WORK_CLASSES,
    canonical_invariants=[
        "Work/Action/Outcome architecture is universal",
        "Work types compose from canonical primitives",
        "No independent work engines per type",
        "Temporal tracking applies to all work",
    ],
)


# ============================================================
# DIMENSION K: FINANCE
# ============================================================
FINANCE_CLASSES = [
    EquivalenceClass(
        id="simple_finance",
        name="Simple Finance",
        description="Single currency, simple chart of accounts",
        properties={"accounts": 10, "currencies": 1, "dimensions": 2},
    ),
    EquivalenceClass(
        id="multi_currency",
        name="Multi-Currency",
        description="Multiple currencies with daily FX rates",
        properties={"accounts": 50, "currencies": 10, "fx_rates": "daily"},
    ),
    EquivalenceClass(
        id="multi_entity_finance",
        name="Multi-Entity Consolidation",
        description="Consolidated finance across entities",
        properties={"entities": 5, "consolidation": "monthly", "intercompany": True},
    ),
    EquivalenceClass(
        id="project_finance",
        name="Project-Based Finance",
        description="Project-level budget tracking and revenue recognition",
        properties={"projects": 20, "budget_tracking": "project", "revenue_recognition": "percentage"},
    ),
    EquivalenceClass(
        id="regulated_finance",
        name="Regulated Finance (SOX/IFRS)",
        description="Strict controls and audit trail for regulated finance",
        properties={"controls": 100, "audit_trail": "full", "segregation": "strict"},
    ),
]

DIMENSION_K = Dimension(
    id=DimensionId.K_FINANCE,
    name="Finance",
    description="5 finance configurations",
    equivalence_classes=FINANCE_CLASSES,
    canonical_invariants=[
        "Finance is provenance-tracked observations",
        "Canonical mutation governs financial commitments",
        "Multi-entity uses same identity/governance",
    ],
)


# ============================================================
# DIMENSION L: PEOPLE
# ============================================================
PEOPLE_CLASSES = [
    EquivalenceClass(
        id="full_time_only",
        name="Full-Time Only",
        description="Only full-time employees",
        properties={"employment_types": ["full_time"]},
    ),
    EquivalenceClass(
        id="mixed_workforce",
        name="Mixed Workforce",
        description="Mix of full-time, part-time, contractors, interns",
        properties={"employment_types": ["full_time", "part_time", "contractor", "intern"]},
    ),
    EquivalenceClass(
        id="global_workforce",
        name="Global Workforce",
        description="Workforce distributed across multiple countries",
        properties={"employment_types": ["full_time", "contractor"], "countries": 15},
    ),
    EquivalenceClass(
        id="unionized",
        name="Unionized Workforce",
        description="Workforce with collective bargaining agreements",
        properties={"employment_types": ["full_time"], "collective_bargaining": True},
    ),
    EquivalenceClass(
        id="high_turnover",
        name="High Turnover",
        description="High annual turnover with seasonal patterns",
        properties={"annual_turnover_pct": 40, "seasonal": True},
    ),
]

DIMENSION_L = Dimension(
    id=DimensionId.L_PEOPLE,
    name="People / Workforce",
    description="5 workforce compositions",
    equivalence_classes=PEOPLE_CLASSES,
    canonical_invariants=[
        "Person identity is canonical, employment is temporal",
        "No employment-type-specific identity models",
        "All workforce events are provenance-tracked",
    ],
)


# ============================================================
# DIMENSION M: COMMUNICATION
# ============================================================
COMMUNICATION_CLASSES = [
    EquivalenceClass(
        id="email_slack",
        name="Email + Slack",
        description="Email for formal, Slack for informal communication",
        properties={"channels": ["email", "slack"], "formal": "email", "informal": "slack"},
    ),
    EquivalenceClass(
        id="teams_outlook",
        name="Teams + Outlook",
        description="Microsoft Teams and Outlook for communication",
        properties={"channels": ["teams", "outlook"], "formal": "outlook", "informal": "teams"},
    ),
    EquivalenceClass(
        id="multi_channel",
        name="Multi-Channel",
        description="Multiple communication channels",
        properties={"channels": ["email", "slack", "teams", "whatsapp", "sms"]},
    ),
    EquivalenceClass(
        id="regulated_comms",
        name="Regulated Communications",
        description="Regulated communication with 7-year archive",
        properties={"channels": ["email", "bloomberg", "reuters"], "archive": "7_years"},
    ),
]

DIMENSION_M = Dimension(
    id=DimensionId.M_COMMUNICATION,
    name="Communication",
    description="4 communication stack configurations",
    equivalence_classes=COMMUNICATION_CLASSES,
    canonical_invariants=[
        "Communication is external observation, not canonical",
        "Provenance tracks source system",
        "No communication-specific canonical models",
    ],
)


# ============================================================
# DIMENSION N: KNOWLEDGE
# ============================================================
KNOWLEDGE_CLASSES = [
    EquivalenceClass(
        id="wiki_knowledge",
        name="Wiki-Based Knowledge",
        description="Knowledge in wiki platforms like Confluence/Notion",
        properties={"sources": ["confluence", "notion"], "structure": "hierarchical"},
    ),
    EquivalenceClass(
        id="document_knowledge",
        name="Document-Based Knowledge",
        description="Knowledge in document stores like Drive/SharePoint",
        properties={"sources": ["drive", "sharepoint"], "structure": "folder"},
    ),
    EquivalenceClass(
        id="code_knowledge",
        name="Code-As-Knowledge",
        description="Knowledge embedded in code repositories",
        properties={"sources": ["github", "gitlab"], "structure": "repository"},
    ),
    EquivalenceClass(
        id="tribal_knowledge",
        name="Tribal/Expert Knowledge",
        description="Tacit knowledge from people and conversations",
        properties={"sources": ["people", "slack", "recordings"], "structure": "graph"},
    ),
    EquivalenceClass(
        id="regulated_knowledge",
        name="Regulated Knowledge",
        description="Strictly controlled knowledge with versioning",
        properties={"sources": ["vault", "controlled_docs"], "structure": "controlled", "versioning": "strict"},
    ),
]

DIMENSION_N = Dimension(
    id=DimensionId.N_KNOWLEDGE,
    name="Knowledge",
    description="5 knowledge management patterns",
    equivalence_classes=KNOWLEDGE_CLASSES,
    canonical_invariants=[
        "Knowledge derives from canonical reality",
        "Company Brain projects over canonical, not separate store",
        "Epistemic status tracked for all knowledge",
    ],
)


# ============================================================
# DIMENSION O: INTEGRATIONS
# ============================================================
INTEGRATION_CLASSES = [
    EquivalenceClass(
        id="github_only",
        name="GitHub Only",
        description="Single GitHub connector with webhook sync",
        properties={"connectors": ["github"], "sync": "webhook"},
    ),
    EquivalenceClass(
        id="google_workspace",
        name="Google Workspace",
        description="Google Workspace connector with polling sync",
        properties={"connectors": ["google"], "sync": "polling"},
    ),
    EquivalenceClass(
        id="microsoft_365",
        name="Microsoft 365",
        description="Microsoft 365 connector with webhook sync",
        properties={"connectors": ["microsoft"], "sync": "webhook"},
    ),
    EquivalenceClass(
        id="jira_slack",
        name="Jira + Slack",
        description="Jira and Slack connectors with mixed sync",
        properties={"connectors": ["jira", "slack"], "sync": "mixed"},
    ),
    EquivalenceClass(
        id="all_connectors",
        name="All 5 Connectors",
        description="All five standard connectors with mixed sync",
        properties={"connectors": ["github", "google", "microsoft", "jira", "slack"], "sync": "mixed"},
    ),
    EquivalenceClass(
        id="custom_connector",
        name="Custom Connector",
        description="Custom connector implementing Universal Connector Contract",
        properties={"connectors": ["custom"], "contract": "universal"},
    ),
]

DIMENSION_O = Dimension(
    id=DimensionId.O_INTEGRATIONS,
    name="Integrations",
    description="6 integration configurations using Universal Connector Contract",
    equivalence_classes=INTEGRATION_CLASSES,
    canonical_invariants=[
        "Universal Connector Contract is mandatory",
        "Observations remain distinct from canonical truth",
        "Reconciliation is governed mutation",
        "No connector-specific canonical paths",
    ],
)


# ============================================================
# DIMENSION P: COMPANY BRAIN
# ============================================================
COMPANY_BRAIN_CLASSES = [
    EquivalenceClass(
        id="basic_brain",
        name="Basic Company Brain",
        description="Simple context retrieval and projection",
        properties={"context_retrieval": True, "projection": True, "query": "simple"},
    ),
    EquivalenceClass(
        id="advanced_brain",
        name="Advanced Company Brain",
        description="Complex queries with reasoning capabilities",
        properties={"context_retrieval": True, "projection": True, "query": "complex", "reasoning": True},
    ),
    EquivalenceClass(
        id="multi_tenant_brain",
        name="Multi-Tenant Company Brain",
        description="Company Brain with strict tenant isolation",
        properties={"context_retrieval": True, "tenant_isolation": "strict", "cross_tenant": "governed"},
    ),
    EquivalenceClass(
        id="temporal_brain",
        name="Temporal Company Brain",
        description="Company Brain with time-travel queries",
        properties={"context_retrieval": True, "time_travel": True, "as_of": "any"},
    ),
]

DIMENSION_P = Dimension(
    id=DimensionId.P_COMPANY_BRAIN,
    name="Company Brain",
    description="4 Company Brain configurations",
    equivalence_classes=COMPANY_BRAIN_CLASSES,
    canonical_invariants=[
        "Company Brain is ALWAYS projection over canonical reality",
        "Never separate intelligence system",
        "Governance respected in all queries",
        "Temporal queries use canonical temporal model",
    ],
)


# ============================================================
# DIMENSION Q: MEMORY
# ============================================================
MEMORY_CLASSES = [
    EquivalenceClass(
        id="startup_memory",
        name="Startup Memory (1 yr)",
        description="1-year retention for startup",
        properties={"retention_years": 1, "events": 10000},
    ),
    EquivalenceClass(
        id="enterprise_memory",
        name="Enterprise Memory (10 yr)",
        description="10-year retention for enterprise",
        properties={"retention_years": 10, "events": 10000000},
    ),
    EquivalenceClass(
        id="longitudinal_memory",
        name="Longitudinal Memory",
        description="Full longitudinal reconstruction with learning",
        properties={"retention_years": 10, "reconstruction": "full", "learning": True},
    ),
    EquivalenceClass(
        id="ma_memory",
        name="M&A Memory",
        description="M&A lineage with integration events",
        properties={"retention_years": 10, "lineage": "full", "integration_events": True},
    ),
    EquivalenceClass(
        id="change_memory",
        name="Organizational Change Memory",
        description="Organizational change events with decision trace",
        properties={"retention_years": 5, "reorg_events": 20, "decision_trace": True},
    ),
]

DIMENSION_Q = Dimension(
    id=DimensionId.Q_MEMORY,
    name="Living Company Memory",
    description="5 memory configurations",
    equivalence_classes=MEMORY_CLASSES,
    canonical_invariants=[
        "Memory derives from canonical reality",
        "No separate memory store",
        "Epistemic status preserved",
        "Temporal reconstruction is canonical",
    ],
)


# ============================================================
# DIMENSION R: PREDICTION
# ============================================================
PREDICTION_CLASSES = [
    EquivalenceClass(
        id="hiring_prediction",
        name="Hiring Forecast",
        description="12-month hiring forecast based on demand",
        properties={"horizon_months": 12, "model": "demand_based"},
    ),
    EquivalenceClass(
        id="budget_prediction",
        name="Budget Forecast",
        description="24-month budget forecast driver-based",
        properties={"horizon_months": 24, "model": "driver_based"},
    ),
    EquivalenceClass(
        id="revenue_prediction",
        name="Revenue Forecast",
        description="36-month revenue forecast pipeline-based",
        properties={"horizon_months": 36, "model": "pipeline_based"},
    ),
    EquivalenceClass(
        id="capacity_prediction",
        name="Capacity Planning",
        description="18-month capacity planning utilization-based",
        properties={"horizon_months": 18, "model": "utilization_based"},
    ),
    EquivalenceClass(
        id="risk_prediction",
        name="Risk Prediction",
        description="12-month risk prediction scenario-based",
        properties={"horizon_months": 12, "model": "scenario_based"},
    ),
]

DIMENSION_R = Dimension(
    id=DimensionId.R_PREDICTION,
    name="Prediction / Forecasting",
    description="5 prediction scenarios",
    equivalence_classes=PREDICTION_CLASSES,
    canonical_invariants=[
        "Predictions are explicit assumptions + uncertainty",
        "Never become canonical truth",
        "Governed by same authorization as decisions",
        "Traceable to canonical reality inputs",
    ],
)


# ============================================================
# DIMENSION S: COUNTERFACTUAL
# ============================================================
COUNTERFACTUAL_CLASSES = [
    EquivalenceClass(
        id="hiring_scenario",
        name="What-If: Hiring Plan",
        description="Counterfactual scenario for hiring plan changes",
        properties={"scenario": "hiring", "variables": ["headcount", "budget", "timeline"]},
    ),
    EquivalenceClass(
        id="reorg_scenario",
        name="What-If: Reorganization",
        description="Counterfactual scenario for reorganization",
        properties={"scenario": "reorg", "variables": ["structure", "reporting", "roles"]},
    ),
    EquivalenceClass(
        id="market_expansion",
        name="What-If: Market Expansion",
        description="Counterfactual scenario for market expansion",
        properties={"scenario": "expansion", "variables": ["region", "investment", "team"]},
    ),
    EquivalenceClass(
        id="project_delay",
        name="What-If: Project Delay",
        description="Counterfactual scenario for project delay",
        properties={"scenario": "delay", "variables": ["project", "duration", "dependencies"]},
    ),
    EquivalenceClass(
        id="ma_scenario",
        name="What-If: M&A",
        description="Counterfactual scenario for M&A",
        properties={"scenario": "ma", "variables": ["target", "structure", "integration"]},
    ),
]

DIMENSION_S = Dimension(
    id=DimensionId.S_COUNTERFACTUAL,
    name="Counterfactual / Simulation",
    description="5 counterfactual scenarios",
    equivalence_classes=COUNTERFACTUAL_CLASSES,
    canonical_invariants=[
        "Simulation is explicitly non-canonical",
        "Assumptions and uncertainty are first-class",
        "Governed scenario creation/commitment",
        "Canonical reality unchanged by simulation",
    ],
)


# ============================================================
# DIMENSION T: GOVERNED AUTONOMY
# ============================================================
AUTONOMY_CLASSES = [
    EquivalenceClass(
        id="low_autonomy",
        name="Low Autonomy (Human-Gated)",
        description="All autonomous actions require human approval",
        properties={"autonomy_level": "low", "human_approval": "all", "evidence_required": True},
    ),
    EquivalenceClass(
        id="medium_autonomy",
        name="Medium Autonomy (Policy-Gated)",
        description="Autonomy within policy boundaries, exceptions need approval",
        properties={"autonomy_level": "medium", "human_approval": "exceptions", "evidence_required": True},
    ),
    EquivalenceClass(
        id="high_autonomy",
        name="High Autonomy (Governed)",
        description="High autonomy with audit-based human oversight",
        properties={"autonomy_level": "high", "human_approval": "audit", "evidence_required": True, "policy": "strict"},
    ),
    EquivalenceClass(
        id="emergency_autonomy",
        name="Emergency Autonomy",
        description="Emergency autonomy with post-facto review",
        properties={"autonomy_level": "emergency", "human_approval": "post_facto", "evidence_required": True, "scope": "limited"},
    ),
]

DIMENSION_T = Dimension(
    id=DimensionId.T_GOVERNED_AUTONOMY,
    name="Governed Autonomous Operations",
    description="4 autonomy levels",
    equivalence_classes=AUTONOMY_CLASSES,
    canonical_invariants=[
        "Autonomy eligibility → evidence → governance → authorization → commitment → execution → outcome → verification → learning",
        "Human control preserved where required",
        "No separate autonomy authorization system",
        "All autonomous actions provenance-tracked",
    ],
)


# ============================================================
# DIMENSION U: COMPANY CONTINUITY
# ============================================================
CONTINUITY_CLASSES = [
    EquivalenceClass(
        id="founder_departure",
        name="Founder Departure",
        description="Founder departure with planned succession",
        properties={"event": "founder_departure", "succession": "planned", "knowledge_transfer": True},
    ),
    EquivalenceClass(
        id="executive_departure",
        name="Executive Departure",
        description="Executive departure with interim then permanent succession",
        properties={"event": "executive_departure", "succession": "interim_then_permanent", "knowledge_transfer": True},
    ),
    EquivalenceClass(
        id="manager_departure",
        name="Manager Departure",
        description="Manager departure with team continuity",
        properties={"event": "manager_departure", "team_continuity": True, "reports_reassigned": True},
    ),
    EquivalenceClass(
        id="employee_turnover",
        name="High Employee Turnover",
        description="High turnover with continuous knowledge capture",
        properties={"event": "turnover", "rate": "30%", "knowledge_capture": "continuous"},
    ),
    EquivalenceClass(
        id="reorganization",
        name="Major Reorganization",
        description="Company-wide reorganization with canonical continuity",
        properties={"event": "reorg", "scope": "company_wide", "continuity": "canonical"},
    ),
    EquivalenceClass(
        id="acquisition_continuity",
        name="Acquisition Continuity",
        description="Acquisition with legacy preservation",
        properties={"event": "acquisition", "legacy_preserved": True, "integration": "phased"},
    ),
    EquivalenceClass(
        id="merger_continuity",
        name="Merger Continuity",
        description="Merger with both legacies preserved",
        properties={"event": "merger", "both_legacies_preserved": True, "new_identity": True},
    ),
    EquivalenceClass(
        id="system_replacement",
        name="Core System Replacement",
        description="Core system replacement with canonical migration",
        properties={"event": "system_replacement", "data_migration": "canonical", "history_preserved": True},
    ),
]

DIMENSION_U = Dimension(
    id=DimensionId.U_COMPANY_CONTINUITY,
    name="Company Continuity",
    description="8 continuity scenarios",
    equivalence_classes=CONTINUITY_CLASSES,
    canonical_invariants=[
        "Company history remains intact through all changes",
        "Canonical reality preserves all historical facts",
        "Identity/governance/decision lineage continuous",
        "No historical truth rewriting",
    ],
)


# ============================================================
# DIMENSION V: MIGRATION
# ============================================================
MIGRATION_CLASSES = [
    EquivalenceClass(
        id="startup_to_scale",
        name="Startup → Scale-Up",
        description="Startup growing to scale-up",
        properties={"from": "startup_5", "to": "medium_500", "preserve": "all"},
    ),
    EquivalenceClass(
        id="acquisition_migration",
        name="Acquisition Data Migration",
        description="Migrating acquired company data to VCOS",
        properties={"from": "external_system", "to": "vcos_canonical", "preserve": "identity+history"},
    ),
    EquivalenceClass(
        id="merger_migration",
        name="Merger Data Migration",
        description="Merging two systems into VCOS canonical",
        properties={"from": "two_systems", "to": "vcos_canonical", "preserve": "both_histories"},
    ),
    EquivalenceClass(
        id="dept_restructure",
        name="Department Restructure",
        description="Restructuring from functional to divisional",
        properties={"from": "functional", "to": "divisional", "preserve": "work+decision_history"},
    ),
    EquivalenceClass(
        id="system_replacement_mig",
        name="External System Replacement",
        description="Replacing legacy HR system with VCOS",
        properties={"from": "legacy_hr", "to": "vcos_canonical", "preserve": "identity+provenance"},
    ),
    EquivalenceClass(
        id="employee_transfer",
        name="Cross-Entity Employee Transfer",
        description="Employee transferring between entities",
        properties={"from": "entity_a", "to": "entity_b", "preserve": "identity+history+relationships"},
    ),
    EquivalenceClass(
        id="role_migration",
        name="Role Migration",
        description="Migrating from old role model to new",
        properties={"from": "old_role_model", "to": "new_role_model", "preserve": "authorization_history"},
    ),
]

DIMENSION_V = Dimension(
    id=DimensionId.V_MIGRATION,
    name="Migration Universality",
    description="7 migration scenarios",
    equivalence_classes=MIGRATION_CLASSES,
    canonical_invariants=[
        "Identity, provenance, temporal history preserved",
        "Governance, decision history, learning preserved",
        "No historical truth rewriting",
        "Canonical mutation governs migration",
    ],
)


# ============================================================
# DIMENSION W: M&A
# ============================================================
MA_CLASSES = [
    EquivalenceClass(
        id="asset_acquisition",
        name="Asset Acquisition",
        description="Asset purchase with selective transfer",
        properties={"type": "asset", "entities_transfer": "partial", "people_transfer": "selective"},
    ),
    EquivalenceClass(
        id="stock_acquisition",
        name="Stock Acquisition",
        description="Stock purchase with full entity transfer",
        properties={"type": "stock", "entities_transfer": "full", "people_transfer": "all"},
    ),
    EquivalenceClass(
        id="merger_equals",
        name="Merger of Equals",
        description="Two companies merging as equals",
        properties={"type": "merger", "entities": "both", "new_identity": True, "governance": "combined"},
    ),
    EquivalenceClass(
        id="divestiture",
        name="Divestiture / Spin-Off",
        description="Spinning off entity with governed history split",
        properties={"type": "divestiture", "entity_separated": True, "history_split": "governed"},
    ),
    EquivalenceClass(
        id="joint_venture_formation",
        name="JV Formation",
        description="Creating joint venture with shared governance",
        properties={"type": "jv", "parents": 2, "new_entity": True, "governance": "shared"},
    ),
    EquivalenceClass(
        id="roll_up",
        name="Roll-Up Acquisition",
        description="Rolling up multiple acquisitions into platform",
        properties={"type": "rollup", "acquisitions": 5, "platform": "parent", "integration": "phased"},
    ),
]

DIMENSION_W = Dimension(
    id=DimensionId.W_MA,
    name="M&A Lineage",
    description="6 M&A scenarios",
    equivalence_classes=MA_CLASSES,
    canonical_invariants=[
        "M&A lineage is canonical temporal relationship",
        "Both legacies preserved in canonical reality",
        "Identity/governance/finance lineage traceable",
        "No separate M&A canonical model",
    ],
)


# ============================================================
# DIMENSION X: SECURITY
# ============================================================
SECURITY_CLASSES = [
    EquivalenceClass(
        id="standard_security",
        name="Standard Security",
        description="Row-level tenant isolation with standard encryption",
        properties={"tenant_isolation": "row_level", "encryption": "at_rest", "audit": "standard"},
    ),
    EquivalenceClass(
        id="high_security",
        name="High Security (SOC2/ISO)",
        description="Schema-level isolation with HSM keys",
        properties={"tenant_isolation": "schema", "encryption": "at_rest+transit", "audit": "comprehensive", "keys": "hsm"},
    ),
    EquivalenceClass(
        id="regulated_security",
        name="Regulated (FedRAMP/HIPAA)",
        description="Database-level isolation with immutable audit",
        properties={"tenant_isolation": "database", "encryption": "full", "audit": "immutable", "access": "just_in_time"},
    ),
    EquivalenceClass(
        id="zero_trust",
        name="Zero Trust",
        description="Zero trust with continuous verification",
        properties={"tenant_isolation": "zero_trust", "verification": "continuous", "least_privilege": "strict"},
    ),
]

DIMENSION_X = Dimension(
    id=DimensionId.X_SECURITY,
    name="Security / Tenant Isolation",
    description="4 security postures",
    equivalence_classes=SECURITY_CLASSES,
    canonical_invariants=[
        "Tenant isolation is canonical invariant",
        "Scope isolation enforced at mutation boundary",
        "Provenance tracks all access",
        "No security-level-specific canonical models",
    ],
)


# ============================================================
# DIMENSION Y: DISASTER RECOVERY
# ============================================================
DR_CLASSES = [
    EquivalenceClass(
        id="backup_restore",
        name="Backup/Restore",
        description="Traditional backup/restore with 24h RPO",
        properties={"rpo_hours": 24, "rto_hours": 4, "scope": "full"},
    ),
    EquivalenceClass(
        id="pilot_light",
        name="Pilot Light DR",
        description="Pilot light DR with 1h RPO",
        properties={"rpo_hours": 1, "rto_hours": 2, "scope": "core"},
    ),
    EquivalenceClass(
        id="warm_standby",
        name="Warm Standby",
        description="Warm standby with 15min RPO",
        properties={"rpo_minutes": 15, "rto_hours": 1, "scope": "full"},
    ),
    EquivalenceClass(
        id="multi_region_active",
        name="Multi-Region Active-Active",
        description="Active-active multi-region with zero RPO",
        properties={"rpo_seconds": 0, "rto_minutes": 5, "scope": "full", "regions": 3},
    ),
]

DIMENSION_Y = Dimension(
    id=DimensionId.Y_DISASTER_RECOVERY,
    name="Disaster Recovery",
    description="4 DR configurations",
    equivalence_classes=DR_CLASSES,
    canonical_invariants=[
        "Canonical integrity verified post-recovery",
        "Temporal integrity preserved",
        "Provenance chain unbroken",
        "Company Brain state recoverable",
        "Longitudinal state recoverable",
    ],
)


# ============================================================
# DIMENSION Z: ACCESSIBILITY / API / INTEROPERABILITY
# ============================================================
API_CLASSES = [
    EquivalenceClass(
        id="rest_api",
        name="REST API",
        description="REST API with OAuth2 authentication",
        properties={"protocol": "rest", "auth": "oauth2", "versioning": "url"},
    ),
    EquivalenceClass(
        id="graphql_api",
        name="GraphQL API",
        description="GraphQL API with introspection",
        properties={"protocol": "graphql", "auth": "oauth2", "introspection": True},
    ),
    EquivalenceClass(
        id="grpc_api",
        name="gRPC API",
        description="gRPC API with mTLS authentication",
        properties={"protocol": "grpc", "auth": "mtls", "contract": "protobuf"},
    ),
    EquivalenceClass(
        id="webhook_api",
        name="Webhook/Event API",
        description="Webhook API with HMAC authentication",
        properties={"protocol": "webhook", "auth": "hmac", "retry": "exponential"},
    ),
    EquivalenceClass(
        id="multi_protocol",
        name="Multi-Protocol",
        description="Multiple protocols with same canonical semantics",
        properties={"protocols": ["rest", "graphql", "grpc", "webhook"], "canonical": "same"},
    ),
]

DIMENSION_Z = Dimension(
    id=DimensionId.Z_ACCESSIBILITY_API,
    name="Accessibility / API / Interoperability",
    description="5 API/interoperability configurations",
    equivalence_classes=API_CLASSES,
    canonical_invariants=[
        "API semantics are canonical across protocols",
        "No protocol-specific canonical reality",
        "Governance enforced at mutation boundary",
        "Provenance tracks API source",
    ],
)


# ============================================================
# ALL DIMENSIONS REGISTRY
# ============================================================
ALL_DIMENSIONS: List[Dimension] = [
    DIMENSION_A,
    DIMENSION_B,
    DIMENSION_C,
    DIMENSION_D,
    DIMENSION_E,
    DIMENSION_F,
    DIMENSION_G,
    DIMENSION_H,
    DIMENSION_I,
    DIMENSION_J,
    DIMENSION_K,
    DIMENSION_L,
    DIMENSION_M,
    DIMENSION_N,
    DIMENSION_O,
    DIMENSION_P,
    DIMENSION_Q,
    DIMENSION_R,
    DIMENSION_S,
    DIMENSION_T,
    DIMENSION_U,
    DIMENSION_V,
    DIMENSION_W,
    DIMENSION_X,
    DIMENSION_Y,
    DIMENSION_Z,
]

DIMENSIONS_BY_ID: Dict[DimensionId, Dimension] = {d.id: d for d in ALL_DIMENSIONS}


def get_dimension(dim_id: DimensionId) -> Dimension:
    """Get dimension by ID."""
    return DIMENSIONS_BY_ID[dim_id]


def get_all_equivalence_classes() -> List[EquivalenceClass]:
    """Get all equivalence classes across all dimensions."""
    classes = []
    for dim in ALL_DIMENSIONS:
        classes.extend(dim.equivalence_classes)
    return classes


def get_representative_profiles() -> List[Dict[str, Any]]:
    """Generate representative company profiles (not full Cartesian product).
    
    Uses orthogonal array / pairwise sampling to cover all dimension-value
    pairs with minimal profiles.
    """
    # Core profiles that cover major combinations
    profiles = [
        {
            "name": "startup_software_us",
            "dimensions": {
                "A": "startup_5",
                "B": "flat",
                "C": "software",
                "D": "united_states",
                "E": "single_entity",
                "F": "parent_subsidiary_2",  # single entity effectively
                "G": "en_us_only",
                "H": "single_role",
                "I": "startup_governance",
                "J": "project_work",
                "K": "simple_finance",
                "L": "full_time_only",
                "M": "email_slack",
                "N": "wiki_knowledge",
                "O": "github_only",
                "P": "basic_brain",
                "Q": "startup_memory",
                "R": "hiring_prediction",
                "S": "hiring_scenario",
                "T": "low_autonomy",
                "U": "employee_turnover",
                "V": "startup_to_scale",
                "W": "asset_acquisition",
                "X": "standard_security",
                "Y": "backup_restore",
                "Z": "rest_api",
            },
        },
        {
            "name": "small_manufacturing_eu",
            "dimensions": {
                "A": "small_50",
                "B": "functional",
                "C": "manufacturing",
                "D": "europe",
                "E": "single_entity",
                "F": "parent_subsidiary_2",
                "G": "multilingual_eu",
                "H": "multi_role",
                "I": "enterprise_governance",
                "J": "manufacturing_work",
                "K": "multi_currency",
                "L": "mixed_workforce",
                "M": "teams_outlook",
                "N": "document_knowledge",
                "O": "microsoft_365",
                "P": "advanced_brain",
                "Q": "enterprise_memory",
                "R": "capacity_prediction",
                "S": "reorg_scenario",
                "T": "medium_autonomy",
                "U": "manager_departure",
                "V": "dept_restructure",
                "W": "asset_acquisition",
                "X": "high_security",
                "Y": "pilot_light",
                "Z": "graphql_api",
            },
        },
        {
            "name": "medium_healthcare_us",
            "dimensions": {
                "A": "medium_500",
                "B": "matrix",
                "C": "healthcare",
                "D": "united_states",
                "E": "parent_subsidiary",
                "F": "parent_subsidiary_jv",
                "G": "en_us_only",
                "H": "cross_subsidiary",
                "I": "regulated_governance",
                "J": "case_work",
                "K": "regulated_finance",
                "L": "unionized",
                "M": "regulated_comms",
                "N": "regulated_knowledge",
                "O": "all_connectors",
                "P": "temporal_brain",
                "Q": "longitudinal_memory",
                "R": "risk_prediction",
                "S": "ma_scenario",
                "T": "high_autonomy",
                "U": "acquisition_continuity",
                "V": "acquisition_migration",
                "W": "stock_acquisition",
                "X": "regulated_security",
                "Y": "warm_standby",
                "Z": "multi_protocol",
            },
        },
        {
            "name": "large_financial_global",
            "dimensions": {
                "A": "large_5k",
                "B": "divisional",
                "C": "financial_services",
                "D": "multi_region",
                "E": "parent_subsidiary",
                "F": "complex_group",
                "G": "multilingual_global",
                "H": "cross_subsidiary",
                "I": "regulated_governance",
                "J": "workflow_work",
                "K": "multi_entity_finance",
                "L": "global_workforce",
                "M": "multi_channel",
                "N": "code_knowledge",
                "O": "all_connectors",
                "P": "multi_tenant_brain",
                "Q": "enterprise_memory",
                "R": "revenue_prediction",
                "S": "market_expansion",
                "T": "high_autonomy",
                "U": "reorganization",
                "V": "merger_migration",
                "W": "merger_equals",
                "X": "zero_trust",
                "Y": "multi_region_active",
                "Z": "multi_protocol",
            },
        },
        {
            "name": "enterprise_multinational",
            "dimensions": {
                "A": "enterprise_50k",
                "B": "federated",
                "C": "multinational",
                "D": "multi_region",
                "E": "holding_company",
                "F": "holding_3_subs",
                "G": "multilingual_global",
                "H": "acquisition_transfer",
                "I": "federated_governance",
                "J": "program_work",
                "K": "multi_entity_finance",
                "L": "global_workforce",
                "M": "multi_channel",
                "N": "tribal_knowledge",
                "O": "all_connectors",
                "P": "multi_tenant_brain",
                "Q": "ma_memory",
                "R": "risk_prediction",
                "S": "ma_scenario",
                "T": "emergency_autonomy",
                "U": "merger_continuity",
                "V": "merger_migration",
                "W": "roll_up",
                "X": "zero_trust",
                "Y": "multi_region_active",
                "Z": "multi_protocol",
            },
        },
        {
            "name": "mega_conglomerate",
            "dimensions": {
                "A": "mega_500k",
                "B": "hybrid",
                "C": "multinational",
                "D": "multi_region",
                "E": "holding_company",
                "F": "complex_group",
                "G": "multilingual_global",
                "H": "acquisition_transfer",
                "I": "federated_governance",
                "J": "objective_work",
                "K": "multi_entity_finance",
                "L": "global_workforce",
                "M": "multi_channel",
                "N": "tribal_knowledge",
                "O": "custom_connector",
                "P": "temporal_brain",
                "Q": "change_memory",
                "R": "capacity_prediction",
                "S": "project_delay",
                "T": "emergency_autonomy",
                "U": "system_replacement",
                "V": "system_replacement_mig",
                "W": "roll_up",
                "X": "zero_trust",
                "Y": "multi_region_active",
                "Z": "multi_protocol",
            },
        },
    ]
    return profiles


# ============================================================
# CANONICAL INVARIANTS (Phase 20 - Property-Based Acceptance)
# ============================================================
CANONICAL_INVARIANTS = [
    # Property 1: Every canonical entity has tenant/organization ownership
    "PROPERTY_1_TENANT_OWNERSHIP",
    # Property 2: Every governed mutation passes through canonical mutation
    "PROPERTY_2_CANONICAL_MUTATION",
    # Property 3: Every external observation remains distinguishable from canonical truth
    "PROPERTY_3_OBSERVATION_DISTINGUISHABLE",
    # Property 4: Every historical fact remains temporally reconstructable
    "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE",
    # Property 5: Every provenance reference is valid and scoped
    "PROPERTY_5_PROVENANCE_VALID",
    # Property 6: Every authorization is governed
    "PROPERTY_6_AUTHORIZATION_GOVERNED",
    # Property 7: Every outcome is distinguishable from action/execution
    "PROPERTY_7_OUTCOME_DISTINGUISHABLE",
    # Property 8: Every prediction remains distinguishable from verified reality
    "PROPERTY_8_PREDICTION_DISTINGUISHABLE",
    # Property 9: Memory derives from canonical reality
    "PROPERTY_9_MEMORY_DERIVES_CANONICAL",
    # Property 10: Digital Twin remains a projection
    "PROPERTY_10_TWIN_IS_PROJECTION",
    # Property 11: Failure cannot silently invent truth
    "PROPERTY_11_FAILURE_NO_INVENT",
    # Property 12: Company types do not create separate canonical realities
    "PROPERTY_12_NO_FORK",
]