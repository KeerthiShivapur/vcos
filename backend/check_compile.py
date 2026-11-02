import sys

# Try compile instead of ast.parse
source = open('app/core/realtime/crdt.py', 'r', encoding='utf-8').read()

try:
    compile(source, 'crdt.py', 'exec')
    print("Compile OK")
except SyntaxError as e:
    print(f"Syntax Error: {e}")
    print(f"Line {e.lineno}: {e.text}")