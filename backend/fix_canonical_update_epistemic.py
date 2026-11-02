with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update canonical_update to pass epistemic_status from updates or entity
old_update = '''    # For contradiction entities, include updates in provenance for validation
    effective_provenance = provenance or {}
    if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction"):
        effective_provenance = {**effective_provenance, **updates}

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

new_update = '''    # For contradiction entities, include updates in provenance for validation
    effective_provenance = provenance or {}
    if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction"):
        effective_provenance = {**effective_provenance, **updates}

    # Pass epistemic_status from updates if present, else from entity
    entity_epistemic_status = updates.get("epistemic_status") or getattr(entity, "epistemic_status", EpistemicStatus.PROPOSED)

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
        epistemic_status=entity_epistemic_status,
    )'''

content = content.replace(old_update, new_update)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated canonical_update to pass epistemic_status')