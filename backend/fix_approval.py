with open('tests/acceptance/test_release_candidate_slice_2a.py', 'r') as f:
    content = f.read()

# Fix all remaining ApprovalPolicy creations
old1 = '''policy1 = ApprovalPolicy(organization_id=org1.id, name="Policy 1", kind="decision", threshold=1)
        policy2 = ApprovalPolicy(organization_id=org2.id, name="Policy 2", kind="decision", threshold=1)'''

new1 = '''policy1 = ApprovalPolicy(organization_id=org1.id, name="Policy 1", approval_type="decision", required_permission="decision:create")
        policy2 = ApprovalPolicy(organization_id=org2.id, name="Policy 2", approval_type="decision", required_permission="decision:create")'''

old2 = '''policy = ApprovalPolicy(
            organization_id=org.id,
            name="Test Policy",
            kind="decision",
            threshold=1,
        )'''

new2 = '''policy = ApprovalPolicy(
            organization_id=org.id,
            name="Test Policy",
            approval_type="decision",
            required_permission="decision:create",
        )'''

content = content.replace(old1, new1)
content = content.replace(old2, new2)

with open('tests/acceptance/test_release_candidate_slice_2a.py', 'w') as f:
    f.write(content)
print('Done')