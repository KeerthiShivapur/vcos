with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the _create_entity function and canonical_create function
old_create_entity = '''async def _create_entity(db: AsyncSession, entity: Any, provenance: dict = None) -> Any:
    """Create a new entity in the database."""
    if provenance:
        entity.provenance = provenance
    db.add(entity)
    await db.flush()
    return entity


async def canonical_create(
    db: AsyncSession,
    caller: CallerAccess,
    entity: Any,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Create a new canonical entity through the boundary."""
    # Read epistemic_status from entity if present
    entity_epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity.__class__.__name__,
        mutation_type=MutationType.CREATE,
        target_id=entity.id,
        target_organization_id=entity.organization_id,
        mutation_fn=lambda db: _create_entity(db, entity, provenance),
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=entity_epistemic_status,
    )'''

new_create_entity = '''async def _create_entity(db: AsyncSession, entity: Any, provenance: dict = None) -> Any:
    """Create a new entity in the database."""
    if provenance:
        entity.provenance = provenance
    db.add(entity)
    await db.flush()
    return entity


async def _get_existing_by_fingerprint(
    db: AsyncSession,
    entity_type: str,
    fingerprint: str,
    organization_id: str,
) -> Optional[Any]:
    """Check if an entity with the same fingerprint already exists."""
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
        return None
    result = await db.execute(
        select(model).where(
            model.organization_id == organization_id,
            model.fingerprint == fingerprint,
        )
    )
    return result.scalar_one_or_none()


async def canonical_create(
    db: AsyncSession,
    caller: CallerAccess,
    entity: Any,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Create a new canonical entity through the boundary."""
    # Read epistemic_status from entity if present
    entity_epistemic_status = getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)
    
    # Idempotent create: check for existing entity with same fingerprint
    if fingerprint:
        existing = await _get_existing_by_fingerprint(
            db=db,
            entity_type=entity.__class__.__name__,
            fingerprint=fingerprint,
            organization_id=entity.organization_id,
        )
        if existing:
            # Return existing entity instead of creating duplicate
            return MutationResult(
                success=True,
                entity=existing,
                fingerprint=fingerprint,
                provenance=provenance or {},
            )
    
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity.__class__.__name__,
        mutation_type=MutationType.CREATE,
        target_id=entity.id,
        target_organization_id=entity.organization_id,
        mutation_fn=lambda db: _create_entity(db, entity, provenance),
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=entity_epistemic_status,
    )'''

content = content.replace(old_create_entity, new_create_entity)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated canonical_create with idempotent logic')