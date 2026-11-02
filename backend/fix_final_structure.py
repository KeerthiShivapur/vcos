with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Remove the create_adapter function from the top (first 10 lines)
lines = content.split('\n')

# Find where the actual imports start
import_start = 0
for i, line in enumerate(lines):
    if line.strip().startswith('from ') or line.strip().startswith('import '):
        if 'AdapterContext' in line or 'typing' in line or 'typing' in line:
            # This is a real import line
            pass
        # Find first real import
        if 'from ' in line and 'typing' in line:
            break
        if 'import ' in line and 'typing' in line:
            break

# Rebuild content without the create_adapter at top
new_lines = []
skip = True
for i, line in enumerate(lines):
    if skip:
        if i >= 10:  # skip first 10 lines (the create_adapter function)
            skip = False
            new_lines.append(line)
    else:
        new_lines.append(line)

content = '\n'.join(new_lines)

# Remove any existing registry at the end
idx = content.find('# Registry of all adapters')
if idx >= 0:
    content = content[:content.rfind('# Registry of all adapters')]

# Append the registry and create_adapter at the end
with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content + '''

# Registry of all adapters
ADAPTER_REGISTRY: Dict[str, type] = {
    "setup_canonical_context": CompanyProvisioningAdapter,
    "provision_company": CompanyProvisioningAdapter,
    "configure_organization_structure": CompanyProvisioningAdapter,
    "configure_governance": GovernanceAdapter,
    "configure_integrations": IntegrationAdapter,
    "execute_initial_sync": IntegrationAdapter,
    "create_people": CompanyProvisioningAdapter,
    "test_identity_transitions": IdentityAdapter,
    "test_cross_entity_identity": IdentityAdapter,
    "define_roles_permissions": GovernanceAdapter,
    "test_authorization_decisions": GovernanceAdapter,
    "test_delegation_revocation": GovernanceAdapter,
    "test_privileged_operations": GovernanceAdapter,
    "define_work_types": WorkAdapter,
    "execute_work_lifecycle": WorkAdapter,
    "test_work_composition": WorkAdapter,
    "configure_finance": FinanceAdapter,
    "test_multi_currency_transactions": FinanceAdapter,
    "test_consolidation": FinanceAdapter,
    "configure_connectors": IntegrationAdapter,
    "test_inbound_observations": IntegrationAdapter,
    "test_reconciliation": IntegrationAdapter,
    "test_outbound_operations": IntegrationAdapter,
    "configure_company_brain": CompanyBrainAdapter,
    "test_context_retrieval": CompanyBrainAdapter,
    "test_temporal_queries": CompanyBrainAdapter,
    "test_governance_in_queries": CompanyBrainAdapter,
    "verify_memory_derivation": MemoryAdapter,
    "test_epistemic_status": MemoryAdapter,
    "test_longitudinal_memory": MemoryAdapter,
    "create_prediction": PredictionAdapter,
    "verify_prediction_non_canonical": PredictionAdapter,
    "test_governance_on_prediction": PredictionAdapter,
    "create_counterfactual": CounterfactualAdapter,
    "simulate_scenario": CounterfactualAdapter,
    "test_governed_commitment": CounterfactualAdapter,
    "configure_autonomy_policy": AutonomyAdapter,
    "test_autonomy_flow": AutonomyAdapter,
    "test_autonomous_execution": AutonomyAdapter,
    "simulate_continuity_event": ContinuityAdapter,
    "verify_history_intact": ContinuityAdapter,
    "verify_identity_continuous": ContinuityAdapter,
    "execute_migration": AcceptanceAdapter,
    "verify_migration_preservation": AcceptanceAdapter,
    "execute_ma": AcceptanceAdapter,
    "verify_ma_lineage": AcceptanceAdapter,
    "inject_failure": AcceptanceAdapter,
    "verify_tenant_isolation_under_failure": SecurityAdapter,
    "test_governed_recovery": DRAdapter,
    "run_longitudinal_simulation": AcceptanceAdapter,
    "verify_temporal_integrity": AcceptanceAdapter,
    "verify_knowledge_timeline": AcceptanceAdapter,
    "test_backup": DRAdapter,
    "test_restore": DRAdapter,
    "verify_rpo_rto": DRAdapter,
    "test_cross_tenant_rejection": SecurityAdapter,
    "test_cross_scope_rejection": SecurityAdapter,
    "test_provenance_spoofing": SecurityAdapter,
    "test_unauthorized_autonomy": SecurityAdapter,
    "test_api_canonical_semantics": AcceptanceAdapter,
    "test_api_governance": GovernanceAdapter,
    "verify_canonical_integrity": AcceptanceAdapter,
    "verify_invariants": AcceptanceAdapter,
}


async def create_adapter(action: str, context: AdapterContext) -> AcceptanceAdapter:
    """Factory function to create adapter for action."""
    adapter_class = ADAPTER_REGISTRY.get(action)
    if not adapter_class:
        return AcceptanceAdapter(context)
    return adapter_class(context)
''')

print('Fixed file structure')