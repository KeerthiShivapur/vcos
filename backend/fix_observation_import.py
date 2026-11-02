with open('create_company_state.py', 'r') as f:
    content = f.read()

# Add the missing imports at the module level
# Find the line with the canonical_integration import and add CanonicalObservation, CorrelationContext
content = content.replace(
    'from app.models.canonical_integration import Connector, ConnectorInstance as CI, ConnectorCapability, ExternalIdentityMapping, SyncRun, SyncCursor, ExternalEvent',
    'from app.models.canonical_integration import Connector, ConnectorInstance as CI, ConnectorCapability, ExternalIdentityMapping, SyncRun, SyncCursor, ExternalEvent, CanonicalObservation, CorrelationContext, SourceAuthority, ExternalConflict, ExternalOperation, IntegrationHealth'
)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Added CanonicalObservation and CorrelationContext to module imports')