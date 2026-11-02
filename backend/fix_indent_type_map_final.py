with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Fix line 2180 (index 2179): should be '        type_map = {' (8 spaces)
if lines[2179].startswith(b'            type_map = {'):
    lines[2179] = b'        type_map = {'

# Fix lines 2181-2193 (indices 2180-2193): should have 12 spaces
for i in range(2180, 2194):
    if i < len(lines):
        line = lines[i]
        if line.startswith(b'            ') and not line.startswith(b'            }'):
            lines[i] = b'            ' + line.lstrip()

# Fix line 2194 (index 2193): should be '        }' (8 spaces)
if lines[2193].startswith(b'    }'):
    lines[2193] = b'        }'

# Fix line 2195 (index 2194): should be '        model = type_map.get(entity_type)' (8 spaces)
if lines[2194].startswith(b'    model = type_map.get(entity_type)'):
    lines[2194] = b'        model = type_map.get(entity_type)'

# Fix line 2196 (index 2195): should be '        if not model:' (8 spaces)
if lines[2195].startswith(b'        if not model:'):
    lines[2195] = b'        if not model:'

# Fix line 2197 (index 2196): should be '            return None' (12 spaces)
if lines[2196].startswith(b'            return None'):
    lines[2196] = b'            return None'

# Fix line 2199 (index 2199): should be '        # For CompanyDecision...' (8 spaces)
if lines[2199].startswith(b'    # For CompanyDecision'):
    lines[2199] = b'        # For CompanyDecision, check by source_event_id instead of fingerprint'

content = b'\n'.join(lines)
with open('app/intelligence/canonical_mutation.py', 'wb') as f:
    f.write(content)
print('Fixed')