with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix test_14_unknown_external_outcome_preserved - execute operation before verifying
old = '''        operation = await external_operation_service.create_operation(
            db=pg_db_session,
            organization_id=org_id,
            connector_instance_id=instance.id,
            request=request,
            caller=access,
        )
        
        # Simulate verification failure (ambiguous result)
        result = await external_operation_service.verify_operation(
            db=pg_db_session,
            operation_id=operation.id,
            external_result={"partial": True, "status": "unknown"},  # Ambiguous
            caller=access,
        )'''

new = '''        operation = await external_operation_service.create_operation(
            db=pg_db_session,
            organization_id=org_id,
            connector_instance_id=instance.id,
            request=request,
            caller=access,
        )
        
        # Execute the operation to move it to completed state
        await external_operation_service.execute_operation(
            db=pg_db_session,
            operation_id=operation.id,
            caller=access,
        )
        
        # Simulate verification failure (ambiguous result)
        result = await external_operation_service.verify_operation(
            db=pg_db_session,
            operation_id=operation.id,
            external_result={"partial": True, "status": "unknown"},  # Ambiguous
            caller=access,
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')