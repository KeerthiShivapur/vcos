with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the contradiction preservation validation to check DELETE
old = '''    # For UPDATE/TRANSITION of contradiction, check preservation rules
    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if not contradiction:
            return True  # Entity doesn't exist, no preservation needed

        # 1. Check if trying to delete/overwrite the contradiction without supersession
        if context.mutation_type == MutationType.DELETE:
            raise ContradictionPreservationViolation(
                f"Contradiction {context.target_id} cannot be deleted. "
                f"Contradictions must be resolved via supersession, not deletion."
            )'''

new = '''    # For DELETE of contradiction, check preservation rules
    if context.mutation_type == MutationType.DELETE:
        # Load the existing contradiction
        contradiction = await db.get(CompanyDecisionContradiction, context.target_id)
        if contradiction:
            raise ContradictionPreservationViolation(
                f"Contradiction {context.target_id} cannot be deleted. "
                f"Contradictions must be resolved via supersession, not deletion."
            )

    # For UPDATE/TRANSITION of contradiction, check preservation rules
    if context.mutation_type in (MutationType.UPDATE, MutationType.TRANSITION):'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed DELETE check in contradiction preservation validation')