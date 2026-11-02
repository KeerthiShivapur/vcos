import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the import
old_import = 'from app.models.universal_company_context import UniversalCompanyContext'
new_import = 'from app.models import UniversalCompanyContext'

if old_import in content:
    content = content.replace(old_import, new_import)
    with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed import path')
else:
    print('Pattern not found')