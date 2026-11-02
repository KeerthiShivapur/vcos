with open('tests/acceptance/test_release_candidate_slice_2c.py', 'r') as f:
    lines = f.readlines()

# Find the line with "await pg_db_session.expire_all()" and fix it
new_lines = []
for line in lines:
    if 'await pg_db_session.expire_all()' in line:
        line = line.replace('await pg_db_session.expire_all()', 'pg_db_session.expire_all()')
    new_lines.append(line)

with open('tests/acceptance/test_release_candidate_slice_2c.py', 'w') as f:
    f.writelines(new_lines)
print('Done')