# Fix the canonical_mutation.py indentation issue
with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the problematic function
old_code = '''    if other_current:
            print(f"DEBUG: Raising TemporalViolation for {entity_type}, other_current.id={other_current.id}, entity.id={entity.id}")
            raise TemporalViolation(
                f"Multiple current {entity_type} states not allowed. "
                f"Existing: {other_current.id} (state: {other_current.state}), "
                f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
                f"Use supersession to transition."
            )
    
    return True


async def _validate_temporal_intervals('''

new_code = '''    if other_current:
            print(f"DEBUG: Raising TemporalViolation for {entity_type}, other_current.id={other_current.id}, entity.id={entity.id}")
            raise TemporalViolation(
                f"Multiple current {entity_type} states not allowed. "
                f"Existing: {other_current.id} (state: {other_current.state}), "
                f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
                f"Use supersession to transition."
            )
    
    return True


async def _validate_temporal_intervals('''

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content.replace(old_code, new_code))

print('Done')