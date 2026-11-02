with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug output to provenance check
old_provenance = '''    # ================================================================
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
                    )'''

new_provenance = '''    # ================================================================
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
                    )'''

content = content.replace(old_provenance, new_provenance)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added debug to provenance check')