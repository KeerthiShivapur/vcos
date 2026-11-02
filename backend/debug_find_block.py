import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the second critical_checks
idx = content.find('critical_checks', content.find('critical_checks') + 100)
print(f'Found at: {idx}')

# Get the section
section = content[max(0,idx-100):idx+500]
with codecs.open('debug_section.txt', 'w', encoding='utf-8') as f:
    f.write(section)
print('Section written to debug_section.txt')