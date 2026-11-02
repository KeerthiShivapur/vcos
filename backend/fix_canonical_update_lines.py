with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Line 1493 is the mutate call start
# Line 1503 has provenance=provenance
# We need to insert the effective_provenance logic before line 1493
# And change line 1503

# Insert before line 1493 (0-indexed: 1492)
new_lines = lines[:1492]
new_lines.append('    # For contradiction entities, include updates in provenance for validation\n')
new_lines.append('    effective_provenance = provenance or {}\n')
new_lines.append('    if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction"):\n')
new_lines.append('        effective_provenance = {**effective_provenance, **updates}\n')
new_lines.append('\n')

# Add lines 1493-1506 but with provenance=effective_provenance
for i in range(1492, 1506):
    if i == 1502:  # Line 1503 (0-indexed: 1502)
        new_lines.append(lines[i].replace('provenance=provenance', 'provenance=effective_provenance'))
    else:
        new_lines.append(lines[i])

# Add the rest
new_lines.extend(lines[1506:])

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed canonical_update provenance merge')