with open('app/intelligence/connectors/slack.py', 'r') as f:
    content = f.read()

# Find the end of the SlackConnector class (before the register call)
old_end = '''# Register the connector
connector_registry.register(SlackConnector())'''

new_end = '''    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_users", "read_channels", "read_messages", "read_files"],
            "outbound_capabilities": ["send_message", "create_channel", "invite_user", "post_message", "update_message", "delete_message", "add_reaction", "create_thread"],
            "supported_entities": ["user", "channel", "message", "file", "reaction", "thread"],
            "supported_events": ["message.posted", "message.updated", "message.deleted", "channel.created", "channel.archived", "member.joined", "member.left", "reaction.added", "reaction.removed", "thread.created"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "bot_token"],
            "oauth_scopes": [
                "channels:read", "channels:manage", "chat:write", "chat:write.public", "channels:read",
                "groups:read", "im:read", "im:write", "mpim:read", "mpim:write",
                "files:read", "files:write", "reactions:read", "reactions:write"
            ],
            "required_config_fields": ["client_id", "client_secret"],
            "optional_config_fields": ["bot_token", "signing_secret"],
            "rate_limits": {
                "api": {"requests_per_second": 50, "burst": 100},
                "chat_postMessage": {"requests_per_minute": 30},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("bot_token") and not credentials.get("user_token"):
            return False, "No bot_token or user_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": utcnow().isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": utcnow().isoformat(),
            "details": {"authenticated": True},
            "latency_ms": 0,
        }

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        # Slack uses HMAC-SHA256 with signing secret
        import hmac
        import hashlib
        credentials = instance.credentials
        signing_secret = credentials.get("signing_secret")
        if not signing_secret:
            return False
        expected = hmac.new(signing_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.get_health_status(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(SlackConnector())'''

# Read the file
with open('app/intelligence/connectors/slack.py', 'r') as f:
    content = f.read()

# Replace the register line
old = '''# Register the connector
connector_registry.register(SlackConnector())'''

new_end = '''    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_users", "read_channels", "read_messages", "read_files"],
            "outbound_capabilities": ["send_message", "create_channel", "invite_user", "post_message", "update_message", "delete_message", "add_reaction", "create_thread"],
            "supported_entities": ["user", "channel", "message", "file", "reaction", "thread"],
            "supported_events": ["message.posted", "message.updated", "message.deleted", "channel.created", "channel.archived", "member.joined", "member.left", "reaction.added", "reaction.removed", "thread.created"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "bot_token"],
            "oauth_scopes": [
                "channels:read", "channels:manage", "chat:write", "chat:write.public", "channels:read",
                "groups:read", "im:read", "im:write", "mpim:read", "mpim:write",
                "files:read", "files:write", "reactions:read", "reactions:write"
            ],
            "required_config_fields": ["client_id", "client_secret"],
            "optional_config_fields": ["bot_token", "signing_secret"],
            "rate_limits": {
                "api": {"requests_per_second": 50, "burst": 100},
                "chat_postMessage": {"requests_per_minute": 30},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("bot_token") and not credentials.get("user_token"):
            return False, "No bot_token or user_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": utcnow().isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": utcnow().isoformat(),
            "details": {"authenticated": True},
            "latency_ms": 0,
        }

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        # Slack uses HMAC-SHA256 with signing secret
        import hmac
        import hashlib
        credentials = instance.credentials
        signing_secret = credentials.get("signing_secret")
        if not signing_secret:
            return False
        expected = hmac.new(signing_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.get_health_status(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(SlackConnector())'''

# Read and replace
with open('app/intelligence/connectors/slack.py', 'r') as f:
    content = f.read()

old = '''# Register the connector
connector_registry.register(SlackConnector())'''

new_end = '''    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        """Discover and return the connector's capabilities."""
        return {
            "inbound_capabilities": ["read_users", "read_channels", "read_messages", "read_files"],
            "outbound_capabilities": ["send_message", "create_channel", "invite_user", "post_message", "update_message", "delete_message", "add_reaction", "create_thread"],
            "supported_entities": ["user", "channel", "message", "file", "reaction", "thread"],
            "supported_events": ["message.posted", "message.updated", "message.deleted", "channel.created", "channel.archived", "member.joined", "member.left", "reaction.added", "reaction.removed", "thread.created"],
            "sync_modes": ["full", "incremental", "webhook", "polling"],
            "auth_types": ["oauth2", "bot_token"],
            "oauth_scopes": [
                "channels:read", "channels:manage", "chat:write", "chat:write.public", "channels:read",
                "groups:read", "im:read", "im:write", "mpim:read", "mpim:write",
                "files:read", "files:write", "reactions:read", "reactions:write"
            ],
            "required_config_fields": ["client_id", "client_secret"],
            "optional_config_fields": ["bot_token", "signing_secret"],
            "rate_limits": {
                "api": {"requests_per_second": 50, "burst": 100},
                "chat_postMessage": {"requests_per_minute": 30},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("bot_token") and not credentials.get("user_token"):
            return False, "No bot_token or user_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": utcnow().isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": utcnow().isoformat(),
            "details": {"authenticated": True},
            "latency_ms": 0,
        }

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        # Slack uses HMAC-SHA256 with signing secret
        import hmac
        import hashlib
        credentials = instance.credentials
        signing_secret = credentials.get("signing_secret")
        if not signing_secret:
            return False
        expected = hmac.new(signing_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.get_health_status(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)


# Register the connector
connector_registry.register(SlackConnector())'''

# Read and replace
with open('app/intelligence/connectors/slack.py', 'r') as f:
    content = f.read()

content = content.replace(
    '''# Register the connector
connector_registry.register(SlackConnector())''',
    new_end
)

with open('app/intelligence/connectors/slack.py', 'w') as f:
    f.write(content)
print('Fixed Slack connector')