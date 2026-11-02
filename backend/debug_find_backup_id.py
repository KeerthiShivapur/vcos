import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find backup_id generation
search = 'backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])'
idx = content.find(search)
if idx == -1:
    print('Not found')
else:
    end = min(len(content), idx + 200)
    with codecs.open('debug_backup_id.txt', 'w', encoding='utf-8') as f:
        f.write(content[max(0,idx-100):end])
    print('Written to debug_backup_id.txt')