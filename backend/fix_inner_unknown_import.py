with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove all inner imports
content = content.replace(
    '''            # Create external unknown state (unresolved operation)
            from app.models.canonical_reliability import ExternalUnknownState
            unk1 = ExternalUnknownState(''',
    '''            # Create external unknown state (unresolved operation)
            unk1 = ExternalUnknownState('''
)

content = content.replace(
    '''            # Create external unknown state for decision linking
            from app.models.canonical_reliability import ExternalUnknownState
            unk1 = ExternalUnknownState(''',
    '''            # Create external unknown state for decision linking
            unk1 = ExternalUnknownState('''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed inner imports for ExternalUnknownState')