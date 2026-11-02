with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Add debug output to session_for
old = b'            try:\r\n                yield SessionContext(session=session, actor=actor)\r\n            finally:\r\n                self._active_sessions.pop(actor_id, None)\r\n                # Explicitly commit to ensure persistence\r\n                await session.commit()'
new = b'            try:\r\n                yield SessionContext(session=session, actor=actor)\r\n            finally:\r\n                self._active_sessions.pop(actor_id, None)\r\n                # Explicitly commit to ensure persistence\r\n                print(f"DEBUG harness: committing session for {actor_id}")\r\n                await session.commit()\r\n                print(f"DEBUG harness: committed session for {actor_id}")'

content = content.replace(old, new)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Added harness debug output')