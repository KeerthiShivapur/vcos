with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Normalize line endings
content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')

lines = content.split(b'\n')

# Fix all indentation issues in the file
# The pattern we need: function definitions at 4 spaces, body at 8 spaces, nested at 12 spaces

fixed_lines = []
in_load_entity = False
in_mutate = False
in_get_entity = False

for i, line in enumerate(lines):
    stripped = line.lstrip()
    
    # Detect function starts
    if b'async def _load_entity' in line:
        in_load_entity = True
        in_mutate = False
        in_get_entity = False
    elif b'async def mutate' in line:
        in_mutate = True
        in_load_entity = False
        in_get_entity = False
    elif b'def get_entity' in line or b'async def get_entity' in line or b'    async def _load_entity' in line:
        # These are function definitions at 4 spaces
        pass
    
    # Fix indentation for the load_entity function body
    if in_load_entity:
        if line.strip() == b'type_map = {':
            fixed_lines.append(b'        type_map = {')
        elif line.strip() == b'}':
            # Check if this is the closing of type_map (not the function)
            if fixed_lines and b'"CanonicalOperation"' in fixed_lines[-1]:
                fixed_lines.append(b'        }')
            else:
                fixed_lines.append(line)
        elif b'model = type_map.get' in line and line.startswith(b'    ') and not line.startswith(b'        '):
            fixed_lines.append(b'        ' + line.lstrip())
        elif b'if not model:' in line and line.startswith(b'    ') and not line.startswith(b'        '):
            fixed_lines.append(b'        ' + line.lstrip())
        elif b'return None' in line and line.startswith(b'    ') and not line.startswith(b'        '):
            fixed_lines.append(b'        ' + line.lstrip())
        elif b'return await db.get(model, entity_id)' in line and line.startswith(b'    ') and not line.startswith(b'        '):
            fixed_lines.append(b'        ' + line.lstrip())
        else:
            fixed_lines.append(line)
            
        # Detect end of _load_entity function
        if line.strip() == b'' and fixed_lines and fixed_lines[-1] == b'        return await db.get(model, entity_id)':
            in_load_entity = False
    else:
        fixed_lines.append(line)

# Write back
with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(b'\n'.join(fixed_lines))

print('Fixed all indentation')