with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Find the section to replace
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

# Read all lines
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Build new lines
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
new_lines.append('\n')
new_lines.append('        # Seed default system roles with proper permissions\n')
new_lines.append('        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n')
new_lines.append('        await permission_service.sync_role_permissions(pg_db_session)\n')
new_lines.append('\n')
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
new_lines.append('                "description": "Approval required for authorizations",\n')
new_lines.append('                "approval_type": "sequential",\n')
new_lines.append('            },\n')
new_lines.append('            {\n')
new_lines.append('            "name": "Financial Approval",\n')
new_lines.append('                "required_permission": "finance:approve",\n')
new_lines.append('                "description": "Approval required for financial commitments",\n')
new_lines.append('                "approval_type": "sequential",\n')
new_lines.append('            },\n')
new_lines.append('        ]\n')
new_lines.append('\n')
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
new_lines.append('\n')
new_lines.append('        await pg_db_session.flush()\n')
new_lines.append('\n')
new_lines.append('# Verify same governance structure\n')
new_lines.append('scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n')
new_lines.append('scope = scope.scalar_one_or_none()\n')
new_lines.append('assert scope is not None\n')
new_lines.append('\n')
new_lines.append('# Verify same roles\n')
new_lines.append('roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n')
new_lines.append('assert len(roles.scalars().all()) > 0\n')

# Read the file
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Find the section to replace
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

# Build new content
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
new_lines.append('\n')
new_lines.append('        # Seed default system roles with proper permissions\n')
new_lines.append('        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n')
new_lines.append('        await permission_service.sync_role_permissions(pg_db_session)\n')
new_lines.append('\n')
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
new_lines.append('                "description": "Approval required for authorizations",\n')
new_lines.append('                "approval_type": "sequential",\n')
new_lines.append('            },\n')
new_lines.append('            {\n')
new_lines.append('            "name": "Financial Approval",\n')
new_lines.append('            "required_permission": "finance:approve",\n')
new_lines.append('                "description": "Approval required for financial commitments",\n')
new_lines.append('                "approval_type": "sequential",\n')
new_lines.append('            },\n')
new_lines.append('        ]\n')
new_lines.append('\n')
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
new_lines.append('\n')
new_lines.append('        await pg_db_session.flush()\n')
new_lines.append('\n')
new_lines.append('# Verify same governance structure\n')
new_lines.append('scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n')
new_lines.append('scope = scope.scalar_one_or_none()\n')
new_lines.append('assert scope is not None\n')
new_lines.append('\n')
new_lines.append('# Verify same roles\n')
new_lines.append('roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n')
new_lines.append('assert len(roles.scalars().all()) > 0\n')

# Read the file
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Find the section to replace
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

# Build new content
new_lines = lines[:start_idx] + [
    '        # Initialize governance for startup org (same as provisioning does)\n',
    '        from app.models.governance import GovernanceScope, ApprovalPolicy\n',
    '        from app.services.permission_service import permission_service\n',
    '\n',
    '        # Sync permission catalog\n',
    '        await permission_service.sync_catalog(pg_db_session)\n',
    '\n',
    '        # Create root governance scope (org-wide)\n',
    '        root_scope = GovernanceScope(\n',
    '            organization_id=startup_org_id,\n',
    '            name="Organization",\n',
    '            scope_type="organization",\n'
    '            entity_id=startup_org_id,\n'
    '            depth=0,\n'
    '        )\n',
    '        pg_db_session.add(root_scope)\n',
    '        await pg_db_session.flush()\n',
    '\n',
    '        # Seed default system roles with proper permissions\n',
    '        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n',
    '        await permission_service.sync_role_permissions(pg_db_session)\n',
    '\n',
    '        # Create default approval policies\n',
    '        from app.models.governance import ApprovalPolicy\n',
    '        default_policies = [\n',
    '            {\n',
    '                "name": "Decision Approval",\n',
    '                "required_permission": "decisions:approve",\n',
    '                "description": "Approval required for company decisions",\n'
    '                "approval_type": "parallel",\n'
    '            },\n',
    '            {\n',
    '            "name": "Authorization Approval",\n',
    '            "required_permission": "authorizations:approve",\n'
    '            "description": "Approval required for authorizations",\n'
    '            "approval_type": "sequential",\n'
    '            },\n',
    '            {\n',
    '            "name": "Financial Approval",\n'
    '            "required_permission": "finance:approve",\n'
    '            "description": "Approval required for financial commitments",\n'
    '            "approval_type": "sequential",\n'
    '            },\n',
    '        ]\n',
    '\n',
    '        for policy_data in default_policies:\n',
    '    policy = ApprovalPolicy(\n',
    '        organization_id=startup_org_id,\n',
    '        name=policy_data["name"],\n',
    '        approval_type=policy_data["approval_type"],\n',
    '        description=policy_data["description"],\n'
    '        required_permission=policy_data["required_permission"],\n'
    '        scope_id=root_scope.id,\n',
    '    )\n',
    '    pg_db_session.add(policy)\n',
    '\n',
    '    await pg_db_session.flush()\n',
    '\n',
    '# Verify same governance structure\n',
    'scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n',
    'scope = scope.scalar_one_or_none()\n',
    'assert scope is not None\n',
    '\n',
    '# Verify same roles\n',
    'roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n',
    'assert len(roles.scalars().all()) > 0\n',
] + lines[1071:]

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.writelines(new_content)
print('Done')
<tool_call>
<function=write>
<parameter=content>
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Find the section to replace
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

# Read all lines
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Build new content
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
new_lines.append('\n')
new_lines.append('        # Seed default system roles with proper permissions\n')
new_lines.append('        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n')
new_lines.append('        await permission_service.sync_role_permissions(pg_db_session)\n')
new_lines.append('\n')
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
new_lines.append('\n')
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
new_lines.append('\n')
new_lines.append('        await pg_db_session.flush()\n')
new_lines.append('\n')
new_lines.append('# Verify same governance structure\n')
new_lines.append('scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n')
new_lines.append('scope = scope.scalar_one_or_none()\n')
new_lines.append('assert scope is not None\n')
new_lines.append('\n')
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

new_lines = lines[:start_idx] + [
    '        # Initialize governance for startup org (same as provisioning does)\n',
    '        from app.models.governance import GovernanceScope, ApprovalPolicy\n',
    '        from app.services.permission_service import permission_service\n',
    '\n',
    '        # Sync permission catalog\n',
    '        await permission_service.sync_catalog(pg_db_session)\n',
    '\n',
    '        # Create root governance scope (org-wide)\n',
    '        root_scope = GovernanceScope(\n',
    '            organization_id=startup_org_id,\n',
    '            name="Organization",\n',
    '            scope_type="organization",\n'
    '            entity_id=startup_org_id,\n'
    '            depth=0,\n',
    '        )\n',
    '        pg_db_session.add(root_scope)\n',
    '        await pg_db_session.flush()\n',
    '\n',
    '        # Seed default system roles with proper permissions\n',
    '        await permission_service.seed_org_roles(pg_db_session, startup_org_id)\n',
    '        await permission_service.sync_role_permissions(pg_db_session)\n',
    '\n',
    '        # Create default approval policies\n',
    '        from app.models.governance import ApprovalPolicy\n',
    '        default_policies = [\n',
    '            {\n',
    '                "name": "Decision Approval",\n',
    '                "required_permission": "decisions:approve",\n',
    '                "description": "Approval required for company decisions",\n',
    '                "approval_type": "parallel",\n',
    '            },\n',
    '            {\n',
    '            "name": "Authorization Approval",\n',
    '            "required_permission": "authorizations:approve",\n'
    '            "description": "Approval required for authorizations",\n',
    '            "approval_type": "sequential",\n',
    '            },\n',
    '            {\n',
    '            "name": "Financial Approval",\n',
    '            "required_permission": "finance:approve",\n'
    '            "description": "Approval required for financial commitments",\n',
    '            "approval_type": "sequential",\n',
    '            },\n',
    '        ]\n',
    '\n',
    '        for policy_data in default_policies:\n',
    '    policy = ApprovalPolicy(\n',
    '        organization_id=startup_org_id,\n',
    '        name=policy_data["name"],\n',
    '        approval_type=policy_data["approval_type"],\n',
    '        description=policy_data["description"],\n',
    '        required_permission=policy_data["required_permission"],\n',
    '        scope_id=root_scope.id,\n',
    '    )\n',
    '    pg_db_session.add(policy)\n',
    '\n',
    '    await pg_db_session.flush()\n',
    '\n',
    '# Verify same governance structure\n',
    'scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n',
    'scope = scope.scalar_one_or_none()\n',
    'assert scope is not None\n',
    '\n',
    '# Verify same roles\n',
    'roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n',
    'assert len(roles.scalars().all()) > 0\n',
] + lines[1071:]

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.writelines(new_lines)
print('Done')