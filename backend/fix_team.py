with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix workforce component test - add code field to team
old = '''        team = Team(organization_id=org.id, name="Backend", department_id=dept.id)'''

new = '''        team = Team(organization_id=org.id, name="Backend", code="BE", department_id=dept.id)'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')