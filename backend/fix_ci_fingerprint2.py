with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ConnectorInstance - remove fingerprint (the new code still has it)
content = content.replace(
    '''                    connected_at=utcnow(),
                    fingerprint="ci-" + uuid.uuid4().hex[:16]
                )''',
    '''                    connected_at=utcnow()
                )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed fingerprint from ConnectorInstance')