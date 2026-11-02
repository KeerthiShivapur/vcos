with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The DELETE check is at lines 690-695 but inside the UPDATE/TRANSITION block (line 684)
# We need to move it outside. Let me rewrite the whole section properly.

# Find the exact lines to replace
new_lines = lines[:682]  # Up to line 682 (if not context.target_id:)

# Add the DELETE check
new_lines.append('\n')
new_lines.append('    # 1. Check if trying to delete contradiction without supersession\n')
new_lines.append('    if context.mutation_type == MutationType.DELETE:\n')
new_lines.append('        # Load the existing contradiction\n')
new_lines.append('        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)\n')
new_lines.append('        if contradiction:\n')
new_lines.append('            raise ContradictionPreservationViolation(\n')
new_lines.append('                f"Contradiction {context.target_id} cannot be deleted. "\n')
new_lines.append('                f"Contradictions must be resolved via supersession, not deletion."\n')
new_lines.append('            )\n')
new_lines.append('\n')

# Then add the UPDATE/TRANSITION block
new_lines.append('    # For UPDATE/TRANSITION of contradiction, check preservation rules\n')
new_lines.append('    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):\n')
new_lines.append('        # Load the existing contradiction\n')
new_lines.append('        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)\n')
new_lines.append('        if not contradiction:\n')
new_lines.append('            return True  # Entity doesn\'t exist, no preservation needed\n')
new_lines.append('\n')
new_lines.append('        # 2. Check if trying to overwrite side_a or side_b without supersession\n')
new_lines.append('        if context.mutation_type == MutationType.UPDATE:\n')

# Now add the rest from line 699 onwards (the UPDATE logic)
# Skip the old DELETE check (lines 690-695) and the UPDATE check start (line 697-698)
# Continue from line 699 (side_a = ...)
for i in range(698, len(lines)):
    new_lines.append(lines[i])
    # Stop at the end of the function (before _validate_temporal_intervals)
    if i < len(lines) - 1 and 'async def _validate_temporal_intervals' in lines[i+1]:
        break

# Add the remaining lines
for i in range(i+1, len(lines)):
    new_lines.append(lines[i])

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Rewrote the function properly')