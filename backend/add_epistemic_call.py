with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add call to validate_epistemic_integrity after validate_epistemic_boundary
old_call = '''            # Epistemic boundary
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

            # Contradiction preservation validation (Gate 6-E)'''

new_call = '''            # Epistemic boundary (Gate 6-B: basic promotion rules)
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

            # Contradiction preservation validation (Gate 6-E)'''

content = content.replace(old_call, new_call)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added validate_epistemic_integrity call to mutate')