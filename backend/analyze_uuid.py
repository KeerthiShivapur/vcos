import ast

with open('func_source.py', 'r', encoding='utf-8') as f:
    source = f.read()

tree = ast.parse(source)

# Find all assignments to uuid
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == 'uuid':
                print(f'Assignment to uuid at line {node.lineno}: {ast.unparse(node)}')
        if isinstance(node, ast.Tuple):
            for elt in node.elts:
                if isinstance(elt, ast.Name) and elt.id == 'uuid':
                    print(f'Tuple assignment to uuid at line {node.lineno}: {ast.unparse(node)}')
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id == 'uuid':
            print(f'Annotated assignment to uuid at line {node.lineno}: {ast.unparse(node)}')
    elif isinstance(node, ast.For):
        if isinstance(node.target, ast.Name) and node.target.id == 'uuid':
            print(f'For loop with uuid at line {node.lineno}')
    elif isinstance(node, ast.comprehension):
        if node.target.id == 'uuid':
            print(f'Comprehension with uuid at line {node.lineno}')
    elif isinstance(node, ast.NamedExpr):
        if node.target.id == 'uuid':
            print(f'Walrus operator with uuid at line {node.lineno}')
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == 'uuid' or alias.asname == 'uuid':
                print(f'Import uuid at line {node.lineno}')
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name == 'uuid' or alias.asname == 'uuid':
                print(f'From import uuid at line {node.lineno}')
    elif isinstance(node, ast.With):
        for item in node.items:
            if item.optional_vars and isinstance(item.optional_vars, ast.Name) and item.optional_vars.id == 'uuid':
                print(f'With uuid at line {node.lineno}')
    elif isinstance(node, ast.ExceptHandler):
        if node.name == 'uuid':
            print(f'Except uuid at line {node.lineno}')
    elif isinstance(node, ast.FunctionDef):
        for arg in node.args.args:
            if arg.arg == 'uuid':
                print(f'Function param uuid at line {node.lineno}')
        for arg in node.args.kwonlyargs:
            if arg.arg == 'uuid':
                print(f'Kwonly arg uuid at line {node.lineno}')
        if node.args.vararg and node.args.vararg.arg == 'uuid':
            print(f'Vararg uuid at line {node.lineno}')
        if node.args.kwarg and node.args.kwarg.arg == 'uuid':
            print(f'Kwarg uuid at line {node.lineno}')