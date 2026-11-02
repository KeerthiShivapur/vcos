with open('tests/acceptance/test_real_company_onboarding.py', 'r') as f:
    content = f.read()

# Find the test_start_onboarding_creates_organization method and replace it entirely
old = '''test_start_onboarding_creates_organization(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        """Starting onboarding creates organization and begins provisioning."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
            
        # Verify organization created
        assert context.organization_id is not None
            assert context.provisioning_id is not None
            assert context.admin_user_id is not None
            
            # Verify organization exists
            org = await pg_db_session.get(Organization, context.organization_id)
            assert org is not None
            assert org.name == onboarding_context.organization_name
            assert org.slug == onboarding_context.domain
            assert org.status == "provisioning"
            
            # Verify admin user created
            admin = await pg_db_session.get(User, context.admin_user_id)
            assert admin is not None
            assert admin.email == onboarding_context.admin_email
            assert admin.full_name == onboarding_context.admin_name
            
            # Verify provisioning record created
            from app.models.finance import Provisioning
            prov = await pg_db_session.get(Provisioning, context.provisioning_id)
            assert prov is not None
            assert prov.state == ProvisioningState.REQUESTED.value
            assert prov.organization_id == context.organization_id
        '''

new = '''test_start_onboarding_creates_organization(
        self,
        pg_db_session: AsyncSession,
        onboarding_context: OnboardingContext,
    ):
        """Starting onboarding creates organization and begins provisioning."""
        
        context = await onboarding_service.start_company_onboarding(
            pg_db_session,
            onboarding_context,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        
        # Verify organization created
        assert context.organization_id is not None
        assert context.provisioning_id is not None
        assert context.admin_user_id is not None
        
        # Verify organization exists
        org = await pg_db_session.get(Organization, context.organization_id)
        assert org is not None
        assert org.name == onboarding_context.organization_name
        assert org.slug == onboarding_context.domain
        assert org.status == "provisioning"
        
        # Verify admin user created
        admin = await pg_db_session.get(User, context.admin_user_id)
        assert admin is not None
        assert admin.email == onboarding_context.admin_email
        assert admin.full_name == onboarding_context.admin_name
        
        # Verify provisioning record created
        from app.models.finance import Provisioning
        prov = await pg_db_session.get(Provisioning, context.provisioning_id)
        assert prov is not None
        assert prov.state == ProvisioningState.REQUESTED.value
        assert prov.organization_id == context.organization_id
'''

content = content.replace(old, new)

with open('tests/acceptance/test_real_company_onboarding.py', 'w') as f:
    f.write(content)
print('Done')