with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix the execute method indentation in WorkAdapter
old_code = '''                async def execute(self) -> AdapterResult:
                """Execute work lifecycle."""
        return await self.provision()'''

new_code = '''        async def execute(self) -> AdapterResult:
            """Execute work lifecycle."""
            return await self.provision()'''

content = content.replace(
    '                async def execute(self) -> AdapterResult:\n                """Execute work lifecycle."""\n        return await self.provision()',
    '        async def execute(self) -> AdapterResult:\n            """Execute work lifecycle."""\n            return await self.provision()'
)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed')