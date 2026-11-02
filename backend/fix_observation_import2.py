with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix the import - CanonicalObservation and CorrelationContext are in observability, not canonical_integration
content = content.replace(
    'from app.models.canonical_integration import Connector, ConnectorInstance as CI, ConnectorCapability, ExternalIdentityMapping, SyncRun, SyncCursor, ExternalEvent, CanonicalObservation, CorrelationContext, SourceAuthority, ExternalConflict, ExternalOperation, IntegrationHealth',
    'from app.models.canonical_integration import Connector, ConnectorInstance as CI, ConnectorCapability, ExternalIdentityMapping, SyncRun, SyncCursor, ExternalEvent, SourceAuthority, ExternalConflict, ExternalOperation, IntegrationHealth'
)

# Add to observability import
content = content.replace(
    'from app.models.observability import HealthDimension',
    'from app.models.observability import HealthDimension, CanonicalObservation, CorrelationContext'
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed imports for CanonicalObservation and CorrelationContext')