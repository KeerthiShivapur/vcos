with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _create_entity to save provenance to entity
old_create_entity = '''async def _create_entity(db: AsyncSession, entity: Any) -> Any:
    """Create a new entity in the database."""
    db.add(entity)
    await db.flush()
    return entity'''

new_create_entity = '''async def _create_entity(db: AsyncSession, entity: Any, provenance: dict = None) -> Any:
    """Create a new entity in the database."""
    if provenance:
        entity.provenance = provenance
    db.add(entity)
    await db.flush()
    return entity'''

content = content.replace(old_create_entity, new_create_entity)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed _create_entity to save provenance')