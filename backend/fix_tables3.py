import re

with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'r') as f:
    content = f.read()

# Fix all __table_args__ to include extend_existing=True
# More specific regex that only matches the actual __table_args__ assignment
def fix_table_args(match):
    args = match.group(0)
    # Check if extend_existing already exists
    if "extend_existing" in args:
        return args
    # Add extend_existing before the closing ) of the tuple
    # The tuple ends with ), so we replace the last ), with , {"extend_existing": True},)
    if args.endswith('),'):
        return args[:-2] + ', {"extend_existing": True},)'
    elif args.endswith(')'):
        return args[:-1] + ', {"extend_existing": True})'
    return args

# More precise regex - only match __table_args__ = ( ... ) with proper nesting
# We'll process line by line to be safer
lines = content.split('\n')
in_table_args = False
table_args_lines = []
fixed_lines = []
brace_count = 0

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

with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'w') as f:
    f.write(content)

print("Fixed ocsf_siem.py")