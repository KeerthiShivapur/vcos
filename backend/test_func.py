import sys
with open('app/core/realtime/crdt.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check if we can parse just the problematic function
lines = content.split('\n')
func_start = None
for i, line in enumerate(content.split('\n')):
    if 'async def _publish_sync' in line:
        print(f"Function starts at line {i+1}")
        break

# Try parsing just from line 479 onwards
func_lines = content.split('\n')[478:510]
func_source = '\n'.join(func_lines)
print("Function source:")
print(func_source)

try:
    import ast
    ast.parse(func_source)
    print("Function syntax OK")
except SyntaxError as e:
    print(f"Syntax Error in function: {e}")
    print(f"Line {e.lineno}: {e.text}")