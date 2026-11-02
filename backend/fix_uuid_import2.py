import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the backup creation section
idx = content.find('backup_id = "bkp-{}".format(uuid.uuid4().hex[:12])')
if idx == -1:
    print('Not found')
else:
    # Find the start of the section
    section_start = content.rfind('        # Create backup manifest directly', 0, idx)
    if section_start == -1:
        print('Section start not found')
    else:
        # Insert import after the comment
        insert_idx = content.find('\n', section_start) + 1
        content = content[:insert_idx] + '        import uuid\n        import hashlib\n' + content[insert_idx:]
        with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Added uuid import')
    print('Section start not found')