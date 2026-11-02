import codecs

with codecs.open('app/services/restore_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the cross-tenant test exception handling
idx = content.find('print("DEBUG CROSS: Caught exception')
if idx == -1:
    print('Not found')
else:
    end = min(len(content), idx + 2000)
    with codecs.open('debug_cross_tenant7.txt', 'w', encoding='utf-8') as f:
        f.write(content[idx:idx+2000])
    print('Written to debug_cross_tenant7.txt')