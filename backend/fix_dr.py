with open('app/services/disaster_recovery_service.py', 'r') as f:
    content = f.read()

# Fix the DRScenario enum - remove duplicate WORKER_CRASH and fix indentation
content = content.replace(
    '    WORKER_CRASH = "worker_crash"\n    DEPLOYMENT_FAILURE = "deployment_failure"\n    MIGRATION_FAILURE = "migration_failure"',
    '    DEPLOYMENT_FAILURE = "deployment_failure"\n    MIGRATION_FAILURE = "migration_failure"'
)

with open('app/services/disaster_recovery_service.py', 'w') as f:
    f.write(content)

print('Fixed')