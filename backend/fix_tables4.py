import re

with open('D:/vcos1/workspace/vcos/backend/app/core/compliance_dashboards.py', 'r') as f:
    content = f.read()

# Fix all __table_args__ to include extend_existing=True
lines = content.split('\n')
in_table_args = False
brace_count = 0
fixed_lines = []

for line in lines:
    stripped = line.strip()
    
    if '__table_args__ = (' in line:
        in_table_args = True
        brace_count = 1
        table_args_lines = [line]
    elif in_table_args:
        # Count braces
        brace_count += line.count('(')
        brace_count -= line.count(')')
        table_args_lines.append(line)
        
        if brace_count == 0:
            # End of table_args
            table_args_text = '\n'.join(table_args_lines)
            if "extend_existing" not in table_args_text:
                # Add extend_existing before the closing )
                fixed = table_args_text.rstrip()
                if fixed.endswith('),'):  # ends with ),
                    fixed = fixed[:-2] + ', {"extend_existing": True},)'
                elif fixed.endswith(')'):  # ends with )
                    fixed = fixed[:-1] + ', {"extend_existing": True})'
                fixed_lines.append(fixed)
            else:
                fixed_lines.extend(table_args_lines)
            in_table_args = False
            table_args_lines = []
        continue
    
    fixed_lines.append(line)

content = '\n'.join(fixed_lines)

with open('D:/vcos1/workspace/vcos/backend/app/core/compliance_dashboards.py', 'w') as f:
    f.write(content)

print("Fixed compliance_dashboards.py")