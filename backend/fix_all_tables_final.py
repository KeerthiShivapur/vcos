import re

# Fix ocsf_siem.py
with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'r') as f:
    content = f.read()

# Fix all duplicated __table_args__ = ( patterns
# Pattern: __table_args__ = (\n    __table_args__ = (
# Replace with single __table_args__ = (

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

# Now fix each __table_args__ to add extend_existing at the end
# Find all __table_args__ = ( ... ) blocks and add extend_existing

# More robust approach: find each class definition and fix its __table_args__
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
                # Remove any existing extend_existing lines
                pass
            else:
                fixed_lines.append(line)
            i += 1
            # Check if we closed the brace
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
    else:
        fixed_lines.append(line)
        i += 1

content = '\n'.join(fixed_lines)

with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'w') as f:
    f.write(content)

print("Fixed ocsf_siem.py")