with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug around the contradiction preservation call
old = '''            # Contradiction preservation validation (Gate 6-E)
            await validate_contradiction_preservation('''

new = '''            # Contradiction preservation validation (Gate 6-E)
            print(f"DEBUG mutate: Calling validate_contradiction_preservation for {target_entity_type}")
            await validate_contradiction_preservation('''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added debug to mutate method')