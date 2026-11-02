with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug at the very start of the function
old = '''    """
    if context.target_entity_type != "CompanyDecisionContradiction":
        return True

    if not context.target_id:
        return True  # CREATE - no existing entity to validate'''

new = '''    """
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