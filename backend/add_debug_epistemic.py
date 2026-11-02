with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug output to validate_epistemic_integrity
old_historical_start = '''    # ================================================================
    # 5. HISTORICAL EPISTEMIC STATE PROTECTION
    # ================================================================
    # Historical epistemic states cannot be silently rewritten
    # Only applies to UPDATE/TRANSITION of existing entities
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):'''

new_historical_start = '''    # ================================================================
    # 5. HISTORICAL EPISTEMIC STATE PROTECTION
    # ================================================================
    # Historical epistemic states cannot be silently rewritten
    # Only applies to UPDATE/TRANSITION of existing entities
    # DEBUG
    print(f"DEBUG validate_epistemic_integrity: target_id={context.target_id}, mutation_type={context.mutation_type}, epistemic_status={context.epistemic_status}, provenance={context.provenance}")
    # Only applies to UPDATE/TRANSITION of existing entities
    if context.target_id and context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):'''

content = content.replace(old_historical_start, new_historical_start)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added debug output')