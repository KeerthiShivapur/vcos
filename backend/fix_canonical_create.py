with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update canonical_create to pass entity's epistemic_status
old_create = '''async def canonical_create(
    db: AsyncSession,
    caller: CallerAccess,
    entity: Any,
    fingerprint: Optional[str] = None,
    provenance: dict = None,
    required_permissions: list[str] = None,
) -> MutationResult:
    """Create a new canonical entity through the boundary."""
    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity.__class__.__name__,
        mutation_type=MutationType.CREATE,
        target_id=entity.id,
        target_organization_id=entity.organization_id,
        mutation_fn=lambda db: _create_entity(db, entity),
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
    )'''

new_create = '''async def canonical_create(
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
        mutation_fn=lambda db: _create_entity(db, entity),
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
        epistemic_status=entity_epistemic_status,
    )'''

content = content.replace(old_create, new_create)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated canonical_create to pass entity epistemic_status')