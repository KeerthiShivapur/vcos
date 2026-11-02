with open('app/services/provider_adapters.py', 'r') as f:
    content = f.read()

# Add outbound_capabilities and supported_entities to GitHubAdapter
old = '''class GitHubAdapter(BaseConnectorAdapter):
    """GitHub adapter for repositories, issues, PRs, commits."""
    
    provider_name = "github"
    
    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = "https://api.github.com"
        self.client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None'''

new = '''class GitHubAdapter(BaseConnectorAdapter):
    """GitHub adapter for repositories, issues, PRs, commits."""
    
    provider_name = "github"
    
    # Operations this connector can perform
    outbound_capabilities = ["create", "read", "update", "delete"]
    
    # Entity types this connector supports
    supported_entities = ["repository", "issue", "pull_request", "commit", "person"]
    
    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = "https://api.github.com"
        self.client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None'''

content = content.replace(old, new)

with open('app/services/provider_adapters.py', 'w') as f:
    f.write(content)
print('Fixed')