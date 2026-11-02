import re

with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'r') as f:
    content = f.read()

# Fix all __table_args__ to include extend_existing=True
def fix_table_args(match):
    args = match.group(0)
    # Check if extend_existing already exists
    if "extend_existing" in args:
        return args
    # Add extend_existing before the closing )
    return args.rstrip()[:-1] + ', {"extend_existing": True},)'

content = re.sub(r'__table_args__ = \([\s\S]*?\)', fix_table_args, content, flags=re.DOTALL)

with open('D:/vcos1/workspace/vcos/backend/app/core/ocsf_siem.py', 'w') as f:
    f.write(content)

print("Fixed ocsf_siem.py")