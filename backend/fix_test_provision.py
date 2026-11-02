with open('tests/acceptance/test_integration_adversarial.py', 'r') as f:
    content = f.read()

# Find _provision_company and fix it
old = '''async def _provision_company(db: AsyncSession, domain: str) -> tuple:
    """Provision a test company and return (org_id, admin_user, admin_emp, access)."""
    provisioning = await provisioning_service.start_provisioning(
        db,
        organization_name=f"Test Corp {domain}",
        domain=domain,
        plan_key="starter",
        billing_interval="monthly",
    )'''

new = '''async def _provision_company(db: AsyncSession, domain: str) -> tuple:
    """Provision a test company and return (org_id, admin_user, admin_emp, access)."""
    provisioning = await provisioning_service.start_provisioning(
        db,
        organization_name=f"Test Corp {domain}",
        domain=domain,
        admin_email=f"admin@{domain}.com",
        admin_name="Test Admin",
        plan_key="starter",
        billing_interval="monthly",
    )'''

content = content.replace(old, new)

with open('tests/acceptance/test_integration_adversarial.py', 'w') as f:
    f.write(content)
print('Fixed')