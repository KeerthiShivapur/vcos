with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the function and add debug print after the docstring
for i, line in enumerate(lines):
    if 'async def validate_contradiction_preservation' in line:
        start = i
        break

# Find the end of the docstring (line with just """)
for i in range(start, start + 20):
    if i < len(lines) and '"""' in lines[i] and i > start:
        docstring_end = i
        break

# Insert debug print after the docstring
lines.insert(docstring_end + 1, '    print(f"DEBUG validate_contradiction_preservation ENTRY: target_entity_type={context.target_entity_type}, target_id={context.target_id}, mutation_type={context.mutation_type}")\n')

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Added debug print to function')