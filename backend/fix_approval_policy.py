with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix ApprovalPolicy fields
old_ap = '''            ap1 = ApprovalPolicy(
                organization_id=org.id,
                name="Platform Migration Approval",
                approval_type="decision",
                required_permission="decision:create",
                required_approvers=1,
                approval_threshold=1,
                description="Approval required for platform migration decisions"
            )'''

new_ap = '''            ap1 = ApprovalPolicy(
                organization_id=org.id,
                name="Platform Migration Approval",
                approval_type="decision",
                required_permission="decision:create",
                scope_id=None,
                self_approval_allowed=False,
                is_active=True,
                description="Approval required for platform migration decisions"
            )'''

content = content.replace(old_ap, new_ap)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed ApprovalPolicy fields')