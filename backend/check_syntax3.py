import ast
import sys

with open('app/core/realtime/crdt.py', 'r', encoding='utf-8') as f:
    source = f.read()

try:
    ast.parse(source)
    print("Syntax OK")
    sys.exit(0)
except SyntaxError as e:
    print(f"Syntax Error: {e}")
    print(f"Line {e.lineno}: {e.text}")
    # Show context
    lines = open('app/core/realtime/crdt.py', 'r', encoding='utf-8').readlines()
    for i in range(max(0, e.lineno-5), min(len(lines), e.lineno+5)):
        marker = ">>>" if i+1 == e.lineno else "   "
        print(f"{marker} {i+1:4d}: {lines[i].rstrip()}")
    sys.exit(1)