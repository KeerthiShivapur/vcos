import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the disaster recovery section and fix backup selection
# The issue is that the disaster recovery service is not using the backup_id we created
# Let's ensure the restore uses the correct backup_id

# Find the restore_from_backup call
idx = content.find('restore_service.restore_from_backup(')
if idx == -1:
    print('Not found')
else:
    end = min(len(content), idx + 500)
    with codecs.open('debug_restore.txt', 'w', encoding='utf-8') as f:
        f.write(content[max(0,idx-200):end])
    print('Written to debug_restore.txt')