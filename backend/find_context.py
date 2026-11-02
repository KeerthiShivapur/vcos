with open('app/services/onboarding_service.py', 'r') as f:
    content = f.read()

# Find the first occurrence and its surrounding context
idx = content.find('provisioning_started')
if idx >= 0:
    # Find the context.completed_steps.append before it
    start = max(0, idx - 500)
    end = min(len(content), idx + 500)
    print(content[start:end])
    print('===END FIRST===')

# Find second occurrence
idx2 = content.find('provisioning_started', idx + 1)
if idx2 >= 0:
    start = max(0, idx2 - 500)
    end = min(len(content), idx2 + 500)
    print(content[start:end])
    print('===END SECOND===')