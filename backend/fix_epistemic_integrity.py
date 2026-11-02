with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the validate_epistemic_integrity function to properly handle CREATE vs UPDATE
# and not apply historical checks to CREATE operations
old_historical = '''    # ================================================================
    # 5. HISTORICAL EPISTEMIC STATE PROTECTION
    # ================================================================
    # Historical epistemic states cannot be silently rewritten
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
                            )'''

new_historical = '''    # ================================================================
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
                        # Promoting historical record to stronger epistemic status requires evidence
                        justification = context.provenance.get("epistemic_justification") or context.metadata.get("epistemic_justification")
                        if not justification:
                            raise EpistemicPromotionViolation(
                                f"Historical entity with status '{existing_status}' cannot be promoted to "
                                f"'{context.epistemic_status}' without explicit epistemic justification."
                            )'''

content = content.replace(old_historical, new_historical)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed historical check')