"""Script to remove indirect tables from TENANT_SCOPED_DIRECT in migration files."""

indirect_tables = {
    "backup_corruption_tests",
    "backup_verification_results",
    "deployment_completeness_dimensions",
    "developer_api_keys",
    "developer_applications",
    "developer_certifications",
    "developer_subscriptions",
    "developer_usage",
    "developers",
    "devices",
    "industry_templates",
    "marketplace_reviews",
    "optimization_alternatives",
    "plugin_versions",
    "provisioning_steps",
    "role_permissions",
    "subscription_invoices",
    "subscription_payments",
    "workflow_edges",
    "workflow_execution_steps",
    "workflow_nodes",
    "workflow_versions",
}

# Process 9f3c1a7d52e5
with open('alembic/versions/9f3c1a7d52e5_enable_rls_tenant_isolation.py', 'r') as f:
    content = f.read()

# Find TENANT_SCOPED_DIRECT list
start = content.find('TENANT_SCOPED_DIRECT = [')
end = content.find(']', start)
direct_section = content[start:end+1]

# Remove indirect tables
lines = direct_section.split('\n')
new_lines = []
for line in lines:
    # Check if this line contains one of the indirect tables
    keep = True
    for table in indirect_tables:
        if f'"{table}"' in line:
            keep = False
            print(f"Removing {table} from 9f3c1a7d52e5")
            break
    if keep:
        new_lines.append(line)

new_direct_section = '\n'.join(new_lines)
content = content[:start] + new_direct_section + content[end+1:]

# Update comment count
content = content.replace('TENANT_SCOPED_DIRECT tables (640)', 'TENANT_SCOPED_DIRECT tables (618)')

with open('alembic/versions/9f3c1a7d52e5_enable_rls_tenant_isolation.py', 'w') as f:
    f.write(content)

print("Updated 9f3c1a7d52e5")

# Process 9f3c1a7d52e6
with open('alembic/versions/9f3c1a7d52e6_fix_rls_policies.py', 'r') as f:
    content = f.read()

# Find TENANT_SCOPED_DIRECT list
start = content.find('TENANT_SCOPED_DIRECT = [')
end = content.find(']', start)
direct_section = content[start:end+1]

# Remove indirect tables
lines = direct_section.split('\n')
new_lines = []
for line in lines:
    keep = True
    for table in indirect_tables:
        if f'"{table}"' in line:
            keep = False
            print(f"Removing {table} from 9f3c1a7d52e6")
            break
    if keep:
        new_lines.append(line)

new_direct_section = '\n'.join(new_lines)
content = content[:start] + new_direct_section + content[end+1:]

# Update comment count
content = content.replace('TENANT_SCOPED_DIRECT tables (640)', 'TENANT_SCOPED_DIRECT tables (618)')

with open('alembic/versions/9f3c1a7d52e6_fix_rls_policies.py', 'w') as f:
    f.write(content)

print("Updated 9f3c1a7d52e6")