with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update canonical_update to pass updates in provenance for contradiction entities
old = '''    async def update_fn(db: AsyncSession):
        # Re-fetch entity in the mutation transaction
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

        # Apply updates
        for key, value in updates.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        entity.updated_at = utcnow()
        if hasattr(entity, "version"):
            entity.version += 1

        await db.flush()
        return entity

    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.UPDATE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=update_fn,
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=provenance,
        required_permissions=required_permissions,
        entity=entity,
    )'''

new = '''    # For contradiction entities, include updates in provenance for validation
    effective_provenance = provenance or {}
    if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction"):
        effective_provenance = {**effective_provenance, **updates}

    async def update_fn(db: AsyncSession):
        # Re-fetch entity in the mutation transaction
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

        # Apply updates
        for key, value in updates.items():
            if hasattr(entity, key):
                setattr(entity, key, value)

        entity.updated_at = utcnow()
        if hasattr(entity, "version"):
            entity.version += 1

        await db.flush()
        return entity

    return await canonical_mutation_boundary.mutate(
        db=db,
        caller=caller,
        target_entity_type=entity_type,
        mutation_type=MutationType.UPDATE,
        target_id=entity_id,
        target_organization_id=target_org_id,
        mutation_fn=update_fn,
        expected_version=expected_version,
        fingerprint=fingerprint,
        provenance=effective_provenance,
        required_permissions=required_permissions,
        entity=entity,
    )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated canonical_update to pass updates in provenance for contradictions')