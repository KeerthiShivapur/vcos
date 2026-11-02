with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix test_12_revoked_authorization_blocks_operation - use 'superseded' instead of 'revoked'
old = '''    instance = await _create_connector_instance(pg_db_session, org_id, "github")
        
        # Create authorization then revoke it
        from app.models.execution_strategy import CompanyAuthorization
        auth = CompanyAuthorization(
            organization_id=org_id,
            authorization_type="full",
            title="Test Authorization",
            rationale="Test",
            state="revoked",  # Revoked
            scope_type="organization",
            scope_id=org_id,
            approved_by=access.employee_id,
            approved_at=utcnow(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

new = '''        instance = await _create_connector_instance(pg_db_session, org_id, "github")
        
        # Create authorization then revoke it (supersede)
        from app.models.execution_strategy import CompanyAuthorization
        auth = CompanyAuthorization(
            organization_id=org_id,
            authorization_type="full",
            title="Test Authorization",
            rationale="Test",
            state="superseded",  # Superseded (valid state)
            scope_type="organization",
            scope_id=org_id,
            approved_by=access.employee_id,
            approved_at=utcnow(),
            fingerprint=f"fp-{uuid.uuid4().hex[:16]}",
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')