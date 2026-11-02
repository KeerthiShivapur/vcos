# Fix compliance_dashboards.py
import re

with open('D:/vcos1/workspace/vcos/backend/app/core/compliance_dashboards.py', 'r') as f:
    content = f.read()

# Fix duplicated __table_args__ = (
content = re.sub(
    r'__table_args__ = \(\s*\n\s*__table_args__ = \(',
    '__table_args__ = (',
    content
)

# Fix Index with extend_existing inside (wrong place)
content = re.sub(
    r'Index\("([^"]+)",\s*"([^"]+)",\s*\{\s*"extend_existing":\s*True\s*\}\s*,\)',
    r'Index("\1", "\2")',
    content
)

# Fix each __table_args__ block to add extend_existing at the end
lines = content.split('\n')
fixed_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if '__table_args__ = (' in line:
        # Collect the full table_args block
        table_args_lines = [line]
        i += 1
        brace_count = line.count('(') - line.count(')')
        while i < len(lines) and brace_count > 0:
            line = lines[i]
            brace_count += line.count('(')
            brace_count -= line.count(')')
            if 'extend_existing' in line:
                # Skip any existing extend_existing lines
                pass
            else:
                fixed_lines.append(line)
            i += 1
            if brace_count <= 0:
                # Add extend_existing before closing )
                fixed_lines[-1] = fixed_lines[-1].rstrip()
                if fixed_lines[-1].endswith('),'):
                    fixed_lines[-1] = fixed_lines[-1][:-2] + ', {"extend_existing": True},)'
                elif fixed_lines[-1].endswith(')'):
                    fixed_lines[-1] = fixed_lines[-1][:-1] + ', {"extend_existing": True})'
    else:
        fixed_lines.append(line)
    i += 1

content = '\n'.join(fixed_lines)

with open('D:/vcos1/workspace/vcos/backend/app/core/compliance_dashboards.py', 'w') as f:
    f.write(content)

print("Fixed compliance_dashboards.py")