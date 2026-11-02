with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the docstrings that were broken by regex replacement
content = content.replace(
    "'Universal connector framework service.\n    \n    Provides the canonical service layer for:\n    - Connector registration & discovery\n    - Connector instance lifecycle management\n    - Configuration validation\n    - Capability discovery\n    - Connection testing & health checks\n    \n    This is the provider-neutral foundation that all specific connectors build upon.\n    '",
    '"""Universal connector framework service.\n    \n    Provides the canonical service layer for:\n    - Connector registration & discovery\n    - Connector instance lifecycle management\n    - Configuration validation\n    - Capability discovery\n    - Connection testing & health checks\n    \n    This is the provider-neutral foundation that all specific connectors build upon.\n    """'
)

content = content.replace(
    "'Process a game action and return new state.'",
    '"""Process a game action and return new state."""'
)

content = content.replace(
    "'Initialize game state for a new session.'",
    '"""Initialize game state for a new session."""'
)

content = content.replace(
    "'Get user's workspace personalization settings.'",
    '"""Get user\'s workspace personalization settings."""'
)

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed docstrings')