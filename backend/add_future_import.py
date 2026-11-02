with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    content = f.read()

# Add from __future__ import annotations at the very top
if not content.startswith(b'from __future__ import annotations'):
    content = b'from __future__ import annotations\n\n' + content
    with open('app/intelligence/canonical_mutation.py', 'wb') as f:
        f.write(content)
    print("Added from __future__ import annotations")
else:
    print("Already has future import")