import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix CompanyDecision why -> rationale in multi-tenant test
old1 = 'why="Org {i+1} Decision",'
new1 = 'rationale="Org {i+1} Decision",'

old2 = 'why="Verify company can make new decisions after restore",'
new2 = 'rationale="Verify company can make new decisions after restore",'

if old1 in content:
    content = content.replace(old1, new1)
    print('Fixed first why')

if old2 in content:
    content = content.replace(old2, new2)
    print('Fixed second why')
else:
    print('Second not found')

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')