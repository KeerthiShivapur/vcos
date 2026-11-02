with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug at the very start of the function
old = '''async def validate_contradiction_preservation(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """
    Validate that contradiction preservation rules are enforced.
   
    Rules enforced:
    1. Contradiction cannot be deleted or overwritten without supersession
    2. Both sides of a contradiction must be preserved
    3. Provenance of both sides must be preserved
    4. Cross-tenant contradiction creation is blocked
    5. Contradiction provenance cannot be silently modified
    5. Supersession does not erase contradiction history
    """
    if context.target_entity_type != "CompanyDecisionContradiction":
        return True

    if not context.target_id:
        return True  # CREATE - no existing entity to validate'''

new = '''async def validate_contradiction_preservation(
    db: AsyncSession,
    context: CanonicalMutationContext,
) -> bool:
    """
    Validate that contradiction preservation rules are enforced.
   
    Rules enforced:
    1. Contradiction cannot be deleted or overwritten without supersession
    2. Both sides of a contradiction must be preserved
    3. Provenance of both sides must be preserved
    4. Cross-tenant contradiction creation is blocked
    5. Contradiction provenance cannot be silently modified
    5. Supersession does not erase contradiction history
    """
    print(f"DEBUG validate_contradiction_preservation ENTRY: target_entity_type={context.target_entity_type}, target_id={context.target_id}, mutation_type={context.mutation_type}")
    if context.target_entity_type != "CompanyDecisionContradiction":
        print(f"DEBUG validate_contradiction_preservation: Not a contradiction entity, returning True")
        return True

    if not context.target_id:
        print(f"DEBUG validate_contradiction_preservation: No target_id, returning True")
        return True  # CREATE - no existing entity to validate'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added entry debug to contradiction preservation validation')