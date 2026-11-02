import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the backup creation section
idx = content.find('Created backup with ID')
if idx == -1:
    print('Not found')
else:
    end = min(len(content), idx + 1000)
    with codecs.open('debug_backup_section.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:end])
    print('Written to debug_backup_section.txt')