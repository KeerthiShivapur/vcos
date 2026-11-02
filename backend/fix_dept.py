with open('tests/acceptance/test_release_candidate_slice_2b.py', 'r') as f:
    content = f.read()

# Fix workforce component test - add code field to department
old = '''        dept = Department(organization_id=org.id, name="Engineering")
        pg_db_session.add(dept)
        await pg_db_session.flush()
        
        team = Team(organization_id=org.id, name="Backend", department_id=dept.id)'''

new = '''        dept = Department(organization_id=org.id, name="Engineering", code="ENG")
        pg_db_session.add(dept)
        await pg_db_session.flush()
        
        team = Team(organization_id=org.id, name="Backend", department_id=dept.id)'''

content = content.replace(old, new)

with open('tests/acceptance/test_release_candidate_slice_2b.py', 'w') as f:
    f.write(content)
print('Done')