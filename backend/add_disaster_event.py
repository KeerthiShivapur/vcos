# Add DisasterEvent and DisasterMetrics dataclasses before DisasterRecoveryService class
# Find the right place to insert them - right before "class DisasterRecoveryService:"
with open('app/services/disaster_recovery_service.py', 'r') as f:
    content = f.read()

# Find where to insert the new classes
insert_idx = content.find('class DisasterRecoveryService:')
if insert_idx == -1:
    insert_idx = content.find('class DisasterRecoveryService:')
    if insert_idx == -1:
        insert_idx = content.find('class DisasterRecoveryService')

if insert_idx >= 0:
    # Define the new classes to insert
    new_classes = '''@dataclass
class DisasterEvent:
    """Disaster event record."""
    disaster_id: str
    disaster_type: DisasterType
    severity: DisasterSeverity
    status: DisasterStatus
    organization_id: str
    detected_at: datetime
    declared_at: Optional[datetime] = None
    recovery_plan: Optional[str] = None
    backup_id: Optional[str] = None
    affected_systems: List[str] = field(default_factory=list)
    affected_tenants: List[str] = field(default_factory=list)
    rpo_target_minutes: int = 15
    rto_target_minutes: int = 30
    actual_rpo_minutes: Optional[int] = None
    actual_rto_minutes: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class DRMetrics:
    """DR metrics for a disaster event."""
    disaster_id: str
    rpo_target_minutes: int
    rpo_actual_minutes: Optional[int] = None
    rto_target_minutes: int = 30
    rto_actual_minutes: Optional[int] = None
    backup_used: Optional[str] = None
    backup_age_minutes: Optional[int] = None
    data_loss_bytes: int = 0
    data_loss_records: int = 0
    recovery_success: bool = False
    recovery_time_seconds: Optional[float] = None
    validation_passed: bool = False
    validation_details: Dict[str, Any] = field(default_factory=dict)


'''
    # Insert before DisasterRecoveryService class
    new_content = content[:insert_idx] + new_classes + '\n\n' + content[insert_idx:]
    
    with open('app/services/disaster_recovery_service.py', 'w') as f:
        f.write(new_content)
    
    print('Added DisasterEvent and DRMetrics classes')