with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

old_method = '''async def _create_test_identity_mappings(self, db: AsyncSession, org_id: str, 
                                               connector_instances: Dict[str, CI], admin_emp_id: str):
        """Create test identity mappings linking external identities to VCOS persons."""
        for provider, instance in connector_instances.items():
            # Map admin user
            mapping = await external_identity_service.resolve_identity(
                db=db,
                organization_id=org_id,
                connector_instance_id=instance.id,
                external_id=f"{provider}_user_1",
                external_email=f"alice@{provider}.com",
                external_display_name="Alice Admin",
                external_avatar_url=f"https://{provider}.com/avatar/alice",
                external_metadata={"provider": provider},
            )
            # Resolve to admin employee
            await external_identity_service.resolve_mapping(
                db=db,
                mapping_id=mapping.id,
                organization_id=org_id,
                resolved_by=admin_emp_id,
                vcos_entity_id=admin_emp_id,
                resolution_method="manual",
                resolution_notes="Test mapping for admin user",
            )

            # Create a conflict for bob (same email across providers)
            if provider == "google":
                # First mapping - will be the primary
                pass
            elif provider == "microsoft":
                # Second mapping with same email - will create conflict
                mapping2 = await external_identity_service.resolve_identity(
                    db=db,
                    organization_id=org_id,
                    connector_instance_id=instance.id,
                    external_id=f"{provider}_user_2",
                    external_email="bob@google.com",  # Same email as google's bob
                    external_display_name="Bob Builder",
                    external_avatar_url=f"https://{provider}.com/avatar/bob",
                    external_metadata={"provider": provider},
                )
                # This should create a conflict state'''

new_method = '''async def _create_test_identity_mappings(self, db: AsyncSession, org_id: str, 
                                               connector_instances: Dict[str, CI], admin_emp_id: str):
        """Create test identity mappings linking external identities to VCOS persons."""
        for provider, instance in connector_instances.items():
            # Clean up any existing mappings for this test data to ensure clean state
            await db.execute(
                delete(ExternalIdentityMapping).where(
                    ExternalIdentityMapping.organization_id == org_id,
                    ExternalIdentityMapping.connector_instance_id == instance.id,
                    ExternalIdentityMapping.external_id.in_([
                        f"{provider}_user_1",
                        f"{provider}_user_2"
                    ])
                )
            )
            await db.flush()
            
            # Map admin user
            mapping = await external_identity_service.resolve_identity(
                db=db,
                organization_id=org_id,
                connector_instance_id=instance.id,
                external_id=f"{provider}_user_1",
                external_email=f"alice@{provider}.com",
                external_display_name="Alice Admin",
                external_avatar_url=f"https://{provider}.com/avatar/alice",
                external_metadata={"provider": provider},
            )
            # Resolve to admin employee - only if in pending state
            if mapping.mapping_state == "pending":
                await external_identity_service.resolve_mapping(
                    db=db,
                    mapping_id=mapping.id,
                    organization_id=org_id,
                    resolved_by=admin_emp_id,
                    vcos_entity_id=admin_emp_id,
                    resolution_method="manual",
                    resolution_notes="Test mapping for admin user",
                )
            elif mapping.mapping_state == "mapped":
                # Already mapped - verify it's mapped to the correct entity
                assert mapping.vcos_entity_id == admin_emp_id, f"Mapping already resolved to different entity: {mapping.vcos_entity_id}"
            else:
                # Handle other states (conflict, etc.)
                pass

            # Create a conflict for bob (same email across providers)
            if provider == "google":
                # First mapping - will be the primary
                pass
            elif provider == "microsoft":
                # Second mapping with same email - will create conflict
                mapping2 = await external_identity_service.resolve_identity(
                    db=db,
                    organization_id=org_id,
                    connector_instance_id=instance.id,
                    external_id=f"{provider}_user_2",
                    external_email="bob@google.com",  # Same email as google's bob
                    external_display_name="Bob Builder",
                    external_avatar_url=f"https://{provider}.com/avatar/bob",
                    external_metadata={"provider": provider},
                )
                # This should create a conflict state'''

content = content.replace(old_method, new_method)
with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content)
print('Done')