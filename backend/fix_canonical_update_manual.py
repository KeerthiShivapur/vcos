with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the canonical_update function and fix the provenance merge
mutate_call_start = -1
# Look for the line with "return await canonical_mutation_boundary.mutate"
for i, line in enumerate(lines):
    if 'return await canonical_mutation_boundary.mutate' in line:
        # Check if we're in canonical_update by looking back
        context = ''.join(lines[max(0,i-50):i])
        if 'canonical_update' in context:
            mutate_call_start = i
            break

if mutate_call_start == -1:
    print("Could not find mutate call in canonical_update")
    exit(1)

# Find the provenance=provenance line
provenance_line = -1
for i in range(mutate_call_start, min(mutate_call_start + 20, len(lines))):
    if 'provenance=provenance' in lines[i]:
        provenance_line = i
        break

if provenance_line == -1:
    print("Could not find provenance=provenance line")
    exit(1)

# Insert the effective_provenance logic before the mutate call
indent = '    '
new_lines = lines[:mutate_call_start]
new_lines.append(indent + '# For contradiction entities, include updates in provenance for validation\n')
new_lines.append(indent + 'effective_provenance = provenance or {}\n')
new_lines.append(indent + 'if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction"):\n')
new_lines.append(indent + '    effective_provenance = {**effective_provenance, **updates}\n')
new_lines.append('\n')

# Now add the mutate call with effective_provenance
# Find the end of the mutate call
paren_count = 0
mutate_call_end = mutate_call_start
for i in range(mutate_call_start, len(lines)):
    for ch in lines[i]:
        if ch == '(':
            paren_count += 1
        elif ch == ')':
            paren_count -= 1
            if paren_count == 0:
                mutate_call_end = i
                break
    if paren_count == 0:
        break

# Replace the mutate call with the new one
# We need to change provenance=provenance to provenance=effective_provenance
for i in range(mutate_call_start, mutate_call_end + 1):
    if 'provenance=provenance' in lines[i]:
        new_lines.append(lines[i].replace('provenance=provenance', 'provenance=effective_provenance'))
    else:
        new_lines.append(lines[i])

# Add the rest
new_lines.extend(lines[mutate_call_end + 1:])

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed canonical_update provenance merge')