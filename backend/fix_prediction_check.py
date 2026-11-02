with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the prediction/outcome confusion check to only apply when promoting existing PREDICTED entity
old_prediction = '''    # ================================================================
    # 9. PREDICTION/OUTCOME CONFUSION PREVENTION
    # ================================================================
    # A prediction cannot become an actual outcome without verification
    if context.epistemic_status == EpistemicStatus.OBSERVED:
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
                        )'''

new_prediction = '''    # ================================================================
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
                        )'''

content = content.replace(old_prediction, new_prediction)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed prediction check')