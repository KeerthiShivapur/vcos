import re

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the backup creation section and add commit after it
old_text = """        backup_id = backup_metadata.backup_id
        
        logger.info(f"✅ Real backup created: {backup_id}")"""

new_text = """        backup_id = backup_metadata.backup_id
        
        # Ensure backup is committed so restore can reference it
        await pg_db_session.commit()
        
        logger.info(f"✅ Real backup created: {backup_id}")"""

content = content.replace(old_text, new_text)

with open('tests/acceptance/test_deployment_dr_production_verification.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated backup commit")