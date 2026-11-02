with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the historical check section and move it after the contradiction section
# Find start and end of historical check
hist_start = -1
hist_end = -1
contra_start = -1
contra_end = -1

for i, line in enumerate(lines):
    if '# 5. HISTORICAL EPISTEMIC STATE PROTECTION' in line:
        hist_start = i
    if '# 6. CONTRADICTION PRESERVATION INTEGRATION' in line:
        contra_start = i
    if contra_start != -1 and i > contra_start and '# 7.' in lines[i]:
        contra_end = i
        break
    if hist_start != -1 and i > hist_start and '# 6.' in lines[i]:
        hist_end = i

print(f"hist_start={hist_start}, hist_end={hist_end}, contra_start={contra_start}, contra_end={contra_end}")