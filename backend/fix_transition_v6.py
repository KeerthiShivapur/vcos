with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the canonical_transition function - replace the validation section
old_code = b'''    # Validate state transition FIRST (before any database operation)
    # This ensures invalid transitions are caught and returned as failed MutationResult
    current_state = getattr(entity, state_field)
    try:
        validate_state_transition(entity_type, current_state, new_state)
    except InvalidStateTransition as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Validate provenance for TRANSITION mutations
    # Create a context with the provenance for validation
    transition_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.TRANSITION,
        provenance=provenance or {},
    )
    await validate_provenance(db, transition_context)

    # Also validate required provenance fields for TRANSITION
    # This ensures required provenance fields like authorization_id, source_commitment_id are present
    transition_context_full = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.TRANSITION,
        provenance=provenance or {},
    )
    await validate_provenance(db, transition_context_full)

    # Validate temporal integrity for TRANSITION
    await validate_temporal_integrity(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        entity=entity,
        organization_id=caller.organization_id,
        mutation_type=MutationType.TRANSITION,
        allow_supersession=True,
    )
    
    # Epistemic boundary validation
    validate_epistemic_boundary(
        CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=await caller.get_permissions(db),
            target_entity_type=entity_type,
            target_id=entity_id,
            epistemic_status=epistemic_status,
        ),
        epistemic_status,
    )'''

new_code = b'''    # Read epistemic_status from entity if present
    epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    
    # Validate provenance for TRANSITION mutations FIRST (before state validation)
    # This ensures missing required provenance fields are caught before state validation
    transition_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.TRANSITION,
        provenance=provenance or {},
        epistemic_status=epistemic_status,
    )
    await validate_provenance(db, transition_context)

    # Validate temporal integrity for TRANSITION
    await validate_temporal_integrity(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        entity=entity,
        organization_id=caller.organization_id,
        mutation_type=MutationType.TRANSITION,
        allow_supersession=True,
    )
    
    # Epistemic boundary validation
    validate_epistemic_boundary(
        CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=await caller.get_permissions(db),
            target_entity_type=entity_type,
            target_id=entity_id,
            epistemic_status=epistemic_status,
        ),
        epistemic_status,
    )
    
    # Epistemic integrity (Gate 6-F)
    await validate_epistemic_integrity(
        db=db,
        context=CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=await caller.get_permissions(db),
            target_entity_type=entity_type,
            target_id=entity_id,
            mutation_type=MutationType.TRANSITION,
            provenance=provenance or {},
            epistemic_status=epistemic_status,
        ),
    )
    
    # Contradiction preservation validation
    await validate_contradiction_preservation(
        db=db,
        context=CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=await caller.get_permissions(db),
            target_entity_type=entity_type,
            target_id=entity_id,
            mutation_type=MutationType.TRANSITION,
            provenance=provenance or {},
        ),
    )

    # Validate state transition FIRST (before any database operation)
    # This ensures invalid transitions are caught and returned as failed MutationResult
    current_state = getattr(entity, state_field)
    try:
        validate_state_transition(entity_type, current_state, new_state)
    except InvalidStateTransition as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)'''

content = content.replace(old_code, new_code)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed canonical_transition validation order")