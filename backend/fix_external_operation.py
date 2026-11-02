with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ExternalOperation - remove fingerprint
content = content.replace(
    '''            eo1 = ExternalOperation(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                operation_type="create",
                target_entity_type="repository",
                target_external_id="test/repo",
                payload={"name": "test-repo", "private": True},
                state="completed",
                governance_verified=True,
                fingerprint=f"eo-{uuid.uuid4().hex[:16]}"
            )''',
    '''            eo1 = ExternalOperation(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                operation_type="create",
                target_entity_type="repository",
                target_external_id="test/repo",
                payload={"name": "test-repo", "private": True},
                state="completed",
                governance_verified=True
            )'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed fingerprint from ExternalOperation')