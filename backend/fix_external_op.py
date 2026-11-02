with open('app/services/external_operation_service.py', 'r') as f:
    content = f.read()

# Find the create_operation method and add validation
old = '''        instance = await db.get(ConnectorInstance, connector_instance_id)
        if not instance or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        # Verify governance chain
        if not request.governance_verified:
            raise ValueError("Operation must be governance-verified")'''

new = '''        instance = await db.get(ConnectorInstance, connector_instance_id)
        if not instance or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        # Verify connector supports the requested operation
        connector = await db.get(Connector, instance.connector_id)
        if not connector:
            raise ValueError("Connector not found")
        
        # Verify connector supports the requested operation type
        if request.operation_type.value not in connector.outbound_capabilities:
            raise ValueError(f"Connector does not support operation type: {request.operation_type.value}")
        
        # Verify connector supports the target entity type
        if request.target_entity_type not in connector.supported_entities:
            raise ValueError(f"Connector does not support entity type: {request.target_entity_type}")
        
        # Verify governance chain
        if not request.governance_verified:
            raise ValueError("Operation must be governance-verified")'''

content = content.replace(old, new)

with open('app/services/external_operation_service.py', 'w') as f:
    f.write(content)
print('Fixed')