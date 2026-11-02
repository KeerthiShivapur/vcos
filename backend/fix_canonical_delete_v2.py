with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Fix canonical_delete to run validations first, then do database-level update
old = b'''async def canonical_delete(
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

new = b'''async def canonical_delete(
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
    
    This function runs all validations (governance, temporal, provenance, epistemic, etc.)
    through the canonical mutation boundary, then executes a database-level optimistic DELETE.
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
    
    # Define the mutation function that does database-level optimistic delete
    async def delete_mutation_fn(db: AsyncSession) -> Any:
        if expected_version is not None and has_version:
            # Use database-level optimistic concurrency with WHERE version = :expected_version
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
            # Fallback to standard ORM delete (no version check)
            entity = await db.get(model, entity_id)
            if not entity:
                raise ValueError(f"Entity not found: {entity_type}:{entity_id}")
        
            await db.delete(entity)
            await db.flush()
            return {"deleted": True, "id": entity_id}
    
    # Call the canonical mutation boundary which runs all validations
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

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed canonical_delete')