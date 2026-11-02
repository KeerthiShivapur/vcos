with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Fix test_14_unknown_external_outcome_preserved - change operation_type from CREATE to READ
old = '''        request = OperationRequest(
            source_action_id=None,
            source_decision_id=None,
            source_authorization_id=None,
            source_commitment_id=None,
            operation_type=OperationType.CREATE,
            target_entity_type="repository",
            target_external_id="test/repo",
            payload={"name": "test-repo"},
            governance_verified=True,
        )'''

new = '''        request = OperationRequest(
            source_action_id=None,
            source_decision_id=None,
            source_authorization_id=None,
            source_commitment_id=None,
            operation_type=OperationType.READ,
            target_entity_type="repository",
            target_external_id="test/repo",
            payload={},
            governance_verified=True,
        )'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')