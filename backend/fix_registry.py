import re

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Replace the entire registry section
new_registry = '''ADAPTER_REGISTRY: Dict[str, type] = {
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
    "test_cross_tenant_rejection": SecurityAdapter,
    "test_cross_scope_rejection": SecurityAdapter,
    "test_provenance_spoofing": SecurityAdapter,
    "test_unauthorized_autonomy": SecurityAdapter,
    "test_backup": DRAdapter,
    "test_restore": DRAdapter,
    "verify_rpo_rto": DRAdapter,
}'''

# Find the registry section
idx = content.find('ADAPTER_REGISTRY: Dict[str, type] = {')
if idx >= 0:
    # Find the end of the registry (the closing brace)
    brace_count = 0
    start_idx = content.find('ADAPTER_REGISTRY: Dict[str, type] = {')
    if start_idx >= 0:
        i = start_idx + len('ADAPTER_REGISTRY: Dict[str, type] = {')
        brace_count = 1
        while i < len(content) and brace_count > 0:
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
            i += 1
        else:
            end_idx = content.find('\n}\n\n', content.find('ADAPTER_REGISTRY'))
            if end_idx < 0:
                end_idx = content.find('\n}\n\n', content.find('ADAPTER_REGISTRY'))
                if end_idx >= 0:
                    end_idx += 3
                else:
                    end_idx = content.find('ADAPTER_REGISTRY') + 3000
        
        content = content[:content.find('ADAPTER_REGISTRY')] + new_registry + content[end_idx:]
        print('Replaced registry')
    else:
        # Find the first occurrence of ADAPTER_REGISTRY
        idx = content.find('ADAPTER_REGISTRY')
        if idx >= 0:
            # Find the end of the registry dict
            brace_count = 0
            i = content.find('{', content.find('ADAPTER_REGISTRY'))
            if i >= 0:
                brace_count = 1
                j = i + 1
                while j < len(content) and brace_count > 0:
                    if content[j] == '{':
                        brace_count += 1
                    elif content[j] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = j + 1
                            break
                    j += 1
                else:
                    end_idx = content.find('\n}\n\n', content.find('ADAPTER_REGISTRY'))
                    if end_idx >= 0:
                        end_idx += 3
                    else:
                        end_idx = content.find('ADAPTER_REGISTRY') + 3000
                
                content = content[:content.find('ADAPTER_REGISTRY')] + new_registry + content[end_idx:]
                print('Replaced registry')

# Remove any create_adapter functions
content = re.sub(r'\nasync def create_adapter\(action: str, context: AdapterContext\) -> AcceptanceAdapter:.*?return adapter_class\(context\)\n', '', content, flags=re.DOTALL)

# Add the registry and create_adapter at the end
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
    "test_cross_tenant_rejection": SecurityAdapter,
    "test_cross_scope_rejection": SecurityAdapter,
    "test_provenance_spoofing": SecurityAdapter,
    "test_unauthorized_autonomy": SecurityAdapter,
    "test_backup": DRAdapter,
    "test_restore": DRAdapter,
    "verify_rpo_rto": DRAdapter,
}


async def create_adapter(action: str, context: AdapterContext) -> AcceptanceAdapter:
    """Factory function to create adapter for action."""
    adapter_class = ADAPTER_REGISTRY.get(action)
    if not adapter_class:
        return AcceptanceAdapter(context)
    return adapter_class(context)
'''

with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Remove all existing registry sections
content = re.sub(r'# Registry of all adapters\s*\nADAPTER_REGISTRY: Dict\[str, type\] = \{.*?\n\}', '', content, flags=re.DOTALL)

# Remove any create_adapter functions
content = re.sub(r'\nasync def create_adapter\(action: str, context: AdapterContext\) -> AcceptanceAdapter:.*?return adapter_class\(context\)\n', '', content, flags=re.DOTALL)

# Write the cleaned content + new registry
new_content = content.rstrip() + '''

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
    "test_cross_tenant_rejection": SecurityAdapter,
    "test_cross_scope_rejection": SecurityAdapter,
    "test_provenance_spoofing": SecurityAdapter,
    "test_unauthorized_autonomy": SecurityAdapter,
    "test_backup": DRAdapter,
    "test_restore": DRAdapter,
    "verify_rpo_rto": DRAdapter,
}


async def create_adapter(action: str, context: AdapterContext) -> AcceptanceAdapter:
    """Factory function to create adapter for action."""
    adapter_class = ADAPTER_REGISTRY.get(action)
    if not adapter_class:
        return AcceptanceAdapter(context)
    return adapter_class(context)
'''

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed registry')