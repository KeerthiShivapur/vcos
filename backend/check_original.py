with open('work_original.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Search for MeetingAgendaItemOut and MeetingActionItemOut
for cls in ['MeetingAgendaItemOut', 'MeetingActionItemOut', 'AgendaItemOut', 'ActionItemOut', 'MeetingAgendaItemCreate', 'MeetingActionItemCreate']:
    idx = content.find('class ' + cls)
    if idx >= 0:
        end = content.find('\nclass ', idx + 1)
        if end == -1:
            end = len(content)
        print(f'=== {cls} ===')
        print(content[idx:idx+500])
        print()
    else:
        print(f'{cls}: NOT FOUND')

# Also check for AgendaItemOut and ActionItemOut
for cls in ['AgendaItemOut', 'ActionItemOut']:
    idx = content.find('class ' + cls)
    if idx >= 0:
        end = content.find('\nclass ', idx + 1)
        if end == -1:
            end = len(content)
        print(f'=== {cls} ===')
        print(content[idx:idx+500])
        print()
    else:
        print(f'{cls}: NOT FOUND')