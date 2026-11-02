with open('app/services/external_operation_service.py', 'r') as f:
    content = f.read()

# Find the call to _mark_unknown in verify_operation
idx = content.find('_mark_unknown(db, operation, "Result verification failed")')
if idx >= 0:
    print(content[max(0,idx-200):idx+200])