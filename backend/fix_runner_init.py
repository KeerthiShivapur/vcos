with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Fix ConcurrentTestRunner.__init__ to accept harness as first argument
old = b'class ConcurrentTestRunner:\r\n    """Runs concurrent operations with controlled scheduling.\r\n    \r\n    Each concurrent operation gets its own database session to avoid\r\n    SQLAlchemy session sharing issues.\r\n    """\r\n    \r\n    def __init__(\r\n        self,\r\n        session_factory,\r\n        actors: List[\'CanonicalActor\'],\r\n        barrier: Optional[\'ConcurrencyBarrier\'] = None,\r\n    ):\r\n        self.session_factory = session_factory\r\n        self.actors = {a.user_id: a for a in actors}\r\n        self.results: List[ConcurrentTestResult] = []\r\n        self._results_lock = asyncio.Lock()\r\n        self.barrier = barrier\r\n        # Create a simple harness-like object with session_for method\r\n        class SimpleHarness:\r\n            def __init__(self, session_factory):\r\n                self.session_factory = session_factory\r\n            \r\n            @asynccontextmanager\r\n            async def session_for(self, actor_id: str):\r\n                async with self.session_factory() as session:\r\n                    yield Se'

new = b'class ConcurrentTestRunner:\r\n    """Runs concurrent operations with controlled scheduling.\r\n    \r\n    Each concurrent operation gets its own database session to avoid\r\n    SQLAlchemy session sharing issues.\r\n    """\r\n    \r\n    def __init__(\r\n        self,\r\n        harness,\r\n        actors: List[\'CanonicalActor\'],\r\n        barrier: Optional[\'ConcurrencyBarrier\'] = None,\r\n        session_factory=None,\r\n    ):\r\n        self.harness = harness\r\n        self.session_factory = session_factory or harness.session_factory\r\n        self.actors = {a.user_id: a for a in actors}\r\n        self.results: List[ConcurrentTestResult] = []\r\n        self._results_lock = asyncio.Lock()\r\n        self.barrier = barrier'

content = content.replace(old, new)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Fixed ConcurrentTestRunner.__init__')