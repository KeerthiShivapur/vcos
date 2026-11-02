with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\postgres_resolver.py', 'rb') as f:
    content = f.read()

# Find all occurrences of the pattern
import re
matches = [(m.start(), content[m.start():m.start()+80]) for m in re.finditer(b'all\(\s*\[', content)]
for m in matches:
    print(f'Found at {m.start()}: {m}')

# Fix the specific issue: line 96 has a closing ) that should be ]
# Let's read the file and fix it
with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\postgres_resolver.py', 'rb') as f:
    content = f.read()

# Find and fix the specific pattern
old = b'return all([\n            self.reachable,\n            self.authenticated,\n            self.version_supported,\n            self.extensions_available,\n            self.privileges_sufficient,\n            self.database_creatable,\n            self.schema_initializable,\n            self.storage_sufficient,\n            self.connection_capacity,\n            self.health_acceptable,\n        )'

new = b'return all([\n            self.reachable,\n            self.authenticated,\n            self.version_supported,\n            self.extensions_available,\n            self.privileges_sufficient,\n            self.database_creatable,\n            self.schema_initializable,\n            self.storage_sufficient,\n            self.connection_capacity,\n            self.health_acceptable,\n        ])'

content = content.replace(
    b'return all([\n            self.reachable,\n            self.authenticated,\n            self.version_supported,\n            self.extensions_available,\n            self.privileges_sufficient,\n            self.database_creatable,\n            self.schema_initializable,\n            self.storage_sufficient,\n            self.connection_capacity,\n            self.health_acceptable,\n        )',
    b'return all([\n            self.reachable,\n            self.authenticated,\n            self.version_supported,\n            self.extensions_available,\n            self.privileges_sufficient,\n            self.database_creatable,\n            self.schema_initializable,\n            self.storage_sufficient,\n            self.connection_capacity,\n            self.health_acceptable,\n        ])'
)

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\scale\\postgres\\postgres_resolver.py', 'wb') as f:
    f.write(content)
    
print('Fixed!')