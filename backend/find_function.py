with open('app/intelligence/canonical_mutation.py', 'rb') as f:
    lines = f.read().split(b'\n')

# Find the validate_provenance function start and end
start_idx = None
end_idx = None
brace_count = 0
in_function = False

for i, line in enumerate(lines):
    if b'async def validate_provenance(' in line:
        start_idx = i
        in_function = True
        continue
    if in_function:
        if b'async def ' in line and i > 0:
            # Found next function
            end_idx = i
            break
        # Could also check for the end of the function

if start_idx is not None:
    print(f"Function starts at line {start_idx}")
    # Find the end by looking for the next 'async def ' or end of file
    for i in range(start_idx + 1, len(lines)):
        if b'async def ' in lines[i] and i > start_idx:
            end_idx = i
            break
    if end_idx is None:
        end_idx = len(lines)
    print(f"Function spans lines {start_idx} to {end_idx}")
    print(f"Lines: {end_idx - start_idx}")

# Print the function
for i in range(start_idx, min(end_idx, start_idx + 100)):
    print(f"{i}: {lines[i].decode('utf-8', errors='replace')}")