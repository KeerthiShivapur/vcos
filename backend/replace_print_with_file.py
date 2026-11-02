with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Replace print with file write for debugging
old = b'print(f"DEBUG ConcurrentSessionHarness.session_for START for {actor_id}", flush=True)'
new = b'with open("harness_debug.log", "a") as f: f.write(f"DEBUG ConcurrentSessionHarness.session_for START for {actor_id}\\n")'

content = content.replace(old, new)

old = b'print(f"DEBUG ConcurrentSessionHarness: committing session for {actor_id}", flush=True)'
new = b'with open("harness_debug.log", "a") as f: f.write(f"DEBUG ConcurrentSessionHarness: committing session for {actor_id}\\n")'

content = content.replace(old, new)

old = b'print(f"DEBUG ConcurrentSessionHarness: committed session for {actor_id}", flush=True)'
new = b'with open("harness_debug.log", "a") as f: f.write(f"DEBUG ConcurrentSessionHarness: committed session for {actor_id}\\n")'

content = content.replace(old, new)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Replaced print with file write')