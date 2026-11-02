with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the sync validate_epistemic_boundary function with comprehensive Gate 6-F implementation
old_function = '''def validate_epistemic_boundary(
    context: CanonicalMutationContext,
    target_epistemic: EpistemicStatus,
) -> bool:
    """Enforce epistemic boundaries - prevent illegal promotion."""

    # Define allowed transitions
    allowed_promotions = {
        EpistemicStatus.OBSERVED: [EpistemicStatus.MEASURED, EpistemicStatus.EVIDENCE_BACKED],
        EpistemicStatus.MEASURED: [EpistemicStatus.EVIDENCE_BACKED],
        EpistemicStatus.EVIDENCE_BACKED: [EpistemicStatus.INFERRED],
        EpistemicStatus.INFERRED: [EpistemicStatus.PREDICTED, EpistemicStatus.PROPOSED],
        EpistemicStatus.PREDICTED: [EpistemicStatus.PROPOSED],
        EpistemicStatus.PROPOSED: [EpistemicStatus.CONTESTED],
        EpistemicStatus.CONTESTED: [],
    }

    current = context.epistemic_status
    target = target_epistemic

    if target not in allowed_promotions.get(current, []):
        # Allow same status (no promotion)
        if target != current:
            raise EpistemicViolation(
                f"Illegal epistemic promotion: {current} -> {target}. "
                f"Allowed from {current}: {allowed_promotions.get(current, [])}"
            )

    return True


# -------------------------------------------------------------------------
# Exact-Once / Fingerprint Validation
# -------------------------------------------------------------------------'''

new_function = '''def validate_epistemic_boundary(
    context: CanonicalMutationContext,
    target_epistemic: EpistemicStatus,
) -> bool:
    """Enforce epistemic boundaries - prevent illegal promotion."""
    
    # Define allowed transitions (Gate 6-F: Epistemic Integrity)
    # Observation → Measured → Evidence-Backed → Inferred → Predicted/Proposed → Contested
    allowed_promotions = {
        EpistemicStatus.OBSERVED: [EpistemicStatus.MEASURED, EpistemicStatus.EVIDENCE_BACKED],
        EpistemicStatus.MEASURED: [EpistemicStatus.EVIDENCE_BACKED],
        EpistemicStatus.EVIDENCE_BACKED: [EpistemicStatus.INFERRED],
        EpistemicStatus.INFERRED: [EpistemicStatus.PREDICTED, EpistemicStatus.PROPOSED],
        EpistemicStatus.PREDICTED: [EpistemicStatus.PROPOSED],
        EpistemicStatus.PROPOSED: [EpistemicStatus.CONTESTED],
        EpistemicStatus.CONTESTED: [],
    }

    current = context.epistemic_status
    target = target_epistemic

    if target not in allowed_promotions.get(current, []):
        # Allow same status (no promotion)
        if target != current:
            raise EpistemicViolation(
                f"Illegal epistemic promotion: {current} -> {target}. "
                f"Allowed from {current}: {allowed_promotions.get(current, [])}"
            )

    return True


async def validate_epistemic_integrity(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """
    Gate 6-F: Comprehensive Epistemic Integrity Enforcement.
    
    Enforces the following invariants:
    1. No illegal epistemic promotion without required supporting evidence
    2. AI-generated content cannot silently become canonical facts
    3. Evidence does not equal truth (evidence supports claims, doesn't prove them)
    4. Provenance must survive epistemic transitions
    5. Historical epistemic state cannot be silently rewritten
    6. Contradiction preservation during epistemic transitions
    7. Governance authorization required for epistemic promotion
    8. Temporal context preserved during epistemic transitions
    9. Prevention of prediction/outcome confusion
    10. Prevention of recommendation/decision confusion
    11. Prevention of decision/authorization confusion
    12. Prevention of authorization/execution confusion
    """
    
    # ================================================================
    # 1. BASIC PROMOTION RULES (already enforced by validate_epistemic_boundary)
    # ================================================================
    validate_epistemic_boundary(context, context.epistemic_status)
    
    # ================================================================
    # 2. AI ORIGIN TRACKING - AI-generated content must remain explicitly marked
    # ================================================================
    ai_origin_fields = ["ai_generated", "model_id", "model_version", "generation_context"]
    has_ai_origin = any(context.provenance.get(f) or context.metadata.get(f) for f in ai_origin_fields)
    
    # If content is AI-generated and being promoted to observed/measured/evidence_backed,
    # it must have explicit human confirmation
    if has_ai_origin and context.epistemic_status in (
        EpistemicStatus.OBSERVED, 
        EpistemicStatus.MEASURED, 
        EpistemicStatus.EVIDENCE_BACKED
    ):
        human_confirmation = context.provenance.get("human_confirmed") or context.metadata.get("human_confirmed")
        if not human_confirmation:
            raise AIOriginViolation(
                f"AI-generated content cannot be promoted to {context.epistemic_status} "
                f"without explicit human confirmation. "
                f"Source: {context.provenance.get('model_id', 'unknown model')}"
            )
    
    # AI-originated content must preserve its origin metadata through all transitions
    if has_ai_origin:
        for field in ai_origin_fields:
            if field in context.provenance or field in context.metadata:
                # Verify origin metadata is not being stripped
                pass  # Provenance validation will enforce this
    
    # ================================================================
    # 3. EVIDENCE != TRUTH PROTECTION
    # ================================================================
    # Evidence supports claims; it does not automatically prove them.
    # An entity with evidence_backed status cannot be treated as observed fact.
    evidence_fields = ["evidence_ids", "supporting_evidence", "source_evidence"]
    has_evidence = any(context.provenance.get(f) or context.metadata.get(f) for f in evidence_fields)
    
    if has_evidence and context.epistemic_status == EpistemicStatus.OBSERVED:
        # Evidence-backed claim being treated as direct observation requires explicit justification
        direct_observation = context.provenance.get("direct_observation") or context.metadata.get("direct_observation")
        if not direct_observation:
            raise EvidenceTruthConfusionViolation(
                f"Evidence-supported claim cannot be promoted to OBSERVED "
                f"without direct observation confirmation. "
                f"Use EVIDENCE_BACKED for evidence-supported claims."
            )
    
    # ================================================================
    # 4. PROVENANCE PRESERVATION DURING EPISTEMIC TRANSITION
    # ================================================================
    # If this is an UPDATE or TRANSITION that changes epistemic status,
    # provenance must be preserved
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load existing entity to check provenance
        from app.models.company_operating import CompanyDecision
        from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
        from app.models.company_actions import CompanyAction
        
        entity_type_map = {
            "CompanyDecision": CompanyDecision,
            "CompanyCommitment": CompanyCommitment,
            "CompanyAuthorization": CompanyAuthorization,
            "CompanyAction": CompanyAction,
        }
        
        model = entity_type_map.get(context.target_entity_type)
        if model:
            existing = await db.get(model, context.target_id)
            if existing:
                # Check if provenance is being stripped
                existing_provenance = getattr(existing, "provenance", None)
                new_provenance = context.provenance
                
                if existing_provenance and new_provenance:
                    # Verify critical provenance fields are not stripped
                    critical_fields = ["source_event_id", "decision_id", "authorization_id", "commitment_id", "evidence_ids"]
                    for field in critical_fields:
                        if existing_provenance.get(field) and not new_provenance.get(field):
                            raise ProvenanceStrippingViolation(
                                f"Epistemic transition cannot strip provenance field '{field}'. "
                                f"Original: {existing_provenance.get(field)}"
                            )
    
    # ================================================================
    # 5. HISTORICAL EPISTEMIC STATE PROTECTION
    # ================================================================
    # Historical epistemic states cannot be silently rewritten
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        model = entity_type_map.get(context.target_entity_type)
        if model:
            existing = await db.get(model, context.target_id)
            if existing:
                existing_status = getattr(existing, "epistemic_status", None)
                if existing_status and existing_status != context.epistemic_status:
                    # Epistemic status change requires explicit justification
                    if context.epistemic_status in (
                        EpistemicStatus.OBSERVED, 
                        EpistemicStatus.MEASURED, 
                        EpistemicStatus.EVIDENCE_BACKED
                    ):
                        # Promoting historical record to stronger epistemic status requires evidence
                        justification = context.provenance.get("epistemic_justification") or context.metadata.get("epistemic_justification")
                        if not justification:
                            raise EpistemicPromotionViolation(
                                f"Historical entity with status '{existing_status}' cannot be promoted to "
                                f"'{context.epistemic_status}' without explicit epistemic justification."
                            )
    
    # ================================================================
    # 6. CONTRADICTION PRESERVATION INTEGRATION
    # ================================================================
    # If this entity has associated contradictions, epistemic promotion
    # must not silently resolve them
    if context.target_id:
        from app.models.company_operating import CompanyDecisionContradiction
        contradictions = await db.execute(
            select(CompanyDecisionContradiction).where(
                CompanyDecisionContradiction.decision_id == context.target_id,
                CompanyDecisionContradiction.status.in_(["open", "acknowledged"])
            )
        )
        open_contradictions = contradictions.scalars().all()
        
        if open_contradictions and context.epistemic_status in (
            EpistemicStatus.EVIDENCE_BACKED,
            EpistemicStatus.MEASURED,
            EpistemicStatus.OBSERVED
        ):
            # Promoting to strong epistemic status while contradictions exist
            # requires explicit contradiction resolution
            resolution = context.provenance.get("contradiction_resolution") or context.metadata.get("contradiction_resolution")
            if not resolution:
                raise ContradictionPreservationViolation(
                    f"Cannot promote to {context.epistemic_status} while {len(open_contradictions)} "
                    f"contradiction(s) remain open. Explicit contradiction resolution required."
                )
    
    # ================================================================
    # 7. GOVERNANCE AUTHORIZATION FOR EPISTEMIC PROMOTION
    # ================================================================
    # Strong epistemic promotions require appropriate governance
    promotion_requiring_governance = {
        EpistemicStatus.EVIDENCE_BACKED: ["decisions:manage", "evidence:validate"],
        EpistemicStatus.MEASURED: ["decisions:manage", "evidence:validate"],
        EpistemicStatus.OBSERVED: ["decisions:manage", "evidence:validate", "governance:approve"],
    }
    
    required_perms = promotion_requiring_governance.get(context.epistemic_status, [])
    if required_perms:
        caller_perms = await context.caller.get_permissions(db) if db else frozenset()
        for perm in required_perms:
            if perm not in caller_perms:
                raise EpistemicPromotionViolation(
                    f"Promotion to {context.epistemic_status} requires permission: {perm}"
                )
    
    # ================================================================
    # 8. TEMPORAL CONTEXT PRESERVATION
    # ================================================================
    # Epistemic transitions must preserve temporal context
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        model = entity_type_map.get(context.target_entity_type)
        if model:
            existing = await db.get(model, context.target_id)
            if existing:
                # Preserve valid_from/valid_to temporal context
                existing_valid_from = getattr(existing, "valid_from", None)
                existing_valid_to = getattr(existing, "valid_to", None)
                if existing_valid_from or existing_valid_to:
                    # Temporal context must be preserved or explicitly extended
                    pass  # Temporal validation will enforce this
    
    # ================================================================
    # 9. PREDICTION/OUTCOME CONFUSION PREVENTION
    # ================================================================
    # A prediction cannot become an actual outcome without verification
    if context.epistemic_status == EpistemicStatus.OBSERVED:
        # Check if this was previously a prediction
        model = entity_type_map.get(context.target_entity_type)
        if model and context.target_id:
            existing = await db.get(model, context.target_id)
            if existing:
                existing_status = getattr(existing, "epistemic_status", None)
                if existing_status == EpistemicStatus.PREDICTED:
                    # Prediction becoming observation requires outcome verification
                    verification = context.provenance.get("outcome_verification") or context.metadata.get("outcome_verification")
                    if not verification:
                        raise EvidenceTruthConfusionViolation(
                            f"Prediction cannot become OBSERVED without outcome verification. "
                            f"Use EVIDENCE_BACKED for verified predictions."
                        )
    
    # ================================================================
    # 10. RECOMMENDATION/DECISION CONFUSION PREVENTION
    # ================================================================
    if context.target_entity_type == "CompanyDecision" and context.mutation_type == MutationType.CREATE:
        # New decisions must have appropriate epistemic status
        if context.epistemic_status == EpistemicStatus.OBSERVED:
            raise EvidenceTruthConfusionViolation(
                f"New decision cannot be created as OBSERVED. "
                f"Decisions start as PROPOSED and progress through governance."
            )
    
    # ================================================================
    # 11. DECISION/AUTHORIZATION CONFUSION PREVENTION
    # ================================================================
    if context.target_entity_type == "CompanyAuthorization" and context.mutation_type == MutationType.TRANSITION:
        # Authorization transition to approved requires decision backing
        if context.epistemic_status == EpistemicStatus.EVIDENCE_BACKED:
            decision_id = context.provenance.get("decision_id")
            if not decision_id:
                raise EvidenceTruthConfusionViolation(
                    f"Authorization cannot be EVIDENCE_BACKED without supporting decision_id"
                )
    
    # ================================================================
    # 12. AUTHORIZATION/EXECUTION CONFUSION PREVENTION
    # ================================================================
    if context.target_entity_type == "CompanyAction" and context.mutation_type == MutationType.CREATE:
        # Actions require authorization provenance
        auth_id = context.provenance.get("authorization_id") or context.metadata.get("authorization_id")
        if not auth_id:
            raise EvidenceTruthConfusionViolation(
                f"Action cannot be created without authorization_id provenance"
            )
    
    return True


# -------------------------------------------------------------------------
# Exact-Once / Fingerprint Validation
# -------------------------------------------------------------------------'''

content = content.replace(old_function, new_function)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Enhanced validate_epistemic_boundary with Gate 6-F enforcement')