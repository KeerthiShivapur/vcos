with open('tests/concurrency/context.py', 'rb') as f:
    content = f.read()

# Add flush=True to print statements
content = content.replace(
    b'print(f"DEBUG SimpleHarness: session_for {actor_id} start")',
    b'print(f"DEBUG SimpleHarness: session_for {actor_id} start", flush=True)'
)
content = content.replace(
    b'print(f"DEBUG SimpleHarness: session_for {actor_id} end")',
    b'print(f"DEBUG SimpleHarness: session_for {actor_id} end", flush=True)'
)

with open('tests/concurrency/context.py', 'wb') as f:
    f.write(content)
print('Added flush=True')