with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ExternalOperation - remove inner import and fingerprint
old_eo = '''            # Create external operation
            from app.models.canonical_integration import ExternalOperation
            eo1 = ExternalOperation(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                external_operation_id="ext-op-123",
                operation_type="CREATE",
                target_entity_type="repository",
                target_external_id="test/repo",
                payload={"name": "test-repo", "private": True},
                state="completed",
                governance_verified=True,
                fingerprint=f"eo-{uuid.uuid4().hex[:16]}"
            )'''

new_eo = '''            # Create external operation
            eo1 = ExternalOperation(
                organization_id=org.id,
                connector_instance_id=ci_github.id,
                source_action_id=None,
                operation_type="create",
                target_entity_type="repository",
                target_external_id="test/repo",
                payload={"name": "test-repo", "private": True},
                state="completed",
                governance_verified=True
            )'''

content = content.replace(old_eo, new_eo)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed ExternalOperation')