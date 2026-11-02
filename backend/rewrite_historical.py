with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the historical check section and rewrite it completely
new_lines = []
i = 0
while i < len(lines):
    if i < len(lines) and '# 5. HISTORICAL EPISTEMIC STATE PROTECTION' in lines[i]:
        # Skip the old historical check section until the contradiction section
        new_lines.append(lines[i])  # # 5. HISTORICAL...
        new_lines.append(lines[i+1])  # =====...
        new_lines.append(lines[i+2])  # Historical...
        new_lines.append('    # DEBUG\n')
        new_lines.append('    print(f"DEBUG validate_epistemic_integrity: target_id={context.target_id}, mutation_type={context.mutation_type}, epistemic_status={context.epistemic_status}, provenance={context.provenance}")\n')
        
        # Skip until we hit the contradiction section
        i += 3  # Skip the comment, =====, and Historical... lines
        while i < len(lines) and '# 6. CONTRADICTION PRESERVATION INTEGRATION' not in lines[i]:
            i += 1
        # Now i points to the contradiction section, don't increment i, let the loop handle it
        continue
    else:
        new_lines.append(lines[i])
        i += 1

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Rewrote historical section')