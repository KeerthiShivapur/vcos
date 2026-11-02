with open('app/services/disaster_recovery_service.py', 'r') as f:
    content = f.read()

# Find the DRScenario enum and fix it
# Find the start and end of the DRScenario enum
start = content.find('class DRScenario(str, Enum):')
end = content.find('\n\n', content.find('class DRScenario(str, Enum):'))

# Extract the enum definition
enum_start = content.find('class DRScenario(str, Enum):')
enum_end = content.find('\n\n', enum_start)

# Extract the enum content
enum_content = content[enum_start:enum_end]

# Check if there are duplicates
print("DRScenario enum found")

# Let's just rewrite the entire DRScenario enum properly
old_enum = '''class DRScenario(str, Enum):
    """Disaster recovery scenarios."""
    
    REGION_OUTAGE = "region_outage"
    DB_FAILOVER = "db_failover"
    REPLICA_PROMOTION = "replica_promotion"
    RECOVERY_TEST = "recovery_test"
    STORAGE_FALLBACK = "storage_fallback"
    DB_CORRUPTION = "db_corruption"
    CONNECTION_LOSS = "connection_loss"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_FAILURE = "external_api_failure"
    WORKER_CRASH = "worker_crash"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"'''

# Find the actual content and replace
old_enum = content[content.find('class DRScenario(str, Enum):'):]
end_idx = old_enum.find('\n\nclass ')
if end_idx == -1:
    end_idx = len(old_enum)
old_enum = old_enum[:end_idx]

# Check what the actual enum looks like
print("Found enum start")
print(old_enum[:500])