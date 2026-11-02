# Check which indirect tables are in TENANT_SCOPED_DIRECT in 9f3c1a7d52e6
indirect_tables = [
    'backup_corruption_tests', 'backup_verification_results',
    'deployment_completeness_dimensions',
    'developer_api_keys', 'developer_applications', 'developer_certifications',
    'developer_subscriptions', 'developer_usage', 'developers', 'devices',
    'industry_templates', 'marketplace_reviews',
    'optimization_alternatives', 'plugin_versions', 'provisioning_steps',
    'role_permissions', 'subscription_invoices', 'subscription_payments',
    'workflow_edges', 'workflow_execution_steps', 'workflow_nodes', 'workflow_versions',
]

with open('alembic/versions/9f3c1a7d52e6_fix_rls_policies.py', 'r') as f:
    content = f.read()

direct_section = content.split('TENANT_SCOPED_DIRECT = [')[1].split(']')[0]

for table in indirect_tables:
    if f'"{table}"' in direct_section:
        print(f'{table}: IN TENANT_SCOPED_DIRECT')
    else:
        print(f'{table}: NOT in TENANT_SCOPED_DIRECT')