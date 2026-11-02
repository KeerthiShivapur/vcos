import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add more debug logging around commit
old_commit = '''        await db_session.flush()
        await db_session.commit()  # Ensure cleanup is committed
        logger.info("Cleanup committed, deleted old backups")'''

new_commit = '''        await db_session.flush()
        print("DEBUG: About to commit cleanup")
        await db_session.commit()
        print("DEBUG: Cleanup commit successful")
        logger.info("Cleanup committed, deleted old backups")'''

if old in content:
    content = content.replace(old_commit, new_commit)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Added debug logging for commit')
else:
    print('Pattern not found')