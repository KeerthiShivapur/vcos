import codecs

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix ApprovalPolicy scope_type
content = content.replace(
    'parts.append(f"pol:{p.id}:{p.approval_type}:{p.scope_type}:{p.scope_id}")',
    'parts.append(f"pol:{p.id}:{p.approval_type}:{p.scope_id}")'
)

with codecs.open('tests/acceptance/test_production_deployment_dr_e2e.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed ApprovalPolicy scope_type')