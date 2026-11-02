import ast

# Read raw bytes
with open('app/core/realtime/crdt.py', 'rb') as f:
    data = f.read()

# Check for BOM
print("First 4 bytes:", data[:4])

# Check for any non-ASCII characters
non_ascii = [(i, b) for i, b in enumerate(data) if b > 127]
print(f"Non-ASCII bytes: {len(non_ascii)}")
if non_ascii:
    for i, b in non_ascii[:20]:
        print(f"  Position {i}: 0x{b:02x} ({chr(b) if 32 <= b < 127 else '?'})")

# Try parsing with explicit encoding
source = open('app/core/realtime/crdt.py', 'r', encoding='utf-8').read()
try:
    ast.parse(source)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax Error: {e}")
    print(f"Line {e.lineno}: {e.text}")