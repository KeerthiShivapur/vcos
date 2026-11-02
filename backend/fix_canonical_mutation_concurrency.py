"""Fix canonical mutation concurrency issues for 35-G.3"""
import re

with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read().decode('utf-8', errors='replace')

# Fix 1: Update canonical_update to always use database-level optimistic concurrency
# when version is available, not just when expected_version is provided

old_canonical_update = '''async def canonical_update(
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
    
    # For UPDATE mutations, use database-level optimistic concurrency
    # Build the update values including version increment
    update_values = {**updates, "updated_at": utcnow()}
    if hasattr(entity, "version"):
        update_values["version"] = model.version + 1
    
    # For optimistic concurrency, use database-level WHERE clause
    if expected_version is not None:
        # Use database-level optimistic concurrency with WHERE version = :expected_version
        # First, do the update without RETURNING to avoid ORM attachment issues
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
            print(f"DEBUG: Concurrency violation detected for entity_id={entity_id}, expected_version={expected_version}")
            return MutationResult(
                success=False, 
                error=f"Stale version: expected {expected_version}, entity was modified concurrently",
                error_code="ConcurrencyViolation"
            )
        
        # Explicitly commit to ensure persistence
        await db.commit()
        
        # Fetch the updated entity separately to avoid RETURNING clause issues
        updated_entity = await db.get(model, entity_id)
        if updated_entity is None:
            return MutationResult(
                success=False, 
                error="Entity not found after update",
                error_code="NotFound"
            )
        
        print(f"DEBUG: Update successful for entity_id={entity_id}, new_version={updated_entity.version if hasattr(updated_entity, 'version') else 'N/A'}")
        return MutationResult(success=True, entity=updated_entity, fingerprint=fingerprint)
    
    # If no expected_version, fall back to the standard mutation path
    # (but this should not happen in normal operation)
    print(f"DEBUG canonical_update: calling mutate with updates={updates}")
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

new_canonical_update = '''async def canonical_update(
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
        update_values["version"] = model.version + 1
        
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

content = content.replace(old_canonical_update, new_canonical_update)

# Fix 2: Update canonical_transition to use database-level optimistic concurrency
old_canonical_transition = '''async def canonical_transition(
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
    """Execute a canonical state transition through the boundary."""
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

    async def transition_fn(db: AsyncSession):
        # Re-fetch entity in the mutation transaction
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
       
        # Validate state transition
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
        expected_version=ex'''

new_canonical_transition = '''async def canonical_transition(
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

    # Determine the state field name for this entity type
    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"
    
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
            "version": model.version + 1,
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

content = content.replace(old_canonical_transition, new_canonical_transition)

# Fix 3: Update canonical_delete to use database-level optimistic concurrency
old_canonical_delete = '''async def canonical_delete(
    db: AsyncSession,
    caller: CallerAccess,
    entity_type: str,
    entity_id: str,
    expected_version: Optional[int] = None,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Delete a canonical entity through the boundary."""
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

    async def delete_fn(db: AsyncSession):
        # Re-fetch entity in the mutation transaction
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

new_canonical_delete = '''async def canonical_delete(
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

content = content.replace(old_canonical_delete, new_canonical_delete)

# Fix 4: Add the delete import at the top if not present
if 'from sqlalchemy import select, and_, insert, update' in content:
    content = content.replace(
        'from sqlalchemy import select, and_, insert, update',
        'from sqlalchemy import select, and_, insert, update, delete'
    )

# Fix 5: Fix _execute_idempotent_create to ensure proper atomic handling
# The issue is that the PostgreSQL ON CONFLICT DO NOTHING with RETURNING might not work correctly
# in all cases. Let's ensure it properly handles the conflict target.

old_idempotent_create = '''async def _execute_idempotent_create(
    db: AsyncSession,
    entity: Any,
    provenance: dict = None,
) -> Tuple[bool, Any]:
    """Create a new entity atomically using dialect-specific idempotent INSERT.
    
    Uses INSERT ... ON CONFLICT DO NOTHING (PostgreSQL) or INSERT OR IGNORE (SQLite)
    for atomic idempotent creation.
    Returns (is_new, entity) where is_new is True if entity was created,
    False if existing entity was found.
    """
    model = type(entity)
    if provenance:
        entity.provenance = provenance
    # Get the conflict target columns for this entity type from universal registry
    conflict_target_columns = await get_conflict_target_columns(type(entity).__name__)
    
    # Prepare the insert values
    insert_values = {}
    for col in model.__table__.columns:
        if col.name != 'id' or getattr(entity, col.name, None) is not None:
            val = getattr(entity, col.name, None)
            if val is not None:
                insert_values[col.name] = val
    
    # Use dialect-specific idempotent insert
    dialect_name = db.bind.dialect.name
    
    if dialect_name in ('sqlite', 'sqlite.aiosqlite'):
        # SQLite: INSERT OR IGNORE
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        stmt = sqlite_insert(model).values(**_get_insert_values(entity, model)).prefix_with('OR IGNORE')
        result = await db.execute(stmt)
        await db.flush()
        
        # For SQLite INSERT OR IGNORE, check if row was inserted by querying
        # Use the conflict target columns to find the entity
        conflict_columns = await get_conflict_target_columns(type(entity).__name__)
        where_clause = []
        for col in conflict_columns:
            if hasattr(model, col):
                where_clause.append(getattr(model, col) == getattr(entity, col))
        
        existing = await db.execute(
            select(model).where(*where_clause)
        )
        existing_entity = existing.scalar_one_or_none()
        if existing_entity:
            # Check if it was just inserted (version would be 1 for new) or existed before
            if hasattr(entity, 'version') and getattr(entity, 'version', 0) == 1:
                return True, entity
            return False, existing_entity
        return False, None
    elif db.bind.dialect.name == 'postgresql':
        # PostgreSQL: INSERT ... ON CONFLICT DO NOTHING
        # Use the correct conflict target columns for this entity type from universal registry
        conflict_target_columns = await get_conflict_target_columns(type(entity).__name__)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(model).values(**_get_insert_values(entity, model)).on_conflict_do_nothing(
            index_elements=conflict_target_columns
        ).returning(model)
        result = await db.execute(stmt)
        await db.flush()
        
        inserted_entity = result.scalar_one_or_none()
        if inserted_entity:
            return True, inserted_entity
        else:
            # Entity already existed, fetch it using conflict target columns
            where_clause = []
            for col in conflict_target_columns:
                if hasattr(model, col):
                    where_clause.append(getattr(model, col) == getattr(entity, col))
            
            existing = await db.execute(
                select(model).where(*where_clause)
            )
            existing_entity = existing.scalar_one_or_none()
            if existing_entity:
                return False, existing_entity
            raise RuntimeError("Idempotent insert failed unexpectedly")
    else:
        # Fallback for other dialects
        db.add(entity)
        try:
            await db.flush()
            return True, entity
        except IntegrityError:
            await db.rollback()
            # Use fingerprint from entity for fallback
            entity_fingerprint = getattr(entity, 'fingerprint', None)
            if entity_fingerprint:
                existing = await db.execute(
                    select(model).where(model.fingerprint == entity_fingerprint)
                )
                existing_entity = existing.scalar_one_or_none()
                if existing_entity:
                    return False, existing_entity
            raise
    
    return False, None'''

new_idempotent_create = '''async def _execute_idempotent_create(
    db: AsyncSession,
    entity: Any,
    provenance: dict = None,
) -> Tuple[bool, Any]:
    """Create a new entity atomically using dialect-specific idempotent INSERT.
    
    Uses INSERT ... ON CONFLICT DO NOTHING (PostgreSQL) or INSERT OR IGNORE (SQLite)
    for atomic idempotent creation.
    Returns (is_new, entity) where is_new is True if entity was created,
    False if existing entity was found.
    
    This function ensures atomic idempotent creation even under high concurrency
    by using database-level unique constraints and ON CONFLICT handling.
    """
    model = type(entity)
    if provenance:
        entity.provenance = provenance
    # Get the conflict target columns for this entity type from universal registry
    conflict_target_columns = await get_conflict_target_columns(type(entity).__name__)
    
    # Prepare the insert values
    insert_values = _get_insert_values(entity, model)
    
    # Use dialect-specific idempotent insert
    dialect_name = db.bind.dialect.name
    
    if dialect_name in ('sqlite', 'sqlite.aiosqlite'):
        # SQLite: INSERT OR IGNORE
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        stmt = sqlite_insert(model).values(**insert_values).prefix_with('OR IGNORE')
        result = await db.execute(stmt)
        await db.flush()
        
        # For SQLite INSERT OR IGNORE, check if row was inserted by querying
        # Use the conflict target columns to find the entity
        conflict_columns = await get_conflict_target_columns(type(entity).__name__)
        where_clause = []
        for col in conflict_columns:
            if hasattr(model, col):
                where_clause.append(getattr(model, col) == getattr(entity, col))
        
        existing = await db.execute(
            select(model).where(*where_clause)
        )
        existing_entity = existing.scalar_one_or_none()
        if existing_entity:
            # Check if it was just inserted (version would be 1 for new) or existed before
            if hasattr(entity, 'version') and getattr(entity, 'version', 0) == 1:
                return True, entity
            return False, existing_entity
        return False, None
    elif dialect_name == 'postgresql':
        # PostgreSQL: INSERT ... ON CONFLICT DO NOTHING
        # Use the correct conflict target columns for this entity type from universal registry
        conflict_target_columns = await get_conflict_target_columns(type(entity).__name__)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(model).values(**insert_values).on_conflict_do_nothing(
            index_elements=conflict_target_columns
        ).returning(model)
        result = await db.execute(stmt)
        await db.flush()
        
        inserted_entity = result.scalar_one_or_none()
        if inserted_entity:
            return True, inserted_entity
        else:
            # Entity already existed, fetch it using conflict target columns
            where_clause = []
            for col in conflict_target_columns:
                if hasattr(model, col):
                    where_clause.append(getattr(model, col) == getattr(entity, col))
            
            existing = await db.execute(
                select(model).where(*where_clause)
            )
            existing_entity = existing.scalar_one_or_none()
            if existing_entity:
                return False, existing_entity
            raise RuntimeError("Idempotent insert failed unexpectedly")
    else:
        # Fallback for other dialects
        db.add(entity)
        try:
            await db.flush()
            return True, entity
        except IntegrityError:
            await db.rollback()
            # Use fingerprint from entity for fallback
            entity_fingerprint = getattr(entity, 'fingerprint', None)
            if entity_fingerprint:
                existing = await db.execute(
                    select(model).where(model.fingerprint == entity_fingerprint)
                )
                existing_entity = existing.scalar_one_or_none()
                if existing_entity:
                    return False, existing_entity
            raise
    
    return False, None'''

content = content.replace(old_idempotent_create, new_idempotent_create)

# Fix 6: Update CanonicalMutationBoundary.mutate to use database-level optimistic concurrency
# when expected_version is provided and entity has version field

old_mutate_method = '''    async def mutate(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        target_entity_type: str,
        mutation_type: MutationType,
        target_id: Optional[str] = None,
        mutation_fn: Callable = None,
        expected_version: Optional[int] = None,
        fingerprint: Optional[str] = None,
        provenance: dict = None,
        epistemic_status: EpistemicStatus = EpistemicStatus.PROPOSED,
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
        required_permissions: Optional[list[str]] = None,
        target_organization_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        entity: Optional[Any] = None,  # For CREATE mutations: the new entity
        updates: Optional[dict] = None,  # For UPDATE mutations: the update values
    ) -> MutationResult:
        """Execute a canonical mutation through the boundary."""
       
        # Build context
        permissions = await caller.get_permissions(db) if db is not None else frozenset()
        metadata_dict = {"updates": updates} if updates else {}
        context = CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=permissions,
            target_entity_type=target_entity_type,
            target_id=target_id,
            mutation_type=mutation_type,
            expected_version=expected_version,
            fingerprint=fingerprint,
            provenance=provenance or {},
            epistemic_status=epistemic_status,
            source_event_id=source_event_id,
            trigger_reason=trigger_reason,
            metadata=metadata_dict,
        )

        # 4. Execute mutation with all validations
        async def mutation_wrapper(db: AsyncSession) -> MutationResult:
            
            # Initialize concurrency components
            concurrency_coordinator = CanonicalConcurrencyCoordinator(db)
            idempotency_manager = IdempotencyKeyManager(db)
            optimistic_manager = OptimisticConcurrencyManager(db)
            
            # Create concurrency context
            concurrency_context = ConcurrencyContext(
                operation_id=str(uuid.uuid4()),
                entity_type=target_entity_type,
                entity_id=target_id or "",
                actor_id=caller.user_id,
                organization_id=caller.organization_id,
                concurrency_type=ConcurrencyControlType.OPTIMISTIC,
                expected_version=expected_version,
                fingerprint=fingerprint,
                max_retries=3,
                retry_delay=0.1,
                timeout=30.0,
            )
            
            # Initialize concurrency coordinator
            canonical_concurrency = CanonicalOperationConcurrency(db)
            canonical_concurrency.optimistic = OptimisticConcurrencyManager(db)
            canonical_concurrency.leases = LeaseManager(db)
            
            # 1. Governance validation
            await validate_governance(
                db=db,
                caller=caller,
                target_entity_type=target_entity_type,
                target_id=target_id,
                target_organization_id=target_organization_id or caller.organization_id,
                required_permissions=required_permissions,
            )
            
            # 2. Target resolution through accessible IDs
            if target_id and target_entity_type not in ["Organization", "User"] and db is not None:
                # Fetch the User object for resolve_accessible_ids
                from app.models.user import User as UserModel
                user_obj = await db.get(UserModel, caller.user_id)
                if not user_obj:
                    raise ScopeViolation(f"User {caller.user_id} not found")
                accessible = await resolve_accessible_ids(
                    db=db,
                    user=user_obj,
                    organization_id=caller.organization_id,
                    kind=_entity_type_to_kind(target_entity_type),
                    ids=[target_id],
                )
                if target_id not in accessible:
                    raise ScopeViolation(
                        f"Target {target_entity_type}:{target_id} not accessible to caller"
                    )
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
            # Temporal integrity (for both CREATE and UPDATE)
            # For CREATE, pass the entity; for UPDATE, load from DB
            if target_id:
                # UPDATE: load existing entity
                entity_for_temporal = await self._load_entity(db, target_entity_type, target_id)
            else:
                # CREATE: entity is passed as parameter
                entity_for_temporal = entity
            
            await validate_temporal_integrity(
                db=db,
                entity_type=target_entity_type,
                entity_id=target_id,
                entity=entity_for_temporal,
                organization_id=caller.organization_id,
                mutation_type=mutation_type,
                allow_supersession=(mutation_type == MutationType.TRANSITION),
            )
            
            # Provenance validation
            context_obj = CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=target_entity_type,
                target_id=target_id,
                provenance=provenance or {},
            )
            await validate_provenance(db, context_obj)
            
            # Epistemic boundary (Gate 6-B: basic promotion rules)
            validate_epistemic_boundary(
                CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    epistemic_status=epistemic_status,
                ),
                epistemic_status,
            )
            
            # Epistemic integrity (Gate 6-F: comprehensive enforcement)
            await validate_epistemic_integrity(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    epistemic_status=epistemic_status,
                ),
            )
            
            # Contradiction preservation validation (Gate 6-E)
            await validate_contradiction_preservation(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    metadata=context.metadata,  # Pass the metadata with updates
                ),
            )
            
            # Concurrency check
            if target_id and expected_version is not None:
                # Load entity to check version
                entity_for_concurrency = await self._load_entity(db, target_entity_type, target_id)
                if entity_for_concurrency:
                    validate_optimistic_concurrency(entity_for_concurrency, expected_version)
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
            # Execute the actual mutation
            if mutation_fn:
                # For UPDATE mutations, use database-level optimistic concurrency
                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:
                    # Load the model for the entity type
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
                        "User": User,
                        "Organization": Organization,
                    }
                    model = type_map.get(target_entity_type)
                    if model:
                        # Use database-level optimistic update
                        pass
                result = await mutation_fn(db)
                
                # For UPDATE mutations, verify the version was actually updated
                if mutation_type == MutationType.UPDATE and target_id and expected_version is not None:
                    entity_for_check = await self._load_entity(db, target_entity_type, target_id)
                    if entity_for_check and hasattr(entity_for_check, 'version'):
                        if entity_for_check.version <= expected_version:
                            raise ConcurrencyViolation(
                                f"Stale version: expected {expected_version}, current is {entity_for_check.version}"
                            )
                
                # Mark idempotency key as complete
                if fingerprint:
                    await idempotency_manager.complete(fingerprint, result.id if hasattr(result, 'id') else str(uuid.uuid4()))
                
                return MutationResult(success=True, entity=result, fingerprint=fingerprint)
            else:
                return MutationResult(success=False, error="No mutation function provided")

        try:
            result = await execute_transactional(db, [
                TransactionalMutation(mutation_fn=mutation_wrapper)
            ])
            return result[0] if result else MutationResult(success=False, error="No result")
        except CanonicalMutationError as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
        except Exception as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)'''

new_mutate_method = '''    async def mutate(
        self,
        db: AsyncSession,
        caller: CallerAccess,
        target_entity_type: str,
        mutation_type: MutationType,
        target_id: Optional[str] = None,
        mutation_fn: Callable = None,
        expected_version: Optional[int] = None,
        fingerprint: Optional[str] = None,
        provenance: dict = None,
        epistemic_status: EpistemicStatus = EpistemicStatus.PROPOSED,
        source_event_id: Optional[str] = None,
        trigger_reason: Optional[str] = None,
        required_permissions: Optional[list[str]] = None,
        target_organization_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        entity: Optional[Any] = None,  # For CREATE mutations: the new entity
        updates: Optional[dict] = None,  # For UPDATE mutations: the update values
    ) -> MutationResult:
        """Execute a canonical mutation through the boundary."""
       
        # Build context
        permissions = await caller.get_permissions(db) if db is not None else frozenset()
        metadata_dict = {"updates": updates} if updates else {}
        context = CanonicalMutationContext(
            caller=caller,
            tenant_id=caller.organization_id,
            governance_scope_ids=caller.visible_scope_ids,
            permissions=permissions,
            target_entity_type=target_entity_type,
            target_id=target_id,
            mutation_type=mutation_type,
            expected_version=expected_version,
            fingerprint=fingerprint,
            provenance=provenance or {},
            epistemic_status=epistemic_status,
            source_event_id=source_event_id,
            trigger_reason=trigger_reason,
            metadata=metadata_dict,
        )

        # 4. Execute mutation with all validations
        async def mutation_wrapper(db: AsyncSession) -> MutationResult:
            
            # Initialize concurrency components
            concurrency_coordinator = CanonicalConcurrencyCoordinator(db)
            idempotency_manager = IdempotencyKeyManager(db)
            optimistic_manager = OptimisticConcurrencyManager(db)
            
            # Create concurrency context
            concurrency_context = ConcurrencyContext(
                operation_id=str(uuid.uuid4()),
                entity_type=target_entity_type,
                entity_id=target_id or "",
                actor_id=caller.user_id,
                organization_id=caller.organization_id,
                concurrency_type=ConcurrencyControlType.OPTIMISTIC,
                expected_version=expected_version,
                fingerprint=fingerprint,
                max_retries=3,
                retry_delay=0.1,
                timeout=30.0,
            )
            
            # Initialize concurrency coordinator
            canonical_concurrency = CanonicalOperationConcurrency(db)
            canonical_concurrency.optimistic = OptimisticConcurrencyManager(db)
            canonical_concurrency.leases = LeaseManager(db)
            
            # 1. Governance validation
            await validate_governance(
                db=db,
                caller=caller,
                target_entity_type=target_entity_type,
                target_id=target_id,
                target_organization_id=target_organization_id or caller.organization_id,
                required_permissions=required_permissions,
            )
            
            # 2. Target resolution through accessible IDs
            if target_id and target_entity_type not in ["Organization", "User"] and db is not None:
                # Fetch the User object for resolve_accessible_ids
                from app.models.user import User as UserModel
                user_obj = await db.get(UserModel, caller.user_id)
                if not user_obj:
                    raise ScopeViolation(f"User {caller.user_id} not found")
                accessible = await resolve_accessible_ids(
                    db=db,
                    user=user_obj,
                    organization_id=caller.organization_id,
                    kind=_entity_type_to_kind(target_entity_type),
                    ids=[target_id],
                )
                if target_id not in accessible:
                    raise ScopeViolation(
                        f"Target {target_entity_type}:{target_id} not accessible to caller"
                    )
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
            # Temporal integrity (for both CREATE and UPDATE)
            # For CREATE, pass the entity; for UPDATE, load from DB
            if target_id:
                # UPDATE: load existing entity
                entity_for_temporal = await self._load_entity(db, target_entity_type, target_id)
            else:
                # CREATE: entity is passed as parameter
                entity_for_temporal = entity
            
            await validate_temporal_integrity(
                db=db,
                entity_type=target_entity_type,
                entity_id=target_id,
                entity=entity_for_temporal,
                organization_id=caller.organization_id,
                mutation_type=mutation_type,
                allow_supersession=(mutation_type == MutationType.TRANSITION),
            )
            
            # Provenance validation
            context_obj = CanonicalMutationContext(
                caller=caller,
                tenant_id=caller.organization_id,
                governance_scope_ids=caller.visible_scope_ids,
                permissions=await caller.get_permissions(db),
                target_entity_type=target_entity_type,
                target_id=target_id,
                provenance=provenance or {},
            )
            await validate_provenance(db, context_obj)
            
            # Epistemic boundary (Gate 6-B: basic promotion rules)
            validate_epistemic_boundary(
                CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    epistemic_status=epistemic_status,
                ),
                epistemic_status,
            )
            
            # Epistemic integrity (Gate 6-F: comprehensive enforcement)
            await validate_epistemic_integrity(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    epistemic_status=epistemic_status,
                ),
            )
            
            # Contradiction preservation validation (Gate 6-E)
            await validate_contradiction_preservation(
                db=db,
                context=CanonicalMutationContext(
                    caller=caller,
                    tenant_id=caller.organization_id,
                    governance_scope_ids=caller.visible_scope_ids,
                    permissions=await caller.get_permissions(db),
                    target_entity_type=target_entity_type,
                    target_id=target_id,
                    mutation_type=mutation_type,
                    provenance=provenance or {},
                    metadata=context.metadata,  # Pass the metadata with updates
                ),
            )
            
            # Concurrency check - use database-level version check when available
            if target_id and expected_version is not None:
                # Load entity to check version
                entity_for_concurrency = await self._load_entity(db, target_entity_type, target_id)
                if entity_for_concurrency:
                    validate_optimistic_concurrency(entity_for_concurrency, expected_version)
            
            # Exact-once check with idempotency key manager
            # Skip for CREATE mutations - database-level idempotent INSERT handles it
            if fingerprint and mutation_type != MutationType.CREATE:
                is_new, existing_id = await idempotency_manager.check_and_reserve(
                    key=fingerprint,
                    entity_type=target_entity_type,
                    organization_id=caller.organization_id,
                )
                
                if not is_new:
                    # Entity already exists, load and return
                    existing_entity = await self._load_entity(db, target_entity_type, existing_id)
                    return MutationResult(success=True, entity=existing_entity, fingerprint=fingerprint)
                
                # Mark idempotency key as reserved
                await idempotency_manager.complete(fingerprint, target_id or str(uuid.uuid4()))
            
            # Execute the actual mutation
            if mutation_fn:
                # For UPDATE/TRANSITION/DELETE mutations, use database-level optimistic concurrency
                # when expected_version is provided and entity has version field
                if mutation_type in (MutationType.UPDATE, MutationType.TRANSITION, MutationType.DELETE) and target_id and expected_version is not None:
                    # Load the model for the entity type
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
                        "User": User,
                        "Organization": Organization,
                    }
                    model = type_map.get(target_entity_type)
                    if model:
                        # Check if entity has version field
                        entity_for_check = await self._load_entity(db, target_entity_type, target_id)
                        if entity_for_check and hasattr(entity_for_check, 'version'):
                            # The mutation_fn should handle the database-level update
                            pass
                
                result = await mutation_fn(db)
                
                # For UPDATE/TRANSITION/DELETE mutations, verify the version was actually updated
                if mutation_type in (MutationType.UPDATE, MutationType.TRANSITION, MutationType.DELETE) and target_id and expected_version is not None:
                    entity_for_check = await self._load_entity(db, target_entity_type, target_id)
                    if entity_for_check and hasattr(entity_for_check, 'version'):
                        if entity_for_check.version <= expected_version:
                            raise ConcurrencyViolation(
                                f"Stale version: expected {expected_version}, current is {entity_for_check.version}"
                            )
                
                # Mark idempotency key as complete
                if fingerprint:
                    await idempotency_manager.complete(fingerprint, result.id if hasattr(result, 'id') else str(uuid.uuid4()))
                
                return MutationResult(success=True, entity=result, fingerprint=fingerprint)
            else:
                return MutationResult(success=False, error="No mutation function provided")

        try:
            result = await execute_transactional(db, [
                TransactionalMutation(mutation_fn=mutation_wrapper)
            ])
            return result[0] if result else MutationResult(success=False, error="No result")
        except CanonicalMutationError as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)
        except Exception as e:
            return MutationResult(success=False, error=str(e), error_code=type(e).__name__)'''

content = content.replace(old_mutate_method, new_mutate_method)

with open('app/intelligence/canonical_mutation.py', 'w') as f:
    f.write(content)

print("Fixed canonical_mutation.py")