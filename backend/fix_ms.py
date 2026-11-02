with open('app/intelligence/connectors/microsoft.py', 'r') as f:
    content = f.read()

# Find the last occurrence of the duplicate methods
old = '''    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(Microsoft365Connector())'''

new_text = '''# Register the connector
connector_registry.register(Microsoft365Connector())'''

content = content.replace(
    '''    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(Microsoft365Connector())''',
    new_text
)

with open('app/intelligence/connectors/microsoft.py', 'w') as f:
    f.write(content)
print('Fixed')