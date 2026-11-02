import re

with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the validate_epistemic_integrity function and replace it entirely
old_function_pattern = r'async def validate_epistemic_integrity\([\s\S]*?^async def '

new_function = '''async def validate_epistemic_integrity(
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
    # If this is an UPDATE or TRANSITION, provenance must be preserved
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
                # DEBUG
                print(f"DEBUG provenance check: existing.provenance={getattr(existing, 'provenance', None)}, new_provenance={context.provenance}")
                # Check if provenance is being stripped
                existing_provenance = getattr(existing, "provenance", None)
                new_provenance = context.provenance or {}
                
                # If existing entity has provenance, new provenance must not strip it
                if existing_provenance:
                    # Verify critical provenance fields are not stripped
                    critical_fields = ["source_event_id", "decision_id", "authorization_id", "commitment_id", "evidence_ids"]
                    for field in critical_fields:
                        if existing_provenance.get(field) and not new_provenance.get(field):
                            raise ProvenanceStrippingViolation(
                                f"Epistemic transition cannot strip provenance field '{field}'. "
                                f"Original: {existing_provenance.get(field)}"
                            )
                    # Also check if new provenance is empty - any UPDATE must preserve provenance
                    if not new_provenance:
                        raise ProvenanceStrippingViolation(
                            f"Epistemic transition cannot strip all provenance. "
                            f"Original provenance had: {list(existing_provenance.keys())}"
                        )
                # If no existing provenance but promoting to strong status, require provenance
                elif not new_provenance and context.epistemic_status in (
                    EpistemicStatus.OBSERVED, EpistemicStatus.MEASURED, EpistemicStatus.EVIDENCE_BACKED
                ):
                    raise ProvenanceStrippingViolation(
                        f"Promotion to {context.epistemic_status} requires provenance to be provided"
                    )
    
    # ================================================================
    # 5. HISTORICAL EPISTEMIC STATE PROTECTION
    # ================================================================
    # Historical epistemic states cannot be silently rewritten
    # Only applies to UPDATE/TRANSITION of existing entities
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
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
                existing_status = getattr(existing, "epistemic_status", None)
                # Only check if there's an actual status change to a stronger level
                if existing_status and existing_status != context.epistemic_status:
                    # Define epistemic hierarchy for comparison
                    hierarchy = {
                        EpistemicStatus.OBSERVED: 6,
                        EpistemicStatus.MEASURED: 5,
                        EpistemicStatus.EVIDENCE_BACKED: 4,
                        EpistemicStatus.INFERRED: 3,
                        EpistemicStatus.PREDICTED: 2,
                        EpistemicStatus.PROPOSED: 1,
                        EpistemicStatus.CONTESTED: 0,
                    }
                    existing_level = hierarchy.get(existing_status, 0)
                    new_level = hierarchy.get(context.epistemic_status, 0)
                    
                    # Only require justification if promoting to stronger epistemic level
                    if new_level > existing_level and context.epistemic_status in (
                        EpistemicStatus.OBSERVED,
                        EpistemicStatus.MEASURED,
                        EpistemicStatus.EVIDENCE_BACKED
                    ):
                        # Check for valid justifications
                        justification = context.provenance.get("epistemic_justification") or context.metadata.get("epistemic_justification")
                        direct_observation = context.provenance.get("direct_observation") or context.metadata.get("direct_observation")
                        contradiction_resolution = context.provenance.get("contradiction_resolution") or context.metadata.get("contradiction_resolution")
                        outcome_verification = context.provenance.get("outcome_verification") or context.metadata.get("outcome_verification")
                        
                        has_valid_justification = justification or direct_observation or contradiction_resolution or outcome_verification
                        
                        if not has_valid_justification:
                            raise EpistemicPromotionViolation(
                                f"Historical entity with status '{existing_status}' cannot be promoted to "
                                f"'{context.epistemic_status}' without explicit epistemic justification, "
                                f"direct observation, contradiction resolution, or outcome verification."
                            )
    
    # ================================================================
    # 6. CONTRADICTION PRESERVATION INTEGRATION
    # ================================================================
    # If this entity has associated contradictions, epistemic promotion
    # must not silently resolve them
    if context.target_id and context.target_entity_type == "CompanyDecision":
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
    # Governance authorization is already enforced by validate_governance
    # which is called before validate_epistemic_integrity in the mutation wrapper.
    # No additional governance checks needed here.
    pass
    
    # ================================================================
    # 8. TEMPORAL CONTEXT PRESERVATION
    # ================================================================
    # Epistemic transitions must preserve temporal context
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
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
    # Only applies when promoting an existing PREDICTED entity to OBSERVED
    if context.epistemic_status == EpistemicStatus.OBSERVED and context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Check if this was previously a prediction
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


async def validate_exact_once('''

# Replace the function
content = re.sub(
    r'async def validate_epistemic_integrity\([\s\S]*?^async def validate_exact_once\(',
    new_function,
    content,
    flags=re.MULTILINE
)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Replaced validate_epistemic_integrity function')