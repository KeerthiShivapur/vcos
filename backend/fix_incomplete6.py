with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_text = '''        org = production_company_real_pg["organization"]
        
        # Create a restore operation that will fail
        from app.models.backup_manifest import RestoreOperation
        
        restore_op = RestoreOperation(
            id=f"rop-fail-{uuid.uuid4().hex[:12]}",
            backup_id="nonexistent-backup",
            organization_id=org_id,'''

new_text = '''        org = production_company_real_pg["organization"]
        org_id = org.id
        
        # Create a restore operation that will fail
        from app.models.backup_manifest import RestoreOperation
        
        restore_op = RestoreOperation(
            id=f"rop-fail-{uuid.uuid4().hex[:12]}",
            backup_id="nonexistent-backup",
            organization_id=org_id,'''

content = content.replace(old_text, new_text)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed")