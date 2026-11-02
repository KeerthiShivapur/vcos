"""Rewrite the service file with proper formatting."""
import ast
import sys

with open('app/services/canonical_reality_integrity_service.py', 'r') as f:
    content = f.read()

# Parse to check syntax
try:
    tree = ast.parse(content)
    print("AST parsing successful")
except SyntaxError as e:
    print(f"Syntax error: {e}")
    print(f"Line {e.lineno}: {e.text}")
    sys.exit(1)

# Use ast.unparse to regenerate (Python 3.9+)
import sys
if sys.version_info >= (3, 9):
    import ast
    new_content = ast.unparse(ast.parse(content))
    with open('app/services/canonical_reality_integrity_service.py', 'w') as f:
        f.write(new_content)
    print("Rewritten with ast.unparse")
else:
    print("Python version too old for ast.unparse")