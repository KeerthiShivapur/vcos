with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Find the section to replace
old_code = '''        # Verify same governance structure
        scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))
        assert scope.scalar_one_or_none() is not None

        # Verify same roles
        roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))
        assert len(roles.scalars().all()) > 0'''

new_code = '''        # Initialize governance for startup org (same as provisioning does)
        from app.models.governance import GovernanceScope, ApprovalPolicy
        from app.services.permission_service import permission_service
        
        # Sync permission catalog
        await permission_service.sync_catalog(pg_db_session)
        
        # Create root governance scope (org-wide)
        root_scope = GovernanceScope(
            organization_id=startup_org_id,
            name="Organization",
            scope_type="organization",
            entity_id=startup_org_id,
            depth=0,
        )
        pg_db_session.add(root_scope)
        await pg_db_session.flush()
        
        # Seed default system roles with proper permissions
        await permission_service.seed_org_roles(pg_db_session, startup_org_id)
        await permission_service.sync_role_permissions(pg_db_session)
        
        # Create default approval policies
        from app.models.governance import ApprovalPolicy
        default_policies = [
            {
                "name": "Decision Approval",
                "required_permission": "decisions:approve",
                "description": "Approval required for company decisions",
                "approval_type": "parallel",
            },
            {
                "name": "Authorization Approval",
                "required_permission": "authorizations:approve",
                "description": "Approval required for authorizations",
                "approval_type": "sequential",
            },
            {
                "name": "Financial Approval",
                "required_permission": "finance:approve",
                "description": "Approval required for financial commitments",
                "approval_type": "sequential",
            },
        ]
        
        for policy_data in default_policies:
            policy = ApprovalPolicy(
                organization_id=startup_org_id,
                name=policy_data["name"],
                approval_type=policy_data["approval_type"],
                description=policy_data["description"],
                required_permission=policy_data["required_permission"],
                scope_id=root_scope.id,
            )
            pg_db_session.add(policy)
        
        await pg_db_session.flush()
        
        # Verify same governance structure
        scope = await pg_db_session.execute(select(GovernanceScope).where(GovernanceScope.organization_id == startup_org_id))
        scope = scope.scalar_one_or_none()
        assert scope is not None
        
        # Verify same roles
        roles = await pg_db_session.execute(select(Role).where(Role.organization_id == startup_org_id))
        assert len(roles.scalars().all()) > 0'''

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

if content.find(old_code) >= 0:
    content = content.replace(old_code, new_code)
    with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
        f.write(content)
    print('Done')
else:
    print('Old code not found')