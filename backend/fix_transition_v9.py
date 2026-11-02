with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix the canonical_transition fast path - wrap all validation in try/except and define update_values early
old_code = b'''    # Read epistemic_status from entity if present
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
    try:
        await validate_provenance(db, transition_context)
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Validate temporal integrity for TRANSITION
    try:
        await validate_temporal_integrity(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            entity=entity,
            organization_id=caller.organization_id,
            mutation_type=MutationType.TRANSITION,
            allow_supersession=True,
        )
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Epistemic boundary validation
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Epistemic integrity (Gate 6-F)
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Contradiction preservation validation
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Validate state transition FIRST (before any database operation)
    # This ensures invalid transitions are caught and returned as failed MutationResult
    current_state = getattr(entity, state_field)
    try:
        validate_state_transition(entity_type, current_state, new_state)
    except InvalidStateTransition as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Epistemic integrity (Gate 6-F)
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Contradiction preservation validation
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Use database-level optimistic concurrency for state transitions when version field exists
    if expected_version is not None and has_version:
        # Build update values with state change and version increment
        update_values = {
            state_field: new_state,
            "updated_at": utcnow(),
            "version": expected_version + 1,
        }
        
        update_stmt = (
            update(model)
            .where(model.id == entity_id)
            .where(model.version == expected_version)
            .values(**update_values)
        )
        
        result = await db.execute(update_stmt)
        await db.flush()
        print(f"DEBUG: rowcount={result.rowcount}, entity_id={entity_id}, expected_version={expected_version}")
        
        # Check rowcount to see if update succeeded
        if result.rowcount == 0:
            return MutationResult(
                success=False, 
                error=f"Stale version: expected {expected_version}, entity was modified concurrently",
                error_code="ConcurrencyViolation"
            )
        
        # Fetch the updated entity
        updated_entity = await db.get(model, entity_id)
        if updated_entity is None:
            return MutationResult(
                success=False, 
                error="Entity not found after transition",
                error_code="NotFound"
            )
        
        # Record transition in history
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=caller.organization_id,
            entity_type=entity_type.lower().replace("company", ""),
            entity_id=entity_id,
            entity_label=getattr(entity, "title", str(entity.id))[:300],
            field="state",
            old_value=current_state,
            new_value=new_state,
            reason=f"State transition: {current_state} -> {new_state}",
            source_event_id=f"state_transition:{new_state}",
            changed_at=utcnow(),
        )
        db.add(history)
        await db.flush()
        
        return MutationResult(success=True, entity=updated_entity, fingerprint=None, version=updated_entity.version)
    
    # Fallback for entities without version field - use standard mutation path
    async def transition_fn(db: AsyncSession):
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
       
        current_state = getattr(entity, state_field)
        validate_state_transition(entity_type, current_state, new_state)
        old_state = current_state
        setattr(entity, state_field, new_state)
        entity.updated_at = utcnow()
        if hasattr(entity, "version"):
            entity.version += 1
       
        from app.models.execution_strategy import StrategicHistory
        history = StrategicHistory(
            organization_id=caller.organization_id,
            entity_type=entity_type.lower().replace("company", ""),
            entity_id=entity.id,
            entity_label=getattr(entity, "title", str(entity.id))[:300],
            field="state",
            old_value=old_state,
            new_value=new_state,
            reason=f"State transition: {old_state} -> {new_state}",
            source_event_id=f"state_transition:{new_state}",
            changed_at=utcnow(),
        )
        db.add(history)
       
        await db.flush()
        return entity
   
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.TRANSITION,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=transition_fn,
        expected_version=expected_version,
        provenance=provenance,
        required_permissions=required_permissions,
        trigger_reason=trigger_reason,
        entity=entity,
    )'''

new_code = b'''    # Read epistemic_status from entity if present
    epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    
    # Build update values for the fast path (needed before validation in case of early return)
    update_values = {
        state_field: new_state,
        "updated_at": utcnow(),
        "version": expected_version + 1,
    }
    
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
    try:
        await validate_provenance(db, transition_context)
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Validate temporal integrity for TRANSITION
    try:
        await validate_temporal_integrity(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            entity=entity,
            organization_id=caller.organization_id,
            mutation_type=MutationType.TRANSITION,
            allow_supersession=True,
        )
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Epistemic boundary validation
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Epistemic integrity (Gate 6-F)
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Contradiction preservation validation
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Validate state transition FIRST (before any database operation)
    # This ensures invalid transitions are caught and returned as failed MutationResult
    current_state = getattr(entity, state_field)
    try:
        validate_state_transition(entity_type, current_state, new_state)
    except InvalidStateTransition as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Epistemic integrity (Gate 6-F)
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Contradiction preservation validation
    try:
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
    except CanonicalMutationError as e:
        return MutationResult(success=False, error=str(e), error_code=type(e).__name__)

    # Use database-level optimistic concurrency for state transitions when version field exists
    if expected_version is not None and has_version:
        # Build update values with state change and version increment
        update_values = {
            state_field: new_state,
            "updated_at": utcnow(),
            "version": expected_version + 1,
        }'''

content = content.replace(old_code, new_code)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed canonical_transition error handling and update_values definition")