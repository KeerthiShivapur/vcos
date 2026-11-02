with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Replace lines 1064-1071 (1-indexed) which are indices 1063-1071 (0-indexed)
# Line 1064 (1-indexed) = index 1063
# Line 1071 (1-indexed) = index 1070

# Read all lines
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    lines = f.readlines()

# Find the exact lines to replace
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'Verify same governance structure' in line and i > 0:
        start_idx = i - 1  # Include the blank line before
    if 'Verify same identity mapping capability' in line:
        end_idx = i
        break

print(f"start_idx={start_idx}, end_idx={end_idx}")

if start_idx is not None and end_idx is not None:
    # Replace lines[start_idx:end_idx] with new content
    new_lines = [
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
        '            scope_type="organization",\n',
        '            entity_id=startup_org_id,\n',
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
        '            "required_permission": "authorizations:approve",\n',
        '            "description": "Approval required for authorizations",\n',
        '            "approval_type": "sequential",\n',
        '            },\n',
        '            {\n',
        '            "name": "Financial Approval",\n',
        '            "required_permission": "finance:approve",\n',
        '            "description": "Approval required for financial commitments",\n',
        '            "approval_type": "sequential",\n',
        '            },\n',
        '        ]\n',
        '\n',
        '        for policy_data in default_policies:\n',
        '            policy = ApprovalPolicy(\n',
        '                organization_id=startup_org_id,\n',
        '                name=policy_data["name"],\n',
        '                approval_type=policy_data["approval_type"],\n',
        '                description=policy_data["description"],\n',
        '                required_permission=policy_data["required_permission"],\n',
        '                scope_id=root_scope.id,\n',
        '            )\n',
        '            pg_db_session.add(policy)\n',
        '\n',
        '        await pg_db_session.flush()\n',
        '\n',
        '        # Verify same governance structure\n',
        '        scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n',
        '        scope = scope.scalar_one_or_none()\n',
        '        assert scope is not None\n',
        '\n',
        '        # Verify same roles\n',
        '        roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n',
        '        assert len(roles.scalars().all()) > 0\n',
    ]

    new_lines = lines[:1063] + [
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
        '            scope_type="organization",\n',
        '            entity_id=startup_org_id,\n',
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
        '            "required_permission": "authorizations:approve",\n',
        '            "description": "Approval required for authorizations",\n',
        '            "approval_type": "sequential",\n',
        '            },\n',
        '            {\n',
        '            "name": "Financial Approval",\n',
        '            "required_permission": "finance:approve",\n',
        '            "description": "Approval required for financial commitments",\n',
        '            "approval_type": "sequential",\n',
        '            },\n',
        '        ]\n',
        '\n',
        '        for policy_data in default_policies:\n',
        '            policy = ApprovalPolicy(\n',
        '                organization_id=startup_org_id,\n',
        '                name=policy_data["name"],\n',
        '                approval_type=policy_data["approval_type"],\n',
        '                description=policy_data["description"],\n',
        '                required_permission=policy_data["required_permission"],\n',
        '                scope_id=root_scope.id,\n',
        '            )\n',
        '        pg_db_session.add(policy)\n',
        '\n',
        '        await pg_db_session.flush()\n',
        '\n',
        '        # Verify same governance structure\n',
        '        scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))\n',
        '        scope = scope.scalar_one_or_none()\n',
        '        assert scope is not None\n',
        '\n',
        '        # Verify same roles\n',
        '        roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))\n',
        '        assert len(roles.scalars().all()) > 0\n',
    ] + lines[1071:]

    with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
        f.writelines(new_lines)
    print('Done')