with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix OperationAttempt field - operation_id not canonical_operation_id
content = content.replace(
    '''            oa1 = OperationAttempt(
                canonical_operation_id=cop1.id,''',
    '''            oa1 = OperationAttempt(
                operation_id=cop1.id,'''
)

# Also fix any other occurrences
content = content.replace(
    '''            oa2 = OperationAttempt(
                canonical_operation_id=cop2.id,''',
    '''            oa2 = OperationAttempt(
                operation_id=cop2.id,'''
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed OperationAttempt field')