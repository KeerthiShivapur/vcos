with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'Verify same governance structure' in line:
        start_idx = i - 1
    if 'Verify same identity mapping capability' in line:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    print("Could not find section")
    exit(1)

print(f"Replacing lines {start_idx} to {end_idx}")

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Build new content
new_content = []
new_lines = []
new_lines.extend(lines[:start_idx])
new_lines.append('        # Initialize governance for startup org (same as provisioning does)\n')
new_lines.append('        from app.models.governance import GovernanceScope, ApprovalPolicy\n')
new_lines.append('        from app.services.permission_service import permission_service\n')
new_lines.append('\n')
new_lines.append('        # Sync permission catalog\n')
new_lines.append('        await permission_service.sync_catalog(pg_db_session)\n')
new_lines.append('\n')
new_lines.append('        # Create root governance scope (org-wide)\n')
new_lines.append('        root_scope = GovernanceScope(\n')
new_lines.append('            organization_id=startup_org_id,\n')
new_lines.append('            name="Organization",\n')
new_lines.append('            scope_type="organization",\n')
new_lines.append('            entity_id=startup_org_id,\n')
new_lines.append('            depth=0,\n')
new_lines.append('        )\n')
new_lines.append('        pg_db_session.add(root_scope)\n')
new_lines.append('        await pg_db_session.flush()\n')
new_lines.append('')
new_lines.append('        # Seed default system roles with proper permissions\n')
new_lines.append('        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n')
new_lines.append('        await permission_service.sync_role_permissions(pg_db_session)\n')
new_lines.append('')
new_lines.append('        # Create default approval policies\n')
new_lines.append('        from app.models.governance import ApprovalPolicy\n')
new_lines.append('        default_policies = [\n')
new_lines.append('            {\n')
new_lines.append('                "name": "Decision Approval",\n')
new_lines.append('                "required_permission": "decisions:approve",\n')
new_lines.append('                "description": "Approval required for company decisions",\n')
new_lines.append('                "approval_type": "parallel",\n')
new_lines.append('            },\n')
new_lines.append('            {\n')
new_lines.append('            "name": "Authorization Approval",\n')
new_lines.append('            "required_permission": "authorizations:approve",\n')
new_lines.append('            "description": "Approval required for authorizations",\n')
new_lines.append('            "approval_type": "sequential",\n')
new_lines.append('            },\n')
new_lines.append('            {\n')
new_lines.append('            "name": "Financial Approval",\n')
new_lines.append('            "required_permission": "finance:approve",\n')
new_lines.append('            "description": "Approval required for financial commitments",\n')
new_lines.append('            "approval_type": "sequential",\n')
new_lines.append('            },\n')
new_lines.append('        ]\n')
new_lines.append('')
new_lines.append('        for policy_data in default_policies:\n')
new_lines.append('            policy = ApprovalPolicy(\n')
new_lines.append('                organization_id=startup_org_id,\n')
new_lines.append('                name=policy_data["name"],\n')
new_lines.append('                approval_type=policy_data["approval_type"],\n')
new_lines.append('                description=policy_data["description"],\n')
new_lines.append('                required_permission=policy_data["required_permission"],\n')
new_lines.append('                scope_id=root_scope.id,\n')
new_lines.append('            )\n')
new_lines.append('        pg_db_session.add(policy)\n')
new_lines.append('')
new_lines.append('        await pg_db_session.flush()\n')
new_lines.append('')
new_lines.append('# Verify same governance structure\n')
new_lines.append('scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n')
new_lines.append('scope = scope.scalar_one_or_none()\n')
new_lines.append('assert scope is not None\n')
new_lines.append('')
new_lines.append('# Verify same roles\n')
new_lines.append('roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n')
new_lines.append('assert len(roles.scalars().all()) > 0\n')

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'Verify same governance structure' in line:
        start_idx = i - 1
    if 'Verify same identity mapping capability' in line:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    print("Could not find section")
    exit(1)

print(f"Replacing lines {start_idx} to {end_idx}")

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Build new content
new_content = []
new_lines = lines[:start_idx] + [
    '        # Initialize governance for startup org (same as provisioning does)\n',
    '        from app.models.governance import GovernanceScope, ApprovalPolicy\n',
    '        from app.services.permission_service import permission_service\n',
    '\n',
    new_lines.append('        # Sync permission catalog\n'),
    new_lines.append('        await permission_service.sync_catalog(pg_db_session)\n'),
    new_lines.append(''),
    new_lines.append('        # Create root governance scope (org-wide)\n'),
    new_lines.append('        root_scope = GovernanceScope(\n'),
    new_lines.append('            organization_id=startup_org_id,\n'),
    new_lines.append('            name="Organization",\n'),
    new_lines.append('            scope_type="organization",\n'),
    new_lines.append('            entity_id=startup_org_id,\n'),
    new_lines.append('            depth=0,\n'),
    new_lines.append('        )\n'),
    new_lines.append('        pg_db_session.add(root_scope)\n'),
    new_lines.append('        await pg_db_session.flush()\n'),
    new_lines.append(''),
    new_lines.append('        # Seed default system roles with proper permissions\n'),
    new_lines.append('        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n'),
    new_lines.append('        await permission_service.sync_role_permissions(pg_db_session)\n'),
    new_lines.append(''),
    new_lines.append('        # Create default approval policies\n'),
    new_lines.append('        from app.models.governance import ApprovalPolicy\n'),
    new_lines.append('        default_policies = [\n'),
    new_lines.append('            {\n'),
    new_lines.append('                "name": "Decision Approval",\n'),
    new_lines.append('                "required_permission": "decisions:approve",\n'),
    new_lines.append('                "description": "Approval required for company decisions",\n'),
    new_lines.append('                "approval_type": "parallel",\n'),
    new_lines.append('            },\n'),
    new_lines.append('            {\n'),
    new_lines.append('            "name": "Authorization Approval",\n'),
    new_lines.append('            "required_permission": "authorizations:approve",\n'),
    new_lines.append('            "description": "Approval required for authorizations",\n'),
    new_lines.append('            "approval_type": "sequential",\n'),
    new_lines.append('            },\n'),
    new_lines.append('            {\n'),
    new_lines.append('            "name": "Financial Approval",\n'),
    new_lines.append('            "required_permission": "finance:approve",\n'),
    new_lines.append('                "description": "Approval required for financial commitments",\n'),
    new_lines.append('            "approval_type": "sequential",\n'),
    new_lines.append('            },\n'),
    new_lines.append('        ]\n'),
    new_lines.append(''),
    new_lines.append('        for policy_data in default_policies:\n'),
    new_lines.append('            policy = ApprovalPolicy(\n'),
    new_lines.append('                organization_id=startup_org_id,\n'),
    new_lines.append('                name=policy_data["name"],\n'),
    new_lines.append('                approval_type=policy_data["approval_type"],\n'),
    new_lines.append('                description=policy_data["description"],\n'),
    new_lines.append('                required_permission=policy_data["required_permission"],\n'),
    new_lines.append('                scope_id=root_scope.id,\n'),
    new_lines.append('            )\n'),
    new_lines.append('        pg_db_session.add(policy)\n'),
    new_lines.append(''),
    new_lines.append('        await pg_db_session.flush()\n'),
    new_lines.append(''),
    new_lines.append('# Verify same governance structure\n'),
    new_lines.append('scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n'),
    new_lines.append('scope = scope.scalar_one_or_none()\n'),
    new_lines.append('assert scope is not None\n'),
    new_lines.append(''),
    new_lines.append('# Verify same roles\n'),
    new_lines.append('roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n'),
    new_lines.append('assert len(roles.scalars().all()) > 0\n'),
] + lines[1071:]

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.writelines(new_content)
print('Done')