import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging after cleanup commit
old_commit = '''        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed
        
        # Create backup manifest directly with correct organization_id'''

new_commit = '''        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed
        logger.info("Cleanup committed, deleted old backups")
        
        # Create backup manifest directly with correct organization_id'''

if old_commit in content:
    content = content.replace(old_commit, new_commit)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging')
else:
    print('Pattern not found')