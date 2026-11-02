with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix 1: In canonical_transition, add provenance validation and catch InvalidStateTransition
old_transition_validation = b'''    # Validate state transition FIRST (before any database operation)
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
    await validate_provenance(db, transition_context)'''

new_transition_validation = b'''    # Validate state transition FIRST (before any database operation)
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
    await validate_provenance(db, transition_context_full)'''

content = content.replace(old_transition_validation, new_transition_validation)

# Fix 2: In canonical_update, add provenance validation
old_update_validation = b'''    # Validate provenance for UPDATE mutations
    await _validate_provenance_references(db, CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.UPDATE,
        provenance=provenance or {},
    ))'''

new_update_validation = b'''    # Validate provenance for UPDATE mutations
    await _validate_provenance_references(db, CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.UPDATE,
        provenance=provenance or {},
    ))
    
    # Also validate required provenance fields for UPDATE
    update_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.UPDATE,
        provenance=provenance or {},
    )
    await validate_provenance(db, update_context)'''

content = content.replace(old_update_validation, new_update_validation)

# Fix 3: In canonical_delete, add provenance validation
old_delete_validation = b'''    # Validate provenance for DELETE mutations
    await _validate_provenance_references(db, CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.DELETE,
        provenance=provenance or {},
    ))'''

new_delete_validation = b'''    # Validate provenance for DELETE mutations
    await _validate_provenance_references(db, CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.DELETE,
        provenance=provenance or {},
    ))
    
    # Also validate required provenance fields for DELETE
    delete_context = CanonicalMutationContext(
        caller=caller,
        tenant_id=caller.organization_id,
        governance_scope_ids=caller.visible_scope_ids,
        permissions=await caller.get_permissions(db),
        target_entity_type=entity_type,
        target_id=entity_id,
        mutation_type=MutationType.DELETE,
        provenance=provenance or {},
    )
    await validate_provenance(db, delete_context)'''

content = content.replace(old_delete_validation, new_delete_validation)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed validation handling in canonical_transition, canonical_update, canonical_delete")