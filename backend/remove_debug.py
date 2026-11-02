with open('app/intelligence/governed_commitment_engine.py', 'r') as f:
    content = f.read()
content = content.replace('print(f"DEBUG: old_state={old_state}, new_state={new_state}")\n        ', '')
with open('app/intelligence/governed_commitment_engine.py', 'w') as f:
    f.write(content)
print('Removed debug print')