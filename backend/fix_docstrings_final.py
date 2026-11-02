import re

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The issue: regex replacement broke multi-line docstrings
# We need to restore the file to a working state
# Let's revert the regex changes and fix the syntax properly

# First, let's restore the original file by reverting the regex changes
# We need to find all single-quoted strings that were converted from triple quotes
# and restore them properly

# For now, let's just restore the file to a known working state
# by reverting the regex substitution

# The issue is that the regex `"""([^"]*)"""` only matches single-line docstrings
# Multi-line docstrings were broken

# Let's restore the file by reading from a backup or rewriting the docstrings properly

# For now, let's just fix the specific syntax errors by ensuring all docstrings
# are properly formatted

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The issue: single quotes were used for multi-line strings
# We need to convert them back to triple quotes for multi-line strings
# and keep single-line docstrings as single quotes

# This is complex. Let's just restore from a known good state.
# Since we don't have a backup, let's rewrite the problematic sections.

# For now, let's just fix the specific syntax errors by ensuring
# all docstrings are properly formatted

# The main issues are:
# 1. Class docstrings that span multiple lines need triple quotes
# 2. Function docstrings can be single-line with single quotes

# Let's identify the problematic sections and fix them

with open('app/intelligence/canonical_integration_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the ConnectorService class docstring (around line 209)
# It was converted to single quotes but spans multiple lines
content = content.replace(
    "'Universal connector framework service.\n    \n    Provides the canonical service layer for:\n    - Connector registration & discovery\n    - Connector instance lifecycle management\n    - Configuration validation\n    - Capability discovery\n    - Connection testing & health checks\n    \n    This is the provider-neutral foundation that all specific connectors build upon.\n    '",
    '"""Universal connector framework service.\n    \n    Provides the canonical service layer for:\n    - Connector registration & discovery\n    - Connector instance lifecycle management\n    - Configuration validation\n    - Capability discovery\n    - Connection testing & health checks\n    \n    This is the provider-neutral foundation that all specific connectors build upon.\n    """'
)

# Fix the _process_game_action function docstring (around line 1473)
content = content.replace(
    "'Process a game action and return new state.'",
    '"""Process a game action and return new state."""'
)

# Fix the _initialize_game_state function docstring
content = content.replace(
    "'Initialize game state for a new session.'",
    '"""Initialize game state for a new session."""'
)

# Fix the get_workspace_settings function docstring
content = content.replace(
    "'Get user's workspace personalization settings.'",
    '"""Get user\'s workspace personalization settings."""'
)

with open('app/intelligence/canonical_integration_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed docstrings')