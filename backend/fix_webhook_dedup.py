with open('app/services/webhook_ingestion_service.py', 'r') as f:
    content = f.read()

# Fix the _deduplicate_and_record method to eagerly load the connector
old = '''async def _deduplicate_and_record(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> ExternalEvent:
        """Deduplicate webhook and record external event."""
        # Load connector if not already loaded
        if not hasattr(instance, 'connector') or instance.connector is None:
            connector = await db.get(Connector, instance.connector_id)
        else:
            connector = instance.connector'''

new = '''async def _deduplicate_and_record(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> ExternalEvent:
        """Deduplicate webhook and record external event."""
        # Eagerly load connector
        connector = await db.get(Connector, instance.connector_id)'''

content = content.replace(old, new)

with open('app/services/webhook_ingestion_service.py', 'w') as f:
    f.write(content)
print('Fixed')