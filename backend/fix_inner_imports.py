with open('create_company_state.py', 'r') as f:
    content = f.read()

# Remove the inner imports since they cause scoping issues
content = content.replace(
    '''            # Create canonical observations
            from app.models.canonical_integration import CanonicalObservation, CorrelationContext
            from app.models.canonical_reliability import CanonicalOperation, OperationAttempt
            
            obs1 = CanonicalObservation(''',
    '''            # Create canonical observations
            obs1 = CanonicalObservation('''
)

content = content.replace(
    '''            # Create external unknown state (unresolved operation)
            from app.models.canonical_reliability import ExternalUnknownState
            
            eus1 = ExternalUnknownState(''',
    '''            # Create external unknown state (unresolved operation)
            eus1 = ExternalUnknownState('''
)

content = content.replace(
    '''            # Create more canonical operations for decision linking
            from app.models.canonical_reliability import CanonicalOperation, OperationAttempt
            
            cop1 = CanonicalOperation(''',
    '''            # Create more canonical operations for decision linking
            cop1 = CanonicalOperation('''
)

content = content.replace(
    '''            # Create canonical operations for intent linking
            from app.models.canonical_reliability import CanonicalOperation, OperationAttempt
            
            cop1 = CanonicalOperation(''',
    '''            # Create canonical operations for intent linking
            cop1 = CanonicalOperation('''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Removed inner imports causing scoping issues')