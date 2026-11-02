import re

with open('app/models/execution_strategy.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Find CompanyAuthorization
idx = content.find('class CompanyAuthorization')
if idx >= 0:
    class_content = content[idx:idx+2000]
    # Find __tablename__
    match = re.search(r'__tablename__\s*=\s*["\']([^"\']+)["\']', class_content)
    if match:
        print(f'Table name: {match.group(1)}')
    else:
        print('No table name found')