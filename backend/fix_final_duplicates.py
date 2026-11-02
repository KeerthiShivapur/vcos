with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'r') as f:
    content = f.read()

# Fix all duplicate state parameters
content = content.replace(
    'state="completed",\n            state="completed",\n            completed_at=utcnow(),',
    'state="completed",\n            completed_at=utcnow(),'
)

content = content.replace(
    'state="completed",\n            state="completed",\n            completed_by=test_employee.id,',
    'state="completed",\n            completed_by=test_employee.id,'
)

content = content.replace(
    'state="completed",\n            state="completed",\n            completed_by=test_employee.id,',
    'state="completed",\n            completed_by=test_employee.id,'
)

with open('D:\\vcos1\\workspace\\vcos\\backend\\tests\\test_gate8_5_canonical_organizational_intelligence.py', 'w') as f:
    f.write(content)

print('Fixed all duplicate state parameters')