with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix canonical_update to run validations first, then do database-level update
old = '''async def canonical_update(
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
        
        print(f"DEBUG: Update successful for entity_id={entity_id}, new_version={updated_entity.version if hasattr(updated_entity, 'version') else 'N/A'}")
        return MutationResult(success=True, entity=updated_entity, fingerprint=fingerprint, version=updated_entity.version)
    
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

new = '''async def canonical_update(
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
        update_values["version"] = expected_version + 1
    
    # Define the mutation function that does database-level optimistic update
    async def update_mutation_fn(db: AsyncSession) -> Any:
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
            # Fallback to standard ORM update (no version check)
            return await _execute_standard_update(db, model, entity_id, updates)
    
    # Call the canonical mutation boundary which runs all validations
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
        epistemic_status=updates.get("epistemic_status") or getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED),
        updates=updates,
    )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed canonical_update')