with open('app/services/release_failure_recovery.py', 'r') as f:
    content = f.read()

# Fix the return statement in inject_failure
old = '''        await db.flush()
        
        logger.warning(f"Injected failure {failure_type} at {failure_type} for release {release_id}")
        return release'''

new = '''        await db.flush()
        
        logger.warning(f"Injected failure {failure_type} at {failure_point} for release {release_id}")
        return injection'''

content = content.replace(old, new)

with open('app/services/release_failure_recovery.py', 'w') as f:
    f.write(content)
print('Done')