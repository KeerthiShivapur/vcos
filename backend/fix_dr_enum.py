with open('app/services/disaster_recovery_service.py', 'r') as f:
    content = f.read()

# Find the DRScenario enum and replace it entirely
old_enum_start = content.find('class DRScenario(str, Enum):')
enum_end = content.find('\n\nclass ', content.find('class DRScenario(str, Enum):'))
if enum_end == -1:
    enum_end = content.find('\n\n', content.find('class DRScenario(str, Enum):'))
    if enum_end == -1:
        enum_end = len(content)

old_enum = content[content.find('class DRScenario(str, Enum):'):enum_end]

# Build the new enum
new_enum = '''class DRScenario(str, Enum):
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
    EXTERNAL_RATE_LIMIT = "external_rate_limit"
    EXTERNAL_PARTIAL_RESPONSE = "external_partial_response"
    EXTERNAL_DUPLICATE_DELIVERY = "external_duplicate_delivery"
    EXTERNAL_OUT_OF_ORDER = "external_out_of_order"
    EXTERNAL_UNKNOWN_OUTCOME = "external_unknown_outcome"

'''

# Replace the old enum with the new one
enum_start = content.find('class DRScenario(str, Enum):')
enum_end = content.find('\n\nclass ', content.find('class DRScenario(str, Enum):'))
if enum_end == -1:
    enum_end = len(content)

new_content = content[:content.find('class DRScenario(str, Enum):')] + new_enum + content[enum_end:]

with open('app/services/disaster_recovery_service.py', 'w') as f:
    f.write(new_content)

print('Fixed DRScenario enum')