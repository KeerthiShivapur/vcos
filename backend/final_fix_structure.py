with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Remove the create_adapter function from the top (first 10 lines)
lines = content.split('\n')
new_lines = []
skip_count = 0
for line in content.split('\n'):
    if skip_count < 10 and 'async def create_adapter' in line:
        skip_count = 1
        continue
    if skip_count > 0:
        skip_count += 1
        if skip_count >= 10:
            skip_count = 0
        continue
    if 'async def create_adapter' in line:
        continue
    if 'Factory function' in line:
        continue
    if 'adapter_class = ADAPTER_REGISTRY.get(action)' in line:
        continue
    if 'if not adapter_class:' in line:
        continue
    if 'return AcceptanceAdapter(context)' in line:
        continue
    if 'return adapter_class(context)' in line:
        continue
    if line.strip() == '' and len(content.split('\n')) - content.split('\n').index(line) < 15:
        continue
    # Keep everything else
    pass

# Actually, let's just do it properly with a simple approach
with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Remove the create_adapter function from the top (first ~10 lines)
lines = content.split('\n')
# Find where the actual imports start (after the create_adapter function)
start_idx = 0
for i, line in enumerate(lines):
    if line.strip().startswith('from ') or line.strip().startswith('import '):
        start_idx = i
        break

# Keep everything from the first import onwards
content = '\n'.join(lines[start_idx:])

# Remove registry from top if present
idx = content.find('# Registry of all adapters')
if idx >= 0:
    end_idx = content.find('\nasync def create_adapter', idx)
    if end_idx < 0:
        end_idx = content.find('\n}\n\n', idx)
        if end_idx >= 0:
            end_idx += 2
        else:
            end_idx = idx + 3000
    content = content[:idx] + content[end_idx:]

# Append registry and create_adapter at the end
addition = '''

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
    "test_governance_on_prediction": GovernanceAdapter,
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
'''

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content + '\n' + addition)

print('Fixed file structure')