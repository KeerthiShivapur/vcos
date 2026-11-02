with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix GovernanceScope fields
old_gs = '''            gs1 = GovernanceScope(
                organization_id=org.id,
                name="Platform Governance",
                scope_type="company",
                scope_id=org.id,
                description="Governance scope for platform operations"
            )'''

new_gs = '''            gs1 = GovernanceScope(
                organization_id=org.id,
                name="Platform Governance",
                scope_type="company",
                entity_id=org.id,
                depth=0
            )'''

content = content.replace(old_gs, new_gs)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed GovernanceScope fields')