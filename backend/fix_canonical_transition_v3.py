with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix canonical_transition to run validations first, then do database-level update
old = b'''async def canonical_transition(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    new_state: str,
    expected_version: Optional[int] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
    trigger_reason: Optional[str] = None,
) -> MutationResult:
    """Execute a canonical state transition through the boundary using database-level optimistic concurrency."""
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type for transition: {entity_type}")

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

    # Use database-level optimistic concurrency for state transitions when version field exists
    if expected_version is not None and has_version:
        # Validate state transition first
        current_state = getattr(entity, state_field)
        validate_state_transition(entity_type, current_state, new_state)
        
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
            entity_id=entity.id,
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
       
        # Validate state transition
        current_state = getattr(entity, state_field)
        validate_state_transition(entity_type, current_state, new_state)
        old_state = current_state
        setattr(entity, state_field, new_state)
        entity.updated_at = utcnow()
        if hasattr(entity, "version"):
            entity.version += 1
       
        # Record transition in history
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

new = b'''async def canonical_transition(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    new_state: str,
    expected_version: Optional[int] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
    trigger_reason: Optional[str] = None,
) -> MutationResult:
    """Execute a canonical state transition through the boundary using database-level optimistic concurrency.
    
    This function runs all validations (governance, temporal, provenance, epistemic, etc.)
    through the canonical mutation boundary, then executes a database-level optimistic UPDATE.
    """
    # Fetch entity to get organization_id for tenant isolation check
    type_map = {
        "CompanyDecision": CompanyDecision,
        "CompanyAuthorization": CompanyAuthorization,
        "CompanyCommitment": CompanyCommitment,
        "CompanyAction": CompanyAction,
        "CompanyDecisionAlternative": CompanyDecisionAlternative,
        "CompanyDecisionContradiction": CompanyDecisionContradiction,
    }
    model = type_map.get(entity_type)
    if not model:
        raise ValueError(f"Unknown entity type for transition: {entity_type}")

    entity = await db.get(model, entity_id)
    if not entity:
        raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

    target_org_id = getattr(entity, "organization_id", None)

    # Determine the state field name for this entity type
    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
    
    # Check if entity supports versioning
    has_version = hasattr(entity, "version")
    current_version = getattr(entity, "version", None) if has_version else None
    
    # If expected_version not provided but entity has version, use current version
    if expected_version is None and current_version is not None:
        expected_version = current_version
    
    # Validate state transition first (will be re-validated in mutation boundary)
    current_state = getattr(entity, state_field)
    validate_state_transition(entity_type, current_state, new_state)
    
    # Build update values for the mutation function
    update_values = {
        state_field: new_state,
        "updated_at": utcnow(),
    }
    if has_version and expected_version is not None:
        update_values["version"] = expected_version + 1
    
    # Define the mutation function that does database-level optimistic update
    async def transition_mutation_fn(db: AsyncSession) -> Any:
        if expected_version is not None and has_version:
            # Use database-level optimistic concurrency with WHERE version = :expected_version
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
                raise ConcurrencyViolation(
                    f"Stale version: expected {expected_version}, entity was modified concurrently"
                )
            
            # Fetch the updated entity
            updated_entity = await db.get(model, entity_id)
            if updated_entity is None:
                raise ValueError("Entity not found after transition")
            
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
            
            return updated_entity
        else:
            # Fallback to standard ORM update (no version check)
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
    
    # Call the canonical mutation boundary which runs all validations
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.TRANSITION,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=transition_mutation_fn,
        expected_version=expected_version,
        provenance=provenance,
        required_permissions=required_permissions,
        trigger_reason=trigger_reason,
        entity=entity,
    )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed canonical_transition')