import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the backup creation section
search_str = 'backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])'
idx = content.find(search_str)
if idx == -1:
    print('Not found')
else:
    end = min(len(content), idx + 2000)
    with codecs.open('debug_backup_create.txt', 'w', encoding='utf-8') as f:
        f.write(content[max(0,idx-200):end])
    print('Written to debug_backup_create.txt')