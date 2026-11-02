with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'r') as f:
    content = f.read()

# Find the position before "if __name__ == \"__main__\":"
idx = content.find('if __name__ == "__main__":')
if idx < 0:
    print("Could not find __main__")
    exit(1)

# Methods to add before the __main__ block
methods_to_add = '''

    def _get_adapter(self, provider: str, instance: CI):
        """Get adapter instance for provider."""
        adapter_map = {
            "google": GoogleWorkspaceAdapter,
            "microsoft": Microsoft365Adapter,
            "slack": SlackAdapter,
            "github": GitHubAdapter,
            "jira": JiraAdapter,
        }
        adapter_class = adapter_map.get(provider)
        if adapter_class:
            return adapter_class(instance)
        return None

    async def _mock_sync_data(self, db: AsyncSession, org_id: str, connector_instances: Dict[str, CI]):
        """Create mock sync data for testing identity mapping."""
        for provider, instance in connector_instances.items():
            # Create some mock external people data
            mock_people = [
                {
                    "external_id": f"{provider}_user_1",
                    "email": f"alice@{provider}.com",
                    "display_name": "Alice Admin",
                    "avatar_url": f"https://{provider}.com/avatar/alice",
                    "metadata": {"provider": provider, "mock": True},
                },
                {
                    "external_id": f"{provider}_user_2",
                    "email": f"bob@{provider}.com",
                    "display_name": "Bob Builder",
                    "avatar_url": f"https://{provider}.com/avatar/bob",
                    "metadata": {"provider": provider, "mock": True},
                },
            ]
            await external_identity_service.discover_identities(
                db=db,
                organization_id=org_id,
                connector_instance_id=instance.id,
                external_people=mock_people,
            )


if __name__ == "__main__":
''' + content[content.find('if __name__ == "__main__"'):]

with open('tests/acceptance/test_release_candidate_hardening_e2e.py', 'w') as f:
    f.write(content[:idx] + methods_to_add + content[idx:])
print('Done')