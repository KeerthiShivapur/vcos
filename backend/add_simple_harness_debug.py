with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Find SimpleHarness.session_for and add debug
old = b'    @asynccontextmanager\r\n    async def session_for(self, actor_id: str):\r\n        async with self.session_factory() as session:\r\n            yield SessionContext(session=session, actor=None)'
new = b'    @asynccontextmanager\r\n    async def session_for(self, actor_id: str):\r\n        async with self.session_factory() as session:\r\n            print(f"DEBUG SimpleHarness: session_for {actor_id} start")\r\n            try:\r\n                yield SessionContext(session=session, actor=None)\r\n            finally:\r\n                print(f"DEBUG SimpleHarness: session_for {actor_id} end")'

content = content.replace(old, new)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Added SimpleHarness debug output')