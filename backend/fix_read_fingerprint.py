with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix canonical_create to read fingerprint from entity if not provided
old_canonical_create = '''async def canonical_create(
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
            )'''

new_canonical_create = '''async def canonical_create(
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
    
    # Read fingerprint from entity if not provided as parameter
    fingerprint = fingerprint or getattr(entity, "fingerprint", None)
    
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
            )'''

content = content.replace(old_canonical_create, new_canonical_create)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed canonical_create to read fingerprint from entity')