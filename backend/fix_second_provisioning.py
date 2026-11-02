with open('app/services/onboarding_service.py', 'r') as f:
    content = f.read()

# Fix second occurrence
old = '''        context.current_phase = OnboardingPhase.PROVISIONING_STARTED
        context.completed_steps.append("company_creation")
        
        # Phase 2: Start provisioning (infrastructure setup)
        provisioning = await provisioning_service.start_provisioning(
            db,
            organization_name=context.organization_name,
            domain=context.domain,
            admin_email=context.admin_email,
            admin_name=context.admin_name,
            plan_key=context.plan_key,
            billing_interval=context.billing_interval,
            custom_domain=context.custom_domain,
        )'''

new = '''        context.current_phase = OnboardingPhase.PROVISIONING_STARTED
        context.completed_steps.append("company_creation")
        
        # Phase 2: Start provisioning (infrastructure setup) using existing organization
        provisioning = await provisioning_service.start_provisioning(
            db,
            organization_name=context.organization_name,
            domain=context.domain,
            admin_email=context.admin_email,
            admin_name=context.admin_name,
            plan_key=context.plan_key,
            billing_interval=context.billing_interval,
            custom_domain=context.custom_domain,
            organization_id=context.organization_id,
        )'''

content = content.replace(old, new)

with open('app/services/onboarding_service.py', 'w') as f:
    f.write(content)
print('Done')