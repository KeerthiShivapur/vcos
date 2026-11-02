with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Add debug output to ConcurrentSessionHarness.session_for
old = b'    @asynccontextmanager\r\n    async def session_for(self, actor_id: str):\r\n        """Create a new session bound to the actor\'s context with automatic commit."""\r\n        actor = self.actors.get(actor_id)\r\n        if not actor:\r\n            raise ValueError(f"Actor {actor_id} not found in harness")\r\n        \r\n        async with self.session_factory() as session:'
new = b'    @asynccontextmanager\r\n    async def session_for(self, actor_id: str):\r\n        """Create a new session bound to the actor\'s context with automatic commit."""\r\n        print(f"DEBUG ConcurrentSessionHarness.session_for START for {actor_id}", flush=True)\r\n        actor = self.actors.get(actor_id)\r\n        if not actor:\r\n            raise ValueError(f"Actor {actor_id} not found in harness")\r\n        \r\n        async with self.session_factory() as session:'

content = content.replace(old, new)

# Add debug output to finally block
old = b'                finally:\r\n                    self._active_sessions.pop(actor_id, None)\r\n                    # Explicitly commit to ensure persistence\r\n                    await session.commit()\r\n    \r\n    def get_caller'
new = b'                finally:\r\n                    self._active_sessions.pop(actor_id, None)\r\n                    # Explicitly commit to ensure persistence\r\n                    print(f"DEBUG ConcurrentSessionHarness: committing session for {actor_id}", flush=True)\r\n                    await session.commit()\r\n                    print(f"DEBUG ConcurrentSessionHarness: committed session for {actor_id}", flush=True)\r\n    \r\n    def get_caller'

content = content.replace(old, new)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Added debug output')