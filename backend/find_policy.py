with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Find WorkAdapter class
idx = content.find('class WorkAdapter')
if idx >= 0:
    # Find the end of the class
    end = content.find('class ', idx + 10)
    if end == -1:
        end = len(content)
    work_adapter = content[idx:end]
    # Find all 'policy' references
    import re
    for m in re.finditer(r'policy', work_adapter):
        pos = m.start()
        print(repr(work_adapter[max(0,pos-50):pos+50]))
        print('---')