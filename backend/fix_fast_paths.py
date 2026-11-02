with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix 1: canonical_transition - move validation before fast path and handle InvalidStateTransition
old_transition_fast_path = b'''    # Use database-level optimistic concurrency for state transitions when version field exists
    if expected_version is not None and has_version:
        # Validate state transition first
        current_state = getattr(entity, state_field)
        validate_state_transition(entity_type, current_state, new_state)
        
        # Build update values with state change and version increment
        update_values = {
            state_field: new_state,
            "updated_at": utcnow(),
            "version": model.version + 1,
        }
        
        update_stmt = (
            update(model)
            .where(model.id == entity_id)
            .where(model.version == expected_version)
            .values(**update_values)
        )
        # Debug: print compiled SQL
        from sqlalchemy.dialects.postgresql import dialect as pg_dialect
        compiled = update_stmt.compile(dialect=pg_dialect(), compile_kwargs={"literal_binds": True})
        print(f"DEBUG SQL: {compiled}")
        
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

new_transition_fast_path = b'''    # Validate state transition FIRST (before any database operation)
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
        # Debug: print compiled SQL
        from sqlalchemy.dialects.postgresql import dialect as pg_dialect
        compiled = update_stmt.compile(dialect=pg_dialect(), compile_kwargs={"literal_binds": True})
        print(f"DEBUG SQL: {compiled}")
        
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

content = content.replace(old_transition_fast_path, new_transition_fast_path)

# Fix 2: canonical_update - add provenance validation before fast path
old_update_fast_path = b'''async def canonical_update(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    updates: dict,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Update an existing canonical entity through the boundary using database-level optimistic concurrency."""
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type: {entity_type}")
    
    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
    
    target_org_id = getattr(entity, "organization_id", None)
    
    # For UPDATE mutations, always use database-level optimistic concurrency when version field exists
    # Build the update values including version increment
    update_values = {**updates, "updated_at": utcnow()}
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version
    
    # Use database-level optimistic concurrency with WHERE version = :expected_version
    if expected_version is not None and has_version:
        update_values["version"] = expected_version + 1
        
        update_stmt = (
            update(model)
            .where(model.id == entity_id)
            .where(model.version == expected_version)
            .values(**update_values)
        )
        # Debug: print compiled SQL
        from sqlalchemy.dialects.postgresql import dialect as pg_dialect
        compiled = update_stmt.compile(dialect=pg_dialect(), compile_kwargs={"literal_binds": True})
        print(f"DEBUG SQL: {compiled}")
        
        result = await db.execute(update_stmt)
        await db.flush()
        print(f"DEBUG: rowcount={result.rowcount}, entity_id={entity_id}, expected_version={expected_version}")
        
        # Check rowcount to see if update succeeded
        if result.rowcount == 0:
            # No rows updated - version conflict or entity not found
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
                error="Entity not found after update",
                error_code="NotFound"
            )
        
        return MutationResult(success=True, entity=updated_entity, fingerprint=fingerprint, version=updated_entity.version)
    
    # Fallback for entities without version field - use standard mutation path with advisory lock
    print(f"DEBUG canonical_update: calling mutate with updates={updates} (no version field)")
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.UPDATE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=lambda db: _execute_standard_update(db, model, entity_id, updates),
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=updates.get("epistemic_status") or getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED),
        updates=updates,
    )'''

new_update_fast_path = b'''async def canonical_update(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    updates: dict,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Update an existing canonical entity through the boundary using database-level optimistic concurrency.
    
    This function runs all canonical validations (governance, temporal, provenance, epistemic,
    contradiction, exact-once, concurrency) through the CanonicalMutationBoundary, then executes
    a database-level optimistic UPDATE with WHERE version = :expected_version.
    """
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type: {entity_type}")
    
    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
    
    target_org_id = getattr(entity, "organization_id", None)
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version
    
    # Build update values for the mutation function
    update_values = {**updates, "updated_at": utcnow()}
    if has_version and expected_version is not None:
        # Use literal integer for next version (not column expression)
        update_values["version"] = expected_version + 1
    
    # Validate provenance for UPDATE mutations
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
    
    # Validate temporal integrity for UPDATE
    await validate_temporal_integrity(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        entity=entity,
        organization_id=caller.organization_id,
        mutation_type=MutationType.UPDATE,
        allow_supersession=False,
    )
    
    # Epistemic boundary validation
    epistemic_status = updates.get("epistemic_status") or getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
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
            mutation_type=MutationType.UPDATE,
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
            mutation_type=MutationType.UPDATE,
            provenance=provenance or {},
        ),
    )
    
    # Define the mutation function that does database-level optimistic UPDATE
    async def update_mutation_fn(db: AsyncSession) -> Any:
        if expected_version is not None and has_version:
            # Database-level optimistic UPDATE with WHERE version = :expected_version
            update_stmt = (
                update(model)
                .where(model.id == entity_id)
                .where(model.version == expected_version)
                .values(**update_values)
            )
            
            result = await db.execute(update_stmt)
            await db.flush()
            
            # Check rowcount to see if update succeeded
            if result.rowcount == 0:
                # No rows updated - version conflict or entity not found
                raise ConcurrencyViolation(
                    f"Stale version: expected {expected_version}, entity was modified concurrently"
                )
            
            # Fetch the updated entity
            updated_entity = await db.get(model, entity_id)
            if updated_entity is None:
                raise ValueError("Entity not found after update")
            
            return updated_entity
        else:
            # Fallback for entities without version field - standard ORM update
            return await _execute_standard_update(db, model, entity_id, updates)
    
    # Call the canonical mutation boundary which runs ALL validations:
    # governance, temporal, provenance, epistemic, contradiction, exact-once, concurrency
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.UPDATE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=update_mutation_fn,
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=epistemic_status,
        updates=updates,
    )'''

content = content.replace(old_update_fast_path, new_update_fast_path)

# Fix 3: canonical_delete - add provenance validation before fast path
old_delete_fast_path = b'''async def canonical_delete(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Delete a canonical entity through the boundary using database-level optimistic concurrency."""
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type: {entity_type}")

    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

    target_org_id = getattr(entity, "organization_id", None)
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version

    # Use database-level optimistic concurrency for delete when version field exists
    if expected_version is not None and has_version:
        delete_stmt = (
            delete(model)
            .where(model.id == entity_id)
            .where(model.version == expected_version)
        )
        
        result = await db.execute(delete_stmt)
        await db.flush()
        
        if result.rowcount == 0:
            return MutationResult(
                success=False, 
                error=f"Stale version: expected {expected_version}, entity was modified concurrently",
                error_code="ConcurrencyViolation"
            )
        
        return MutationResult(success=True, entity={"deleted": True, "id": entity_id}, fingerprint=fingerprint)
    
    # Fallback for entities without version field
    async def delete_fn(db: AsyncSession):
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
       
        await db.delete(entity)
        await db.flush()
        return {"deleted": True, "id": entity_id}
   
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.DELETE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=delete_fn,
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
    )'''

new_delete_fast_path = b'''async def canonical_delete(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Delete a canonical entity through the boundary using database-level optimistic concurrency.
    
    This function runs all canonical validations (governance, temporal, provenance, epistemic,
    contradiction, exact-once, concurrency) through the CanonicalMutationBoundary, then executes
    a database-level optimistic DELETE with WHERE version = :expected_version.
    """
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
        "CompanyGoal": CompanyGoal,
        "CompanyObjective": CompanyObjective,
        "CompanyInitiative": CompanyInitiative,
        "CompanyIntent": CompanyIntent,
        "Project": Project,
        "Task": Task,
        "Employee": Employee,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type: {entity_type}")

    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

    target_org_id = getattr(entity, "organization_id", None)
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version
    
    # Validate provenance for DELETE mutations
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
    
    # Validate temporal integrity for DELETE
    await validate_temporal_integrity(
        db=db,
        entity_type=entity_type,
        entity_id=entity_id,
        entity=entity,
        organization_id=caller.organization_id,
        mutation_type=MutationType.DELETE,
        allow_supersession=False,
    )
    
    # Epistemic boundary validation
    epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
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
            mutation_type=MutationType.DELETE,
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
            mutation_type=MutationType.DELETE,
            provenance=provenance or {},
        ),
    )
    
    # Define the mutation function that does database-level optimistic DELETE
    async def delete_mutation_fn(db: AsyncSession) -> Any:
        if expected_version is not None and has_version:
            # Database-level optimistic DELETE with WHERE version = :expected_version
            delete_stmt = (
                delete(model)
                .where(model.id == entity_id)
                .where(model.version == expected_version)
            )
            
            result = await db.execute(delete_stmt)
            await db.flush()
            
            if result.rowcount == 0:
                raise ConcurrencyViolation(
                    f"Stale version: expected {expected_version}, entity was modified concurrently"
                )
            
            return {"deleted": True, "id": entity_id}
        else:
            # Fallback for entities without version field - standard ORM delete
            entity = await db.get(model, entity_id)
            if not entity:
                raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
        
            await db.delete(entity)
            await db.flush()
            return {"deleted": True, "id": entity_id}
    
    # Call the canonical mutation boundary which runs ALL validations:
    # governance, temporal, provenance, epistemic, contradiction, exact-once, concurrency
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.DELETE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=delete_mutation_fn,
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
    )'''

content = content.replace(old_delete_fast_path, new_delete_fast_path)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)

print("Fixed canonical_update, canonical_transition, canonical_delete fast paths")