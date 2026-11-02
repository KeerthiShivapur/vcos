with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the duplicated code block 
old_block = '''    # Cross-tenant contradiction creation validation
    if context.mutation_type == MutationType.CREATE:
        # Check if any provenance references cross tenant boundaries
        for field in ["decision_id", "lesson_memory_id", "precedent_decision_id"]:
            provenance_value = context.provenance.get(field) or context.metadata.get(field)
            if provenance_value:
                # Would need to validate cross-tenant references here
                pass
   
if other_current:
            print(f"DEBUG: Raising TemporalViolation for {entity_type}, other_current.id={other_current.id}, entity.id={entity.id if entity_id else 'new'}")
            raise TemporalViolation(
                f"Multiple current {entity_type} states not allowed. "
                f"Existing: {other_current.id} (state: {other_current.state}), "
                f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
                f"Use supersession to transition."
            )

            return True

async def _validate_temporal_intervals('''

new_block = '''    # Cross-tenant contradiction creation validation
    if context.mutation_type == MutationType.CREATE:
        # Check if any provenance references cross tenant boundaries
        for field in ["decision_id", "lesson_memory_id", "precedent_decision_id"]:
            provenance_value = context.provenance.get(field) or context.metadata.get(field)
            if provenance_value:
                # Would need to validate cross-tenant references here
                pass

async def _validate_temporal_intervals('''

content = content.replace(old_block, new_block)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Removed duplicated code block')