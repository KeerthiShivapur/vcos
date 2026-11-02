with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the transition_fn in canonical_transition
for i, line in enumerate(lines):
    if 'async def transition_fn' in line and 'canonical_transition' in ''.join(lines[max(0,i-50):i]):
        fn_start = i
        break

# Find the validate_state_transition call
for i in range(fn_start, fn_start + 30):
    if i < len(lines) and 'validate_state_transition(entity_type, entity.state, new_state)' in lines[i]:
        validate_line = i
        break

# Find the old_state = entity.state line
for i in range(fn_start, fn_start + 30):
    if i < len(lines) and 'old_state = entity.state' in lines[i]:
        old_state_line = i
        break

# Find the entity.state = new_state line
for i in range(fn_start, fn_start + 30):
    if i < len(lines) and 'entity.state = new_state' in lines[i]:
        new_state_line = i
        break

print(f"validate_line: {validate_line+1}")
print(f"old_state_line: {old_state_line+1}")
print(f"new_state_line: {new_state_line+1}")

# Now replace these lines
# First, add the state_field determination before transition_fn
# Find the line before transition_fn
for i in range(fn_start - 1, fn_start - 20, -1):
    if 'target_org_id = getattr(entity, "organization_id", None)' in lines[i]:
        insert_after = i
        break

# Insert the state_field logic
new_lines = lines[:insert_after + 1]
new_lines.append('\n')
new_lines.append('    # Determine the state field name for this entity type\n')
new_lines.append('    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"\n')
new_lines.append('\n')

# Add the rest of the lines up to validate_line
new_lines.extend(lines[insert_after + 1:validate_line])

# Replace the validate_state_transition line
new_lines.append('        # Validate state transition\n')
new_lines.append('        current_state = getattr(entity, state_field)\n')
new_lines.append('        validate_state_transition(entity_type, current_state, new_state)\n')

# Replace old_state = entity.state
new_lines.append('        old_state = current_state\n')

# Replace entity.state = new_state
new_lines.append('        setattr(entity, state_field, new_state)\n')

# Add the rest from after new_state_line
new_lines.extend(lines[new_state_line + 1:])

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed canonical_transition to use status for contradictions')