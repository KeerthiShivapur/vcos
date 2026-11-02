with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Add the create_adapter function at the end
new_content = content + '''

async def create_adapter(action: str, context: AdapterContext) -> AcceptanceAdapter:
    """Factory function to create adapter for action."""
    adapter_class = ADAPTER_REGISTRY.get(action)
    if not adapter_class:
        # Return base adapter for unknown actions
        return AcceptanceAdapter(context)
    return adapter_class(context)
'''

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)
print('Added create_adapter function back')