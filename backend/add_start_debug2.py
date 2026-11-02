with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Add debug at the start of ConcurrentSessionHarness.session_for
old = b'    @asynccontextmanager\r\n    async def session_for(self, actor_id: str):\r\n        actor = self.actors.get(actor_id)\r\n        if not actor:\r\n            raise ValueError(f"Actor {actor_id} not found in harness")\r\n        \r\n        async with self.session_factory() as session:'
new = b'    @asynccontextmanager\r\n    async def session_for(self, actor_id: str):\r\n        print(f"DEBUG ConcurrentSessionHarness.session_for START for {actor_id}", flush=True)\r\n        actor = self.actors.get(actor_id)\r\n        if not actor:\r\n            raise ValueError(f"Actor {actor_id} not found in harness")\r\n        \r\n        async with self.session_factory() as session:'

content = content.replace(old, new)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Added start debug')