import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the test function start
idx = content.find('async def test_complete_production_dr_lifecycle')
if idx == -1:
    print('Test function not found')
else:
    # Find the docstring end and the first code line
    docstring_end = content.find('"""', content.find('"""', idx) + 3) + 3
    # Find the first code line after docstring
    code_start = content.find('\n', docstring_end) + 1
    while content[code_start].strip() == '':
        code_start = content.find('\n', code_start) + 1
    
    # Insert cleanup after the first few variable assignments
    insert_point = content.find('org = production_company["organization"]', docstring_end)
    if insert_point == -1:
        insert_point = content.find('org = production_company', docstring_end)
    
    if insert_point != -1:
        # Find the line start
        line_start = content.rfind('\n', 0, insert_point) + 1
        insert_code = '\n        # Clean up any leftover UniversalCompanyContext entries from previous test runs\n        from app.models.universal_company_context import UniversalCompanyContext\n        from sqlalchemy import delete\n        await db_session.execute(delete(UniversalCompanyContext))\n        await db_session.flush()\n\n'
        content = content[:line_start] + insert_code + content[line_start:]
        
        with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Added cleanup at test start')
    else:
        print('Could not find insert point')