with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix SyncCursor - updated_at -> last_updated_at
content = content.replace(
    '''            sc1 = SyncCursor(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                entity_type="repository",
                cursor_value="2024-01-15T10:00:00Z",
                cursor_type="timestamp",
                updated_at=utcnow()
            )''',
    '''            sc1 = SyncCursor(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                entity_type="repository",
                cursor_value="2024-01-15T10:00:00Z",
                cursor_type="timestamp",
                last_updated_at=utcnow()
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed SyncCursor field')